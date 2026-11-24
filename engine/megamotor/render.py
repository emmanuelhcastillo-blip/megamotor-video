"""Render final. Reglas duras: la voz no se toca y la duración no se acorta respecto al original.
Pensado para 2 CPU: libx264 veryfast, un solo pase de ffmpeg."""
import json
import pathlib
import time

from . import captions, cuts, media, qa
from .config import env


def render(job_dir: pathlib.Path, subs="es", vertical=True, crop_x=None, font=None, crf=20, apply_cuts=False):
    job_dir = pathlib.Path(job_dir)
    src = next(job_dir.glob("source.*"))
    info = media.probe(src)
    out = job_dir / "reel.mp4"
    vf = []
    segs = None
    if apply_cuts:
        data = cuts.load(job_dir)
        if not data or not data.get("owner_approved"):
            raise SystemExit("Los cortes no están aprobados por el dueño (cuts <id> --approve). No se corta nada.")
        segs = cuts.keeps(data["cuts"], info["duration"])
        if not any(c.get("apply") for c in data["cuts"]):
            segs = None
    expected = sum(b - a for a, b in segs) if segs else info["duration"]

    if vertical:
        # cubre 1080x1920 y recorta. crop_x en píxeles del frame ya escalado; None = centro.
        x = "(iw-1080)/2" if crop_x is None else str(int(crop_x))
        vf.append(f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:{x}:(ih-1920)/2")

    if subs != "none":
        words_file = job_dir / "words.json"
        if not words_file.exists():
            raise SystemExit("No hay words.json. Corre primero: megamotor transcribe <id>")
        words = json.loads(words_file.read_text(encoding="utf-8"))["words"]
        plan_file = job_dir / "plan.json"
        plan = json.loads(plan_file.read_text(encoding="utf-8")) if plan_file.exists() else {}
        pt = plan.get("pt_segments") if subs == "es-pt" else None
        if segs:
            words, pt = cuts.remap_words(words, segs), cuts.remap_segments(pt, segs)
        ass = captions.build_ass(words, pt, font=font or env("SUB_FONT", "DejaVu Sans"))
        (job_dir / "subs.ass").write_text(ass, encoding="utf-8")
        vf.append("ass=subs.ass")

    cmd = ["ffmpeg", "-y", "-v", "error", "-i", src.name]
    loud = "loudnorm=I=-16:TP=-1.5:LRA=11"
    if segs:
        g, vl, al = cuts.filter_graph(segs, info["has_audio"])
        g += f";[{vl}]{','.join(vf) or 'null'}[vout]"
        if info["has_audio"]:
            g += f";[{al}]{loud}[aout]"
        cmd += ["-filter_complex", g, "-map", "[vout]"] + (["-map", "[aout]"] if info["has_audio"] else [])
    elif vf:
        cmd += ["-vf", ",".join(vf)]
    fps = min(round(info["fps"]), 30)
    cmd += ["-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p"]
    if info["has_audio"]:
        if not segs:
            cmd += ["-af", loud]
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    cmd += ["-movflags", "+faststart", out.name]

    t0 = time.time()
    import subprocess
    p = subprocess.run(cmd, cwd=job_dir, capture_output=True, text=True)  # cwd para que ass=subs.ass resuelva
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-1500:])
    secs = time.time() - t0

    res = media.probe(out)
    if res["duration"] < expected - 0.15:
        raise RuntimeError(f"El render quedó más corto de lo debido ({res['duration']:.2f}s < {expected:.2f}s). Regla dura violada.")
    media.thumbnail(out, job_dir / "cover.jpg", at=min(1.0, res["duration"] / 2))
    report = {"render_seconds": round(secs, 1), "source_seconds": round(info["duration"], 2),
              "output_seconds": round(res["duration"], 2), "size_mb": res["size_mb"],
              "resolution": f"{res['width']}x{res['height']}", "under_10_min": secs < 600,
              "cuts_applied": len(cuts.merge([c for c in data["cuts"] if c.get("apply")])) if segs else 0,
              "cut_seconds": round(info["duration"] - expected, 2)}
    t1 = time.time()
    rq = qa.run(job_dir, out.name, expect=(1080, 1920) if vertical else None, segs=segs or [])
    report["qa_ok"] = rq["ok"]
    report["qa_seconds"] = round(time.time() - t1, 1)
    (job_dir / "render_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
