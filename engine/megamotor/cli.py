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
    s = sub.add_parser("render", help="reel 9:16 con subtítulos, duración fiel al original")
    s.add_argument("id"); s.add_argument("--subs", choices=["none", "es", "es-pt"], default="es")
    s.add_argument("--horizontal", action="store_true"); s.add_argument("--crop-x", type=int); s.add_argument("--crf", type=int, default=20)
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
    elif a.cmd == "render":
        from . import render
        d = jobs.path(a.id)
        rep = render.render(d, a.subs, not a.horizontal, a.crop_x, crf=a.crf)
        jobs.write(a.id, status="renderizado"); print(json.dumps(rep, indent=2))
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
