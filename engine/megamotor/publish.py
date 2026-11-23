"""Publicar reels y responder comentarios por la API oficial de Instagram (Graph API).

SIN PROBAR contra Meta todavía: se valida en la primera publicación real.
Puerta dura: nada sale si job.json no dice "aprobado" (o si el comentario no está aprobado).
"""
import json
import os
import time

import requests

from . import jobs
from .config import need, env

GRAPH = "https://graph.facebook.com"


def _ver():
    return env("IG_GRAPH_VERSION", "v23.0")


def _h():
    return {"Authorization": f"Bearer {need('IG_ACCESS_TOKEN')}"}


def _caption(plan):
    tags = " ".join(t if t.startswith("#") else f"#{t}" for t in plan.get("hashtags", []))
    return (plan["caption"].strip() + ("\n\n" + tags if tags else "")).strip()


def publish_reel(job_id):
    job = jobs.read(job_id)
    if job.get("status") != "aprobado":
        raise SystemExit(f"Bloqueado: el trabajo está '{job.get('status')}', no 'aprobado'. Apruébalo primero.")
    d = jobs.path(job_id)
    plan = jobs.load_plan(job_id)
    reel = d / "reel.mp4"
    uid = need("IG_USER_ID")

    # 1) contenedor con subida reanudable (no hace falta URL pública)
    r = requests.post(f"{GRAPH}/{_ver()}/{uid}/media", headers=_h(), timeout=60,
                      data={"media_type": "REELS", "upload_type": "resumable",
                            "caption": _caption(plan), "share_to_feed": "true"})
    r.raise_for_status()
    j = r.json()
    cid = j["id"]
    uri = j.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{_ver()}/{cid}"

    # 2) subir bytes
    size = os.path.getsize(reel)
    with open(reel, "rb") as f:
        up = requests.post(uri, headers={"Authorization": f"OAuth {need('IG_ACCESS_TOKEN')}",
                                         "offset": "0", "file_size": str(size)}, data=f, timeout=900)
    up.raise_for_status()

    # 3) esperar a que Instagram procese
    for _ in range(60):
        s = requests.get(f"{GRAPH}/{_ver()}/{cid}", headers=_h(), params={"fields": "status_code"}, timeout=60).json()
        code = s.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram rechazó el video: {s}")
        time.sleep(5)
    else:
        raise RuntimeError("Instagram no terminó de procesar a tiempo.")

    # 4) publicar
    p = requests.post(f"{GRAPH}/{_ver()}/{uid}/media_publish", headers=_h(), data={"creation_id": cid}, timeout=60)
    p.raise_for_status()
    media_id = p.json()["id"]
    jobs.write(job_id, status="publicado", media_id=media_id)
    return media_id


def list_comments(media_id):
    r = requests.get(f"{GRAPH}/{_ver()}/{media_id}/comments", headers=_h(), timeout=60,
                     params={"fields": "id,text,username,timestamp", "limit": 50})
    r.raise_for_status()
    return r.json().get("data", [])


def send_approved_replies(job_id):
    """Envía solo respuestas con "approved": true en replies.json. Formato:
    [{"comment_id":"...","text":"...","approved":false}]"""
    f = jobs.path(job_id) / "replies.json"
    items = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    sent = 0
    for it in items:
        if it.get("approved") and not it.get("sent"):
            r = requests.post(f"{GRAPH}/{_ver()}/{it['comment_id']}/replies", headers=_h(),
                              data={"message": it["text"]}, timeout=60)
            r.raise_for_status()
            it["sent"] = True
            sent += 1
    f.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return sent
