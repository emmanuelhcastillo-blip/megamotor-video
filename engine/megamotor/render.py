"""Render final. Reglas duras: la voz no se toca y la duración no se acorta respecto al original.
Pensado para 2 CPU: libx264 veryfast, un solo pase de ffmpeg."""
import json
import pathlib
import time

from . import captions, cuts, effects, media, motion, qa, reframe, sound
from .config import env


def render(job_dir: pathlib.Path, subs="es", vertical=True, crop_x=None, font=None, crf=20, apply_cuts=False, track=True):
    job_dir = pathlib.Path(job_dir)
    src = next(job_dir.glob("source.*"))
    info = media.probe(src)
    out = job_dir / "reel.mp4"
    segs = None
    if apply_cuts:
        data = cuts.load(job_dir)
        if not data or not data.get("owner_approved"):
            raise SystemExit("Los cortes no están aprobados por el dueño (cuts <id> --approve). No se corta nada.")
        segs = cuts.keeps(data["cuts"], info["duration"])
        if not any(c.get("apply") for c in data["cuts"]):
            segs = None
    expected = sum(b - a for a, b in segs) if segs else info["duration"]

    plan_file = job_dir / "plan.json"
    plan = json.loads(plan_file.read_text(encoding="utf-8")) if plan_file.exists() else {}
    fps = min(round(info["fps"]), 30)
    inputs = ["-i", src.name]
    graph = []
    if segs:
        g, vin, ain = cuts.filter_graph(segs, info["has_audio"])
        graph.append(g)
    else:
        vin, ain = "0:v", "0:a"

    tracked, zooms, pips, box = None, [], [], None
    if vertical:
        # cubre 1080x1920 y recorta. crop_x en píxeles del frame ya escalado; None = seguir la cara (o centro).
        # x se expresa respecto a sw para que el zoom de énfasis siga centrado en el mismo punto.
        sw, sh = effects.scaled_size(info["width"], info["height"])
        x = "(iw-1080)/2" if crop_x is None else f"{int(crop_x) + 540}*iw/{sw}-540"
        crop = f"crop@rf=1080:1920:{x}:(ih-1920)*0.4"
        if crop_x is None and track and sw > 1080 * 1.02 and reframe.available():
            rf = reframe.run(job_dir)
            if rf["face_ratio"] >= 0.2:
                to_src = (lambda t: cuts.unmap_time(t, segs)) if segs else (lambda t: t)
                reframe.write_sendcmd(rf["path"], rf["shots"], job_dir / "crop.cmd", fps, expected, to_src, sw)
                crop = "sendcmd=f=crop.cmd," + crop
                tracked = rf["face_ratio"]
                box = rf.get("face_box")
        zooms = effects._to_out(plan.get("zooms"), segs)
        if zooms:
            scale = f"scale=w='trunc({sw}*({effects.zoom_expr(zooms)})/2)*2':h=-2:eval=frame"
        else:
            scale = f"scale={sw}:{sh}"
        graph.append(f"[{vin}]{scale},setsar=1,{crop}[vbase]")
        pips = effects._to_out(plan.get("pip"), segs)
    else:
        graph.append(f"[{vin}]null[vbase]")
    words_file = job_dir / "words.json"
    all_words = json.loads(words_file.read_text(encoding="utf-8"))["words"] if words_file.exists() else []
    mitems = effects._to_out(motion.validate(plan.get("motion"), all_words), segs)
    effects.no_overlap(zooms + pips + mitems)

    vcur = "vbase"
    if pips:
        imgs = effects.pip_images(job_dir, pips)
        mask, ring = effects.make_masks(job_dir)
        first = inputs.count("-i")
        inputs += ["-i", mask.name, "-i", ring.name]
        for img in imgs:
            inputs += ["-loop", "1", "-i", str(img)]
        parts, vcur = effects.pip_graph(vcur, pips, first, fps, box)
        graph += parts
    if mitems:
        mitems = motion.place(mitems, box)
        paths = motion.render_clips(job_dir, mitems)
        first = inputs.count("-i")
        for f in paths:
            inputs += ["-i", str(f.relative_to(job_dir))]
        parts, vcur = motion.overlay_graph(vcur, mitems, paths, first)
        graph += parts

    if subs != "none":
        words_file = job_dir / "words.json"
        if not words_file.exists():
            raise SystemExit("No hay words.json. Corre primero: megamotor transcribe <id>")
        words = json.loads(words_file.read_text(encoding="utf-8"))["words"]
        pt = plan.get("pt_segments") if subs == "es-pt" else None
        if segs:
            words, pt = cuts.remap_words(words, segs), cuts.remap_segments(pt, segs)
        # durante la tipografía cinética el texto ya está en pantalla: no se repite en el subtítulo ES
        kin = [(m["start"], m["end"]) for m in mitems if m["kind"] == "cinetica"]
        words = [w for w in words if not any(a - 0.05 <= w["start"] < b for a, b in kin)]
        ass = captions.build_ass(words, pt, font=font or env("SUB_FONT", "DejaVu Sans"))
        (job_dir / "subs.ass").write_text(ass, encoding="utf-8")
        graph.append(f"[{vcur}]ass=subs.ass[vout]")
    else:
        graph.append(f"[{vcur}]null[vout]")
    srep = {}
    if info["has_audio"]:
        an = sound.run(job_dir, all_words)
        parts, extra, srep = sound.audio_graph(job_dir, ain, plan, an, segs, inputs.count("-i"))
        inputs += extra
        graph += parts
        srep["music_in_source"] = an.get("music_likely")

    cmd = ["ffmpeg", "-y", "-v", "error"] + inputs + ["-filter_complex", ";".join(graph), "-map", "[vout]"]
    if info["has_audio"]:
        cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    cmd += ["-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-t", f"{expected + 0.05:.3f}", "-movflags", "+faststart", out.name]

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
              "cut_seconds": round(info["duration"] - expected, 2),
              "reframe": f"cara {tracked:.0%}" if tracked is not None else ("manual" if crop_x is not None else "centro"),
              "zooms": len(zooms), "pip": len(pips), "motion": len(mitems), "sound": srep,
              "keep_segments": segs or [], "static_ranges": [[x["start"], x["end"]] for x in pips]}
    t1 = time.time()
    rq = qa.run(job_dir, out.name, expect=(1080, 1920) if vertical else None, segs=segs or [],
                static=report["static_ranges"])
    report["qa_ok"] = rq["ok"]
    report["qa_seconds"] = round(time.time() - t1, 1)
    (job_dir / "render_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
