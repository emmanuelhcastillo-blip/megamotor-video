"""Cortes inteligentes con aprobación.

El motor PROPONE cortes a partir de words.json (silencios, muletillas, tartamudeos, tomas repetidas)
y los escribe en cuts.json con "apply": false. Por defecto no se corta nada.
Solo se aplican si el dueño aprueba ese video (`cuts <id> --approve`) y se renderiza con --apply-cuts.
Uniones con crossfade de audio de 30 ms para no pinchar la voz.
"""
import json
import pathlib
import re

XFADE = 0.03
SILENCE_GAP = 0.9     # hueco entre palabras para proponer corte
SILENCE_KEEP = 0.25   # aire que se deja a cada lado del silencio
FILLERS = {"eh", "ehh", "ehm", "em", "emm", "mm", "mmm", "ah", "ahh", "um", "uh", "hum"}
SOFT_FILLERS = {"este", "o sea", "bueno", "pues"}  # palabras reales: solo si van aisladas por pausas
TAKE_MIN = 3          # palabras repetidas para considerar toma repetida
TAKE_WINDOW = 25      # palabras máximo entre las dos tomas


def norm(w):
    return re.sub(r"[^\wáéíóúüñç]", "", w.lower())


def propose(words, duration):
    w = [dict(x, n=norm(x["word"])) for x in words]
    cuts = []

    def add(start, end, kind, text, conf):
        start, end = max(0.0, round(start, 3)), min(duration, round(end, 3))
        if end - start >= 0.12:
            cuts.append({"start": start, "end": end, "kind": kind, "text": text, "confidence": conf, "apply": False})

    # silencios (incluye el inicio y el final)
    edges = [(0.0, 0.0)] + [(x["start"], x["end"]) for x in w] + [(duration, duration)]
    for (_, a_end), (b_start, _) in zip(edges, edges[1:]):
        if b_start - a_end > SILENCE_GAP:
            keep_a = 0.0 if a_end == 0.0 else SILENCE_KEEP
            keep_b = 0.0 if b_start == duration else SILENCE_KEEP
            add(a_end + keep_a, b_start - keep_b, "silencio", f"{b_start - a_end:.1f}s", "alta")

    for i, x in enumerate(w):
        prev_end = w[i - 1]["end"] if i else 0.0
        next_start = w[i + 1]["start"] if i + 1 < len(w) else duration
        if x["n"] in FILLERS:
            add(max(prev_end, x["start"] - 0.03), min(next_start, x["end"] + 0.03), "muletilla", x["word"], "alta")
        elif x["n"] in SOFT_FILLERS and x["start"] - prev_end > 0.3 and next_start - x["end"] > 0.3:
            add(x["start"] - 0.03, x["end"] + 0.03, "muletilla", x["word"], "baja")
        # tartamudeo: misma palabra repetida o fragmento que empieza la siguiente ("pro- problema")
        if i + 1 < len(w) and x["n"]:
            nx = w[i + 1]["n"]
            if x["n"] == nx and nx not in {"no", "sí", "si", "muy"} or (len(x["n"]) <= 4 and len(nx) > len(x["n"]) and nx.startswith(x["n"]) and x["word"].rstrip().endswith("-")):
                add(x["start"], w[i + 1]["start"], "tartamudeo", f"{x['word']} {w[i + 1]['word']}", "media")

    # tomas repetidas: la misma frase de >= TAKE_MIN palabras arranca otra vez poco después -> se corta la primera
    i = 0
    while i < len(w):
        best = None
        for j in range(i + 1, min(len(w), i + TAKE_WINDOW + 1)):
            L = 0
            while j + L < len(w) and i + L < j and w[i + L]["n"] and w[i + L]["n"] == w[j + L]["n"]:
                L += 1
            if L >= TAKE_MIN and (best is None or L > best[1]):
                best = (j, L)
        if best:
            j, L = best
            add(w[i]["start"], w[j]["start"], "toma_repetida",
                " ".join(x["word"] for x in w[i:j]), "media")
            i = j
        else:
            i += 1
    return merge(cuts)


def merge(cuts):
    out = []
    for c in sorted(cuts, key=lambda c: c["start"]):
        if out and c["start"] <= out[-1]["end"]:
            o = out[-1]
            o["end"] = max(o["end"], c["end"])
            if c["kind"] not in o["kind"].split("+"):
                o["kind"] += "+" + c["kind"]
            o["text"] += " | " + c["text"]
            o["confidence"] = min(o["confidence"], c["confidence"], key=["baja", "media", "alta"].index)
        else:
            out.append(dict(c))
    return out


def keeps(cuts, duration):
    """Tramos que se conservan [(a, b)] dados los cortes aplicados."""
    segs, t = [], 0.0
    for c in merge([c for c in cuts if c.get("apply")]):
        if c["start"] > t:
            segs.append((t, c["start"]))
        t = max(t, c["end"])
    if t < duration:
        segs.append((t, duration))
    return [(round(a, 3), round(b, 3)) for a, b in segs if b - a > 0.05]


def map_time(t, segs):
    """Tiempo del original -> tiempo de salida. None si cae dentro de un corte."""
    acc = 0.0
    for a, b in segs:
        if t < a:
            return None
        if t <= b:
            return acc + t - a
        acc += b - a
    return None


def unmap_time(t, segs):
    """Tiempo de salida -> tiempo del original."""
    acc = 0.0
    for a, b in segs:
        if t <= acc + b - a:
            return a + t - acc
        acc += b - a
    return segs[-1][1] if segs else t


def map_range(r, segs):
    """Rango del original -> lista de rangos en la salida (puede partirse)."""
    out, acc = [], 0.0
    for a, b in segs:
        lo, hi = max(r[0], a), min(r[1], b)
        if hi > lo:
            out.append((round(acc + lo - a, 2), round(acc + hi - a, 2)))
        acc += b - a
    return out


def remap_words(words, segs):
    """Palabras del original -> salida. Recorre los tramos en orden, así que un tramo repetido
    (teaser) repite sus palabras. Una palabra partida por un corte se descarta."""
    out, acc = [], 0.0
    for a, b in segs:
        for x in words:
            if x["start"] >= a - 1e-6 and x["end"] <= b + 1e-6:
                out.append(dict(x, start=round(acc + x["start"] - a, 3), end=round(acc + x["end"] - a, 3)))
        acc += b - a
    return out


def remap_segments(segments, segs):
    """Frases (p. ej. pt_segments) -> salida; cada trozo visible conserva su texto."""
    out, acc = [], 0.0
    for a, b in segs:
        for x in segments or []:
            lo, hi = max(x["start"], a), min(x["end"], b)
            if hi - lo > 0.1:
                out.append(dict(x, start=round(acc + lo - a, 3), end=round(acc + hi - a, 3)))
        acc += b - a
    return out


def filter_graph(segs, has_audio, src_name, xfades=None):
    """Una entrada por tramo con búsqueda precisa (-ss/-t antes de -i) y concat.
    No se usa trim sobre una sola entrada: ffmpeg encolaría los fotogramas decodificados de los tramos
    que concat aún no lee y con varios cortes se queda sin memoria.
    Devuelve (entradas, grafo, etiqueta_video, etiqueta_audio); las entradas van primero (índices 0..n-1)."""
    inputs, parts = [], []
    n = len(segs)
    xf = list(xfades) if xfades else [XFADE] * max(0, n - 1)  # un fundido por unión
    for k, (a, b) in enumerate(segs):
        last = k == n - 1
        # el audio necesita el fundido extra para que el crossfade no acorte el audio frente al video
        dur = b - a if last or not has_audio else b - a + xf[k]
        inputs += ["-ss", f"{a:.3f}", "-t", f"{dur:.3f}", "-i", src_name]
        parts.append(f"[{k}:v]trim=duration={b - a:.3f},setpts=PTS-STARTPTS[v{k}]")
        if has_audio:
            parts.append(f"[{k}:a]asetpts=PTS-STARTPTS[a{k}]")
    parts.append("".join(f"[v{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0[vc]")
    alab = None
    if has_audio:
        cur = "a0"
        for k in range(1, n):
            parts.append(f"[{cur}][a{k}]acrossfade=d={xf[k - 1]:.3f}:c1=tri:c2=tri[ax{k}]")
            cur = f"ax{k}"
        alab = cur
    return inputs, ";".join(parts), "vc", alab


def load(job_dir):
    f = pathlib.Path(job_dir) / "cuts.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def save(job_dir, data):
    (pathlib.Path(job_dir) / "cuts.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def snap(segs, pcm, sr=16000, window=0.15, inside=0.02, duration=None):
    """Mueve cada borde interior al punto más silencioso cercano (ventanas de 20 ms), buscando solo hacia
    el lado que se corta: el inicio de un tramo puede adelantarse hasta `window` s y entrar como mucho
    `inside` s; el final, al revés. Así nunca se come el arranque o la cola de una palabra que se conserva
    (los tiempos de Whisper se solapan entre palabras)."""
    import numpy as np
    hop = int(0.02 * sr)

    def quiet(t, lo_t, hi_t):
        lo, hi = max(0, int(lo_t * sr)), min(len(pcm) - hop, int(hi_t * sr))
        if hi <= lo:
            return t
        best, bt = None, t
        for i in range(lo, hi, hop // 2):
            e = float(np.mean(pcm[i:i + hop] ** 2))
            c = (i + hop / 2) / sr
            if best is None or e < best * 0.9 or (e <= best * 1.1 and abs(c - t) < abs(bt - t)):
                best, bt = min(e, best) if best is not None else e, c
        return round(bt, 3)

    out = []
    for a, b in segs:
        na = a if a <= 0.001 else quiet(a, a - window, a + inside)
        nb = b if duration is not None and b >= duration - 0.001 else quiet(b, b - inside, b + window)
        out.append((na, nb) if nb - na > 0.05 else (a, b))
    return out


def digital_gaps(pcm, sr=16000, min_len=0.06, db=-80):
    """Huecos de silencio digital (restos de una edición previa): en un reel suenan a caída de audio."""
    import numpy as np
    hop = int(0.02 * sr)
    n = len(pcm) // hop
    if n == 0:
        return []
    e = 20 * np.log10(np.sqrt((pcm[: n * hop].reshape(n, hop) ** 2).mean(axis=1)) + 1e-9)
    out, i = [], 0
    while i < n:
        if e[i] < db:
            j = i
            while j < n and e[j] < db:
                j += 1
            if (j - i) * 0.02 >= min_len:
                out.append((round(i * 0.02, 3), round(j * 0.02, 3)))
            i = j
        else:
            i += 1
    return out


def xfade_for(segs, pcm, sr=16000, quiet_db=-30, short=XFADE, long=0.08):
    """Fundido por unión: corto si el corte cae en silencio, más largo si cae en mitad del habla."""
    import numpy as np

    def db(t):
        s = pcm[max(0, int(t * sr)): int((t + 0.03) * sr)]
        return 20 * np.log10(np.sqrt(np.mean(s * s)) + 1e-9) if len(s) else -120

    return [long if max(db(b0 - 0.03), db(a1)) > quiet_db else short for (a0, b0), (a1, b1) in zip(segs, segs[1:])]


def subtract(segs, holes, min_len=0.12):
    """Quita los huecos de los tramos (cada tramo puede partirse)."""
    out = []
    for a, b in segs:
        cur = a
        for h0, h1 in sorted(holes):
            if h1 <= cur or h0 >= b:
                continue
            if h0 - cur >= min_len:
                out.append((round(cur, 3), round(h0, 3)))
            cur = max(cur, h1)
        if b - cur >= min_len:
            out.append((round(cur, 3), round(b, 3)))
    return out
