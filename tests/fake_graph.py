"""Servidor Graph API simulado para probar publish.py sin tocar Meta. Uso: python3 fake_graph.py PUERTO LOG"""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT, LOG = int(sys.argv[1]), sys.argv[2]
polls = {"n": 0}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _log(self, body=b""):
        auth = self.headers.get("Authorization", "")
        with open(LOG, "a") as f:
            f.write(json.dumps({"m": self.command, "p": self.path, "auth_ok": auth.endswith("tok-prueba"),
                                "len": len(body)}) + "\n")

    def do_GET(self):
        self._log()
        p = self.path
        if re.search(r"/v\d+\.\d+/c1\?", p):
            polls["n"] += 1
            return self._send({"status_code": "FINISHED" if polls["n"] > 1 else "IN_PROGRESS"})
        if "/content_publishing_limit" in p:
            return self._send({"data": [{"quota_usage": 3, "config": {"quota_total": 50}}]})
        if "/m1/comments" in p:
            return self._send({"data": [{"id": "k1", "text": "¿Y si gano poco?", "username": "ana"},
                                        {"id": "k2", "text": "Gracias!", "username": "luis"}]})
        if "/m1/insights" in p:
            m = re.search(r"metric=(\w+)", p).group(1)
            if m == "ig_reels_video_view_total_time":
                return self._send({"error": {"message": "retirada"}}, 400)
            val = {"views": 1000, "ig_reels_avg_watch_time": 6400, "likes": 50, "shares": 7, "saved": 9}.get(m, 3)
            return self._send({"data": [{"name": m, "values": [{"value": val}]}]})
        if re.search(r"/v\d+\.\d+/17840\?", p):
            return self._send({"id": "17840", "username": "cuenta_prueba"})
        return self._send({"error": "ruta"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        self._log(body)
        p = self.path
        if p.endswith("/17840/media"):
            return self._send({"id": "c1", "uri": f"http://127.0.0.1:{PORT}/upload/c1"})
        if p == "/upload/c1":
            ok = self.headers.get("Authorization") == "OAuth tok-prueba" and self.headers.get("file_size") == str(n)
            return self._send({"success": ok}, 200 if ok else 400)
        if p.endswith("/17840/media_publish"):
            return self._send({"id": "m1"})
        if re.search(r"/k\d+/replies$", p):
            return self._send({"id": "r-" + p.split("/")[-2]})
        return self._send({"error": "ruta"}, 404)


HTTPServer(("127.0.0.1", PORT), H).serve_forever()
