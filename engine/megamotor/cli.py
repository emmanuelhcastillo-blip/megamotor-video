"""CLI: python -m megamotor <comando>"""
import argparse
import json
import shutil

from . import jobs, media
from .config import env, JOBS


def main(argv=None):
    ap = argparse.ArgumentParser(prog="megamotor")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("new", help="crear trabajo desde un video crudo"); s.add_argument("video"); s.add_argument("--name")
    s = sub.add_parser("transcribe", help="palabras con tiempos (Groq gratis; --local = faster-whisper)")
    s.add_argument("id"); s.add_argument("--local", action="store_true"); s.add_argument("--lang", default="es")
    s = sub.add_parser("silences", help="lista silencios (solo informa)"); s.add_argument("id")
    s = sub.add_parser("cuts", help="propone cortes en cuts.json (no corta nada por sí solo)"); s.add_argument("id")
    s.add_argument("--redo", action="store_true", help="rehacer la propuesta")
    s.add_argument("--select", help="marcar para aplicar: 'alta' o índices '0,3,4' o 'ninguno'")
    s.add_argument("--approve", action="store_true", help="SOLO el dueño: aprueba aplicar los cortes marcados")
    s = sub.add_parser("render", help="reel 9:16 con subtítulos, duración fiel al original")
    s.add_argument("id"); s.add_argument("--subs", choices=["none", "es", "es-pt"], default="es")
    s.add_argument("--horizontal", action="store_true"); s.add_argument("--crop-x", type=int); s.add_argument("--crf", type=int, default=20)
    s.add_argument("--apply-cuts", action="store_true", help="aplica cuts.json (exige aprobación del dueño)")
    s.add_argument("--no-track", action="store_true", help="sin seguimiento de cara: recorte centrado")
    s = sub.add_parser("qa", help="QA automático del reel -> qa_report.json"); s.add_argument("id")
    s = sub.add_parser("clips", help="video largo: propone clips por gancho, cierre y autonomía -> clips.json")
    s.add_argument("id"); s.add_argument("--min", type=float, default=20); s.add_argument("--max", type=float, default=60)
    s.add_argument("--n", type=int, default=5)
    s = sub.add_parser("clip-new", help="crea un trabajo nuevo con el clip elegido (rango 1..n)")
    s.add_argument("id"); s.add_argument("rank", type=int); s.add_argument("--name")
    sub.add_parser("status", help="lista trabajos")
    s = sub.add_parser("approve", help="aprobar para publicar"); s.add_argument("id")
    s = sub.add_parser("publish", help="publicar en Instagram (solo aprobados)"); s.add_argument("id")
    s.add_argument("--check", action="store_true", help="solo comprobar (token, cupo, archivo); no publica")
    s = sub.add_parser("comments", help="leer comentarios del reel publicado"); s.add_argument("id")
    s.add_argument("--draft", action="store_true", help="guardar comentarios y preparar replies.json para redactar")
    s = sub.add_parser("insights", help="métricas del reel publicado -> insights.json"); s.add_argument("id")
    sub.add_parser("performance", help="ranking de reels publicados por retención: afina la fórmula de gancho")
    s = sub.add_parser("replies", help="enviar respuestas aprobadas en replies.json"); s.add_argument("id")
    s = sub.add_parser("ui", help="interfaz local de aprobación"); s.add_argument("--port", type=int, default=8765)
    sub.add_parser("doctor", help="revisar entorno y claves")
    a = ap.parse_args(argv)

    if a.cmd == "new":
        jid = jobs.create(a.video, a.name)
        print(jid); print(json.dumps(media.probe(next(jobs.path(jid).glob("source.*"))), indent=2))
    elif a.cmd == "transcribe":
        from . import transcribe
        d = jobs.path(a.id)
        r = transcribe.run(next(d.glob("source.*")), d, a.lang, a.local)
        jobs.write(a.id, status="transcrito"); print(f"{len(r['words'])} palabras · motor {r['engine']}")
    elif a.cmd == "silences":
        d = jobs.path(a.id)
        for s0, s1 in media.detect_silences(next(d.glob("source.*"))): print(f"{s0:.2f} -> {s1:.2f}")
    elif a.cmd == "cuts":
        from . import cuts
        d = jobs.path(a.id)
        data = cuts.load(d)
        if data is None or a.redo:
            wf = d / "words.json"
            if not wf.exists(): raise SystemExit("No hay words.json. Corre primero: megamotor transcribe <id>")
            dur = media.probe(next(d.glob("source.*")))["duration"]
            data = {"owner_approved": False, "source_seconds": round(dur, 2),
                    "cuts": cuts.propose(json.loads(wf.read_text(encoding="utf-8"))["words"], dur)}
        if a.select:
            sel = a.select.strip()
            for k, c in enumerate(data["cuts"]):
                c["apply"] = (c["confidence"] == "alta") if sel == "alta" else (sel != "ninguno" and str(k) in sel.split(","))
            data["owner_approved"] = False  # cambiar la selección invalida la aprobación
        if a.approve:
            data["owner_approved"] = True
        cuts.save(d, data)
        for k, c in enumerate(data["cuts"]):
            print(f"[{k}] {'X' if c['apply'] else ' '} {c['start']:7.2f}-{c['end']:7.2f} {c['kind']:<24} {c['confidence']:<5} {c['text'][:50]}")
        sel = [c for c in data["cuts"] if c["apply"]]
        print(f"{len(sel)} marcados, -{sum(c['end'] - c['start'] for c in sel):.1f}s · aprobado por el dueño: {'sí' if data['owner_approved'] else 'no'}")
    elif a.cmd == "render":
        from . import render
        d = jobs.path(a.id)
        rep = render.render(d, a.subs, not a.horizontal, a.crop_x, crf=a.crf, apply_cuts=a.apply_cuts, track=not a.no_track)
        jobs.write(a.id, status="renderizado" if rep["qa_ok"] else "qa_fallido"); print(json.dumps(rep, indent=2))
        from . import qa
        print(qa.summary(json.loads((d / "qa_report.json").read_text(encoding="utf-8"))))
        if not rep["qa_ok"]: raise SystemExit("QA en rojo: el reel no pasa al dueño. Revisa qa_report.json.")
    elif a.cmd == "qa":
        from . import qa
        d = jobs.path(a.id)
        rep = qa.run(d)
        jobs.write(a.id, status="renderizado" if rep["ok"] else "qa_fallido"); print(qa.summary(rep))
        if not rep["ok"]: raise SystemExit(1)
    elif a.cmd == "clips":
        from . import clips
        d = jobs.path(a.id)
        if not (d / "words.json").exists(): raise SystemExit("No hay words.json. Corre primero: megamotor transcribe <id>")
        res = clips.run(d, a.min, a.max, a.n)
        for c in res["candidates"]:
            print(f"#{c['rank']} {c['start']:8.2f}-{c['end']:8.2f} ({c['duration']:.0f}s) nota {c['score']:5.2f} {c['detalle']}")
            print(f"     gancho: {c['gancho'][:100]}")
            print(f"     cierre: …{c['cierre'][-100:]}")
        if not res["candidates"]: print("Sin candidatos en ese rango de duración.")
    elif a.cmd == "clip-new":
        from . import clips
        import tempfile, pathlib
        d = jobs.path(a.id)
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp) / f"{a.id}-clip{a.rank}.mkv"
            c, words = clips.extract(d, a.rank, f)
            jid = jobs.create(f, a.name or f"{a.id}-clip{a.rank}")
        nd = jobs.path(jid)
        (nd / "words.json").write_text(json.dumps({"engine": "recorte", "language": "es", "words": words,
                                                   "text": " ".join(w["word"] for w in words)}, ensure_ascii=False, indent=2), encoding="utf-8")
        jobs.write(jid, status="transcrito", parent=a.id, parent_range=[c["start"], c["end"]])
        print(jid)
    elif a.cmd == "status":
        for j in jobs.list_all(): print(f"{j['id']:<32} {j['status']}")
    elif a.cmd == "approve":
        jobs.approve(a.id); print("aprobado")
    elif a.cmd == "publish":
        from . import publish
        if a.check:
            res = publish.check(a.id)
            for name, ok, detail in res: print(("OK   " if ok else "FALLO ") + f"{name}: {detail}")
            if not all(ok for _, ok, _ in res): raise SystemExit(1)
        else:
            print("publicado:", publish.publish_reel(a.id))
    elif a.cmd == "comments":
        from . import publish
        j = jobs.read(a.id)
        if not j.get("media_id"): raise SystemExit("Ese trabajo aún no está publicado.")
        if a.draft:
            n, pend = publish.draft_replies(a.id); print(f"{n} comentarios · {pend} respuestas por redactar en replies.json")
        else:
            for c in publish.list_comments(j["media_id"]): print(f"[{c['id']}] @{c.get('username')}: {c['text']}")
    elif a.cmd == "insights":
        from . import publish
        print(json.dumps(publish.insights(a.id), indent=2))
    elif a.cmd == "performance":
        from . import publish
        for r in publish.performance():
            print(f"{r['id']:<28} ret {r['retention']}  vistas {r['views']:<7} interacción {r['engagement']}  gancho: {r['hook'][:60]}")
    elif a.cmd == "replies":
        from . import publish
        print("enviadas:", publish.send_approved_replies(a.id))
    elif a.cmd == "ui":
        from . import ui_server
        ui_server.serve(a.port)
    elif a.cmd == "doctor":
        for t in ("ffmpeg", "ffprobe"): print(f"{t:<10}", "OK" if shutil.which(t) else "FALTA")
        for k in ("GROQ_API_KEY", "IG_ACCESS_TOKEN", "IG_USER_ID"): print(f"{k:<16}", "puesta" if env(k) else "vacía")
        print("datos en:", JOBS.parent)


if __name__ == "__main__":
    main()
