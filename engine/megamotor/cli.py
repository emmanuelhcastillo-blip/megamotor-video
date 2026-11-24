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
    s = sub.add_parser("qa", help="QA automático del reel -> qa_report.json"); s.add_argument("id")
    sub.add_parser("status", help="lista trabajos")
    s = sub.add_parser("approve", help="aprobar para publicar"); s.add_argument("id")
    s = sub.add_parser("publish", help="publicar en Instagram (solo aprobados)"); s.add_argument("id")
    s = sub.add_parser("comments", help="leer comentarios del reel publicado"); s.add_argument("id")
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
        rep = render.render(d, a.subs, not a.horizontal, a.crop_x, crf=a.crf, apply_cuts=a.apply_cuts)
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
    elif a.cmd == "status":
        for j in jobs.list_all(): print(f"{j['id']:<32} {j['status']}")
    elif a.cmd == "approve":
        jobs.approve(a.id); print("aprobado")
    elif a.cmd == "publish":
        from . import publish
        print("publicado:", publish.publish_reel(a.id))
    elif a.cmd == "comments":
        from . import publish
        j = jobs.read(a.id)
        if not j.get("media_id"): raise SystemExit("Ese trabajo aún no está publicado.")
        for c in publish.list_comments(j["media_id"]): print(f"[{c['id']}] @{c.get('username')}: {c['text']}")
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
