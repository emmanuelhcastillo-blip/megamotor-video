"""QA automático de salida. Un reel que falle aquí no llega al dueño.

Un solo pase de ffmpeg por archivo (a 320 px de ancho para que sea barato en 2 CPU):
freezedetect, blackdetect, signalstats (brillo YAVG), volumedetect (picos) y silencedetect.
Se analiza también el original: un fallo solo cuenta si es nuevo (no venía ya en la fuente).
"""
import json
import pathlib
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor

from . import media

FREEZE_MIN = 2.0      # s de imagen congelada para considerarlo fallo
BLACK_MIN = 0.5       # s de negro
SILENCE_MIN = 1.5     # s de silencio nuevo = posible voz perdida
DARKEN_MAX = 0.85     # brillo medio de salida >= 85 % del original
CLIP_DB = -0.1        # pico >= -0.1 dBFS = saturación
DUR_TOL = 0.15        # s


def _ranges(starts, ends, total):
    ends = ends + [total] * (len(starts) - len(ends))  # un evento abierto al final dura hasta el final
    return [(round(a, 2), round(b, 2)) for a, b in zip(starts, ends) if b > a]


def analyze(path):
    """Mide un archivo. Devuelve tramos congelados/negros/silenciosos, brillo y picos."""
    info = media.probe(path)
    total = info["duration"]
    yavg_file = pathlib.Path(str(path) + ".yavg.txt")
    v = (f"[0:v]scale=320:-2,freezedetect=n=-60dB:d={FREEZE_MIN},blackdetect=d={BLACK_MIN}:pix_th=0.10,"
         f"signalstats,metadata=print:key=lavfi.signalstats.YAVG:file='{yavg_file.name}'[v]")
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", pathlib.Path(path).name]
    if info["has_audio"]:
        a = f"[0:a]volumedetect,silencedetect=noise=-45dB:d={SILENCE_MIN}[a]"
        cmd += ["-filter_complex", f"{v};{a}", "-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-filter_complex", v, "-map", "[v]"]
    cmd += ["-f", "null", "-"]
    p = subprocess.run(cmd, cwd=pathlib.Path(path).parent, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-1500:])
    log = p.stderr
    f = lambda pat: [float(x) for x in re.findall(pat, log)]

    yavg = []
    if yavg_file.exists():
        yavg = [float(x) for x in re.findall(r"YAVG=([\d.]+)", yavg_file.read_text())]
        yavg_file.unlink()
    ys = sorted(yavg)
    out = {
        "duration": round(total, 2),
        "width": info["width"], "height": info["height"], "has_audio": info["has_audio"],
        "freezes": _ranges(f(r"freeze_start: ([\d.]+)"), f(r"freeze_end: ([\d.]+)"), total),
        "blacks": _ranges(f(r"black_start:([\d.]+)"), f(r"black_end:([\d.]+)"), total),
        "brightness_mean": round(sum(ys) / len(ys), 1) if ys else None,
        "brightness_p10": round(ys[len(ys) // 10], 1) if ys else None,
    }
    if info["has_audio"]:
        mx = f(r"max_volume: (-?[\d.]+) dB")
        mn = f(r"mean_volume: (-?[\d.]+) dB")
        out["audio_peak_db"] = mx[0] if mx else None
        out["audio_mean_db"] = mn[0] if mn else None
        out["silences"] = _ranges(f(r"silence_start: (-?[\d.]+)"), f(r"silence_end: ([\d.]+)"), total)
    return out


def _new(out_ranges, src_ranges, tol=0.5):
    """Tramos de salida que no se solapan con ninguno del original (con tolerancia)."""
    return [r for r in out_ranges
            if not any(r[0] < s[1] + tol and s[0] - tol < r[1] for s in src_ranges)]


def check(src, out, expect=(1080, 1920)):
    with ThreadPoolExecutor(2) as ex:
        fs, fo = ex.submit(analyze, src), ex.submit(analyze, out)
        s, o = fs.result(), fo.result()
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    add("duracion", o["duration"] >= s["duration"] - DUR_TOL,
        f"salida {o['duration']}s vs original {s['duration']}s")
    if expect:
        add("resolucion", (o["width"], o["height"]) == tuple(expect), f"{o['width']}x{o['height']}")
    nf = _new(o["freezes"], s["freezes"])
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
            ns = _new(o["silences"], s["silences"])
            add("voz_intacta", not ns, ns or "sin silencios nuevos")
    report = {"ok": all(c["ok"] for c in checks), "checks": checks, "source": s, "output": o}
    return report


def run(job_dir, out_name="reel.mp4", expect=(1080, 1920)):
    job_dir = pathlib.Path(job_dir)
    src = next(job_dir.glob("source.*"))
    rep = check(src, job_dir / out_name, expect)
    (job_dir / "qa_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return rep


def summary(rep):
    lines = [("OK   " if c["ok"] else "FALLO ") + f"{c['check']}: {c['detail']}" for c in rep["checks"]]
    return "\n".join(lines + ["QA " + ("VERDE" if rep["ok"] else "ROJO")])
