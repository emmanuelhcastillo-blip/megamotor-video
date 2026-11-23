"""Interfaz local: revisar reels, editar descripción/etiquetas, aprobar y publicar.
Solo escucha en 127.0.0.1. Sin dependencias externas."""
import json
import pathlib
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import jobs

STATIC = pathlib.Path(__file__).parent / "static"
FILES = {"reel.mp4": "video/mp4", "cover.jpg": "image/jpeg", "source.mp4": "video/mp4"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            b = (STATIC / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path == "/api/jobs":
            self._json(jobs.list_all())
        elif (m := re.match(r"^/api/job/([a-z0-9_-]+)$", self.path)):
            try:
                self._json({"job": jobs.read(m[1]), "plan": jobs.load_plan(m[1])})
            except SystemExit as e:
                self._json({"error": str(e)}, 404)
        elif (m := re.match(r"^/media/([a-z0-9_-]+)/([a-z0-9_.]+)$", self.path)) and m[2] in FILES:
            self._file(m[1], m[2])
        else:
            self.send_error(404)

    def _file(self, jid, name):
        try:
            f = jobs.path(jid) / name
        except SystemExit:
            return self.send_error(404)
        if not f.exists():
            return self.send_error(404)
        size = f.stat().st_size
        start, end, code = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng and (m := re.match(r"bytes=(\d*)-(\d*)", rng)):
            if m[1]:
                start = int(m[1])
            if m[2]:
                end = min(int(m[2]), size - 1)
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", FILES[name])
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(f, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = fh.read(min(1 << 20, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def do_POST(self):
        m = re.match(r"^/api/job/([a-z0-9_-]+)/(plan|approve|publish)$", self.path)
        if not m:
            return self.send_error(404)
        jid, action = m[1], m[2]
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        try:
            if action == "plan":
                plan = jobs.load_plan(jid)
                for k in ("caption", "hashtags", "hook"):
                    if k in body:
                        plan[k] = body[k]
                jobs.save_plan(jid, plan)
                self._json({"ok": True})
            elif action == "approve":
                self._json({"ok": True, "job": jobs.approve(jid)})
            else:
                from . import publish
                self._json({"ok": True, "media_id": publish.publish_reel(jid)})
        except SystemExit as e:
            self._json({"error": str(e)}, 400)
        except Exception as e:  # noqa
            self._json({"error": str(e)[:500]}, 500)


def serve(port=8765):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"Megamotor UI en http://127.0.0.1:{port}  (Ctrl+C para salir)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
