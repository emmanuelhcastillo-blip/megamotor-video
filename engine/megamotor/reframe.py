"""Reencuadre 9:16 con seguimiento de cara (OpenCV, sin GPU).

1. Se muestrea el video a 5 fps en gris a 480 px (barato en 2 CPU) y se detectan caras (Haar de OpenCV).
2. Se detectan cambios de plano: dentro de un plano la cámara se mueve suave; entre planos puede saltar.
3. Suavizado offline sin retardo: mediana (quita detecciones sueltas) + media centrada + zona muerta
   (no micro-corrige) + límite de velocidad (nunca un latigazo).
4. El recorrido se escribe como `sendcmd` para el filtro crop: un solo pase de ffmpeg.

Idea de la cadena zona muerta + límite de velocidad estudiada en artbyjazi/autoclip (MIT); esta
implementación es propia (ver docs/CREDITOS.md).
"""
import bisect
import json
import pathlib

from . import media

SAMPLE_FPS = 5.0
ANALYSIS_W = 480
SCENE_DIFF = 28.0       # diferencia media (0-255) entre muestras = cambio de plano
DEAD_ZONE = 40          # px del frame escalado: por debajo, el encuadre no se mueve
MAX_SPEED = 800         # px/s (la mediana ya quita detecciones sueltas)
OUT_W, OUT_H = 1080, 1920


def available():
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


def analysis_size(width, height):
    return ANALYSIS_W, int(round(height * ANALYSIS_W / width / 2)) * 2


class FaceScan:
    """Recibe fotogramas en gris (t, imagen) y acumula caras y cambios de plano."""

    def __init__(self, info):
        import cv2
        self.cv2 = cv2
        self.info = info
        self.w, self.h = analysis_size(info["width"], info["height"])
        self.front = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self.prof = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
        self.samples, self.shots, self.prev_small, self.prev_cx = [], [0.0], None, None

    def feed(self, t, g):
        import numpy as np
        cv2, w, h = self.cv2, self.w, self.h
        small = cv2.resize(g, (64, 36), interpolation=cv2.INTER_AREA).astype(np.int16)
        if self.prev_small is not None and np.abs(small - self.prev_small).mean() > SCENE_DIFF:
            self.shots.append(round(t, 2))
            self.prev_cx = None
        self.prev_small = small
        ming = max(24, h // 12)
        faces = list(self.front.detectMultiScale(g, 1.1, 5, minSize=(ming, ming)))
        if not faces:
            faces = list(self.prof.detectMultiScale(g, 1.1, 5, minSize=(ming, ming)))
            faces += [(w - x - fw, y, fw, fh) for x, y, fw, fh in self.prof.detectMultiScale(cv2.flip(g, 1), 1.1, 5, minSize=(ming, ming))]
        if faces:
            prev = self.prev_cx

            # la cara más grande, pero con preferencia por la que ya seguíamos (no saltar entre personas)
            def score(f):
                x, y, fw, fh = f
                s = fw * fh
                if prev is not None:
                    s *= 1.0 / (1.0 + 4 * abs((x + fw / 2) / w - prev))
                return s
            x, y, fw, fh = max(faces, key=score)
            self.prev_cx = (x + fw / 2) / w
            self.samples.append([round(t, 2), round(self.prev_cx, 4), round(fw / w, 4), round((y + fh / 2) / h, 4)])
        else:
            self.samples.append([round(t, 2), None, None])

    def result(self):
        i = self.info
        return {"duration": i["duration"], "width": i["width"], "height": i["height"],
                "samples": self.samples, "shots": self.shots}


def analyze(src):
    """Análisis suelto (sin QA). El render usa run(), que comparte la decodificación con el QA."""
    from . import qa
    scan = FaceScan(media.probe(src))
    qa.analyze(src, frame_cb=scan.feed, frame_size=(scan.w, scan.h), frame_fps=SAMPLE_FPS)
    return scan.result()


def _median(v, k=2):
    return [sorted(v[max(0, i - k): i + k + 1])[len(v[max(0, i - k): i + k + 1]) // 2] for i in range(len(v))]


def _mean(v, k=3):
    return [sum(v[max(0, i - k): i + k + 1]) / len(v[max(0, i - k): i + k + 1]) for i in range(len(v))]


def build_path(a):
    """Recorrido de x (px del frame escalado a 1920 de alto) por muestra. Devuelve (scaled_w, [(t, x)])."""
    sc = max(OUT_W / a["width"], OUT_H / a["height"])
    sw = int(round(a["width"] * sc / 2)) * 2
    span = max(0, sw - OUT_W)
    centre = span / 2
    samples, shots = a["samples"], a["shots"] + [float("inf")]
    path = []
    for s0, s1 in zip(shots, shots[1:]):
        seg = [s for s in samples if s0 <= s[0] < s1]
        if not seg:
            continue
        known = [(i, s[1]) for i, s in enumerate(seg) if s[1] is not None]
        if not known or span == 0:
            path += [(s[0], centre) for s in seg]
            continue
        # huecos sin cara: se mantiene la última posición conocida (o la siguiente al principio)
        raw, j = [], 0
        for i in range(len(seg)):
            while j + 1 < len(known) and known[j + 1][0] <= i:
                j += 1
            raw.append(known[j][1])
        xs = [min(span, max(0.0, cx * sw - OUT_W / 2)) for cx in raw]
        xs = _mean(_median(xs))
        held, out, pt = xs[0], [], seg[0][0]
        for (t, *_), x in zip(seg, xs):
            if abs(x - held) >= DEAD_ZONE or out == []:
                step = MAX_SPEED * max(t - pt, 1 / SAMPLE_FPS)
                held = held + max(-step, min(step, x - held)) if out else x
            out.append((t, held))
            pt = t
        # la zona muerta deja escalones: una media corta los convierte en arranques/frenadas suaves
        sm = _mean([x for _, x in out], 2)
        path += [(t, round(x, 1)) for (t, _), x in zip(out, sm)]
    return sw, path


def x_at(path, t):
    i = bisect.bisect_right([p[0] for p in path], t)
    if i == 0:
        return path[0][1]
    if i == len(path):
        return path[-1][1]
    (t0, x0), (t1, x1) = path[i - 1], path[i]
    return x0 + (x1 - x0) * (t - t0) / (t1 - t0)


def write_sendcmd(path, shots, out_file, fps, out_duration, to_src=lambda t: t, factor=1.0):
    """Una línea por fotograma de salida cuando x cambia. Dentro de un plano interpola;
    en un cambio de plano el salto es seco (como un corte de cámara), nunca un barrido.
    factor: de píxeles del frame escalado a píxeles de la fuente (el recorte se hace antes de escalar)."""
    by_shot = [[p for p in path if s0 <= p[0] < s1] for s0, s1 in zip(shots, shots[1:] + [float("inf")])]
    lines, last = [], None
    for k in range(int(out_duration * fps) + 1):
        t = k / fps
        ts = to_src(t)
        sub = by_shot[max(0, bisect.bisect_right(shots, ts) - 1)] or path
        x = int(round(x_at(sub, ts) * factor))
        if x != last:
            lines.append(f"{t:.3f} crop@rf x {x};")
            last = x
    pathlib.Path(out_file).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def face_box(a):
    """Cuadrado (x, y, lado) del 9:16 ya recortado donde suele estar la cara: para el círculo del pip."""
    got = [s for s in a["samples"] if s[1] is not None and len(s) > 3]
    if not got:
        return None
    sc = max(OUT_W / a["width"], OUT_H / a["height"])
    fw = sorted(s[2] for s in got)[len(got) // 2] * a["width"] * sc
    cy = sorted(s[3] for s in got)[len(got) // 2] * a["height"] * sc
    side = int(min(OUT_W, max(480, 2.6 * fw))) // 2 * 2
    y = int(min(OUT_H - side, max(0, cy - side * 0.45)))
    return [(OUT_W - side) // 2, y, side]


def run(job_dir):
    """Analiza el original del trabajo y guarda reframe.json (se reutiliza si ya existe).
    La decodificación se comparte con el análisis de QA del original (qa_source.json)."""
    from . import qa
    job_dir = pathlib.Path(job_dir)
    f = job_dir / "reframe.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    scan = FaceScan(media.probe(next(job_dir.glob("source.*"))))
    qa.source(job_dir, frame_cb=scan.feed, frame_size=(scan.w, scan.h))
    a = scan.result()
    a["scaled_width"], a["path"] = build_path(a)
    seen = sum(1 for s in a["samples"] if s[1] is not None)
    a["face_ratio"] = round(seen / max(1, len(a["samples"])), 2)
    a["face_box"] = face_box(a)
    f.write_text(json.dumps(a), encoding="utf-8")
    return a
