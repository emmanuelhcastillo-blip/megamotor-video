"""QA automático de salida. Un reel que falle aquí no llega al dueño.

freezedetect, blackdetect, signalstats (brillo YAVG), volumedetect (picos), silencedetect y ebur128.
Se analiza también el original (una vez, en caché, y en el mismo pase que el seguimiento de cara):
un fallo solo cuenta si es nuevo. La imagen de la salida se mide dentro del propio render (rama del
grafo); del archivo final se comprueban duración, resolución y audio.
"""
import json
import pathlib
import re
import subprocess

from . import cuts, media

FREEZE_MIN = 2.0      # s de imagen congelada para considerarlo fallo
BLACK_MIN = 0.5       # s de negro
SILENCE_MIN = 1.5     # s de silencio nuevo = posible voz perdida
DARKEN_MAX = 0.85     # brillo medio de salida >= 85 % del original
CLIP_DB = -0.1        # pico >= -0.1 dBFS = saturación
DUR_TOL = 0.15        # s
LUFS, LUFS_TOL = -16.0, 1.5


def _ranges(starts, ends, total):
    ends = ends + [total] * (len(starts) - len(ends))  # un evento abierto al final dura hasta el final
    return [(round(a, 2), round(b, 2)) for a, b in zip(starts, ends) if b > a]


def video_tap(yavg_name):
    """Cadena de filtros que mide congelaciones, negros y brillo. Se usa sobre un archivo o como rama
    dentro del propio render (así la salida no se vuelve a decodificar)."""
    return (f"scale=320:-2,format=yuv420p,freezedetect=n=-60dB:d={FREEZE_MIN},blackdetect=d={BLACK_MIN}:pix_th=0.10,"
            f"signalstats,metadata=print:key=lavfi.signalstats.YAVG:file='{yavg_name}'")


AUDIO_TAP = f"volumedetect,silencedetect=noise=-45dB:d={SILENCE_MIN},ebur128=peak=none"


def parse(log, yavg_file, info, video=True):
    total = info["duration"]
    f = lambda pat: [float(x) for x in re.findall(pat, log)]
    out = {"duration": round(total, 2), "width": info["width"], "height": info["height"], "has_audio": info["has_audio"]}
    if video:
        yavg = []
        yavg_file = pathlib.Path(yavg_file)
        if yavg_file.exists():
            yavg = [float(x) for x in re.findall(r"YAVG=([\d.]+)", yavg_file.read_text())]
            yavg_file.unlink()
        ys = sorted(yavg)
        out.update({
            "freezes": _ranges(f(r"freeze_start: ([\d.]+)"), f(r"freeze_end: ([\d.]+)"), total),
            "blacks": _ranges(f(r"black_start:([\d.]+)"), f(r"black_end:([\d.]+)"), total),
            "brightness_mean": round(sum(ys) / len(ys), 1) if ys else None,
            "brightness_p10": round(ys[len(ys) // 10], 1) if ys else None,
        })
    if info["has_audio"]:
        mx = f(r"max_volume: (-?[\d.]+) dB")
        mn = f(r"mean_volume: (-?[\d.]+) dB")
        out["audio_peak_db"] = mx[0] if mx else None
        out["audio_mean_db"] = mn[0] if mn else None
        lu = re.findall(r"I:\s+(-?[\d.]+) LUFS", log)
        out["loudness_lufs"] = float(lu[-1]) if lu else None
        out["silences"] = _ranges(f(r"silence_start: (-?[\d.]+)"), f(r"silence_end: ([\d.]+)"), total)
    return out


def analyze(path, video=True, frame_cb=None, frame_size=None, frame_fps=5.0):
    """Mide un archivo en un solo pase. video=False: solo audio (barato).
    frame_cb(t, gris): además entrega fotogramas en gris a frame_fps (para el seguimiento de cara)
    aprovechando la misma decodificación."""
    import tempfile
    path = pathlib.Path(path)
    info = media.probe(path)
    yavg = path.with_name(path.name + ".yavg.txt")
    parts, maps = [], []
    if video:
        if frame_cb:
            w, h = frame_size
            parts.append(f"[0:v]split=2[q0][r0];[q0]{video_tap(yavg.name)}[v];[r0]fps={frame_fps},scale={w}:{h},format=gray[r]")
        else:
            parts.append(f"[0:v]{video_tap(yavg.name)}[v]")
        maps += ["-map", "[v]"]
    if info["has_audio"]:
        parts.append(f"[0:a]{AUDIO_TAP}[a]")
        maps += ["-map", "[a]"]
    if not parts:
        return parse("", yavg, info, video)
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", path.name, "-filter_complex", ";".join(parts)]
    if frame_cb:
        cmd += ["-map", "[r]", "-f", "rawvideo", "pipe:1"]
    cmd += maps + ["-f", "null", "-"]
    with tempfile.TemporaryFile("w+") as err:  # stderr a archivo: si fuera una tubería podría bloquear el pase
        p = subprocess.Popen(cmd, cwd=path.parent, stdout=subprocess.PIPE if frame_cb else subprocess.DEVNULL, stderr=err)
        if frame_cb:
            import numpy as np
            n, k = frame_size[0] * frame_size[1], 0
            while True:
                buf = p.stdout.read(n)
                if len(buf) < n:
                    break
                frame_cb(k / frame_fps, np.frombuffer(buf, np.uint8).reshape(frame_size[1], frame_size[0]))
                k += 1
        p.wait()
        err.seek(0)
        log = err.read()
    if p.returncode != 0:
        raise RuntimeError(log[-1500:])
    return parse(log, yavg, info, video)


def source(job_dir, frame_cb=None, frame_size=None):
    """Análisis del original, en caché (qa_source.json) mientras el archivo no cambie."""
    job_dir = pathlib.Path(job_dir)
    src = next(job_dir.glob("source.*"))
    st = src.stat()
    key = f"{st.st_size}-{int(st.st_mtime)}"
    f = job_dir / "qa_source.json"
    if f.exists() and not frame_cb:
        c = json.loads(f.read_text(encoding="utf-8"))
        if c.get("_key") == key:
            return c
    a = analyze(src, frame_cb=frame_cb, frame_size=frame_size)
    a["_key"] = key
    f.write_text(json.dumps(a), encoding="utf-8")
    return a


def _new(out_ranges, src_ranges, tol=0.5):
    """Tramos de salida que no se solapan con ninguno del original (con tolerancia)."""
    return [r for r in out_ranges
            if not any(r[0] < s[1] + tol and s[0] - tol < r[1] for s in src_ranges)]


def check(src, out, expect=(1080, 1920), segs=None, static=(), src_an=None, out_video=None):
    """src_an: análisis del original (caché). out_video: métricas de vídeo de la salida medidas dentro del
    render; si vienen, del archivo solo se mide el audio (no se decodifica la imagen otra vez)."""
    s = dict(src_an) if src_an else analyze(src)
    o = analyze(out, video=out_video is None)
    if out_video:
        o.update(out_video)
    checks = []
    expected = s["duration"]
    if segs:  # cortes aprobados: los tramos del original se llevan al tiempo de la salida
        expected = round(sum(b - a for a, b in segs), 2)
        for k in ("freezes", "blacks", "silences"):
            if k in s:
                s[k] = [m for r in s[k] for m in cuts.map_range(r, segs)]

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    add("duracion", o["duration"] >= expected - DUR_TOL,
        f"salida {o['duration']}s vs esperado {expected}s" + (f" (original {s['duration']}s, cortes aprobados)" if segs else ""))
    if expect:
        add("resolucion", (o["width"], o["height"]) == tuple(expect), f"{o['width']}x{o['height']}")
    nf = _new(o["freezes"], s["freezes"] + [tuple(x) for x in static or []], tol=0.2)
    add("sin_congelaciones", not nf, nf or "ninguna nueva")
    nb = _new(o["blacks"], s["blacks"])
    add("sin_negros", not nb, nb or "ninguno nuevo")
    if s["brightness_mean"] and o["brightness_mean"] is not None:
        ratio = o["brightness_mean"] / s["brightness_mean"]
        add("sin_oscurecer", ratio >= DARKEN_MAX,
            f"brillo medio {o['brightness_mean']} vs {s['brightness_mean']} ({ratio:.0%})")
    if s["has_audio"]:
        add("audio_presente", o["has_audio"], "pista de audio en la salida" if o["has_audio"] else "¡sin audio!")
        if o["has_audio"]:
            pk = o.get("audio_peak_db")
            add("sin_saturacion", pk is not None and pk < CLIP_DB, f"pico {pk} dBFS")
            lu = o.get("loudness_lufs")
            add("loudness", lu is not None and abs(lu - LUFS) <= LUFS_TOL, f"{lu} LUFS (objetivo {LUFS})")
            ns = _new(o["silences"], s["silences"])
            add("voz_intacta", not ns, ns or "sin silencios nuevos")
    report = {"ok": all(c["ok"] for c in checks), "checks": checks, "source": s, "output": o}
    return report


def run(job_dir, out_name="reel.mp4", expect=(1080, 1920), segs=None, static=None, out_video=None):
    """segs: tramos conservados si hubo cortes aprobados. static: tramos de salida con imagen fija
    intencionada (pip). Si no se pasan, se leen de render_report.json (comando `qa` suelto)."""
    job_dir = pathlib.Path(job_dir)
    src = next(job_dir.glob("source.*"))
    rr = job_dir / "render_report.json"
    r = json.loads(rr.read_text(encoding="utf-8")) if rr.exists() else {}
    if segs is None:
        segs = [tuple(x) for x in r.get("keep_segments") or []]
    if static is None:
        static = [tuple(x) for x in r.get("static_ranges") or []]
    rep = check(src, job_dir / out_name, expect, segs, static, src_an=source(job_dir), out_video=out_video)
    (job_dir / "qa_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return rep


def summary(rep):
    lines = [("OK   " if c["ok"] else "FALLO ") + f"{c['check']}: {c['detail']}" for c in rep["checks"]]
    return "\n".join(lines + ["QA " + ("VERDE" if rep["ok"] else "ROJO")])
