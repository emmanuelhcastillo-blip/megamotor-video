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

def _graph():
    # IG_GRAPH_URL solo para pruebas con un servidor simulado
    return env("IG_GRAPH_URL", "https://graph.facebook.com").rstrip("/")


def _ver():
    return env("IG_GRAPH_VERSION", "v23.0")


def _h():
    return {"Authorization": f"Bearer {need('IG_ACCESS_TOKEN')}"}


def _caption(plan):
    tags = " ".join(t if t.startswith("#") else f"#{t}" for t in plan.get("hashtags", []))
    return (plan["caption"].strip() + ("\n\n" + tags if tags else "")).strip()


MAX_MB, MAX_SECONDS = 300, 15 * 60  # límites de Reels por API (revisar si Meta los cambia)


def check(job_id):
    """Comprobación previa SIN publicar: archivo, aprobación, token y cupo diario. Nunca imprime el token."""
    from . import media
    out = []
    d = jobs.path(job_id)
    job = jobs.read(job_id)
    reel = d / "reel.mp4"
    out.append(("aprobado", job.get("status") == "aprobado", job.get("status")))
    if reel.exists():
        m = media.probe(reel)
        out.append(("archivo", m["size_mb"] <= MAX_MB and 3 <= m["duration"] <= MAX_SECONDS,
                    f"{m['width']}x{m['height']} {m['duration']:.1f}s {m['size_mb']} MB"))
    else:
        out.append(("archivo", False, "falta reel.mp4"))
    plan = jobs.load_plan(job_id)
    cap = _caption(plan) if plan.get("caption") else ""
    out.append(("descripcion", 0 < len(cap) <= 2200 and len(plan.get("hashtags", [])) <= 30,
                f"{len(cap)} caracteres, {len(plan.get('hashtags', []))} etiquetas"))
    if not env("IG_ACCESS_TOKEN") or not env("IG_USER_ID"):
        out.append(("claves", False, "faltan IG_ACCESS_TOKEN / IG_USER_ID en .env"))
        return out
    try:
        r = requests.get(f"{_graph()}/{_ver()}/{need('IG_USER_ID')}", headers=_h(), timeout=30,
                         params={"fields": "id,username"})
        ok = r.status_code == 200
        out.append(("token", ok, f"@{r.json().get('username')}" if ok else f"HTTP {r.status_code}: {r.text[:160]}"))
        r = requests.get(f"{_graph()}/{_ver()}/{need('IG_USER_ID')}/content_publishing_limit", headers=_h(), timeout=30,
                         params={"fields": "quota_usage,config"})
        if r.status_code == 200 and r.json().get("data"):
            q = r.json()["data"][0]
            total = (q.get("config") or {}).get("quota_total")
            out.append(("cupo", total is None or q.get("quota_usage", 0) < total, f"{q.get('quota_usage')}/{total} hoy"))
        else:
            out.append(("cupo", False, f"HTTP {r.status_code}: {r.text[:160]}"))
    except requests.RequestException as e:
        out.append(("red", False, str(e)[:160]))
    return out


def publish_reel(job_id):
    job = jobs.read(job_id)
    if job.get("status") != "aprobado":
        raise SystemExit(f"Bloqueado: el trabajo está '{job.get('status')}', no 'aprobado'. Apruébalo primero.")
    d = jobs.path(job_id)
    plan = jobs.load_plan(job_id)
    reel = d / "reel.mp4"
    uid = need("IG_USER_ID")

    # 1) contenedor con subida reanudable (no hace falta URL pública)
    r = requests.post(f"{_graph()}/{_ver()}/{uid}/media", headers=_h(), timeout=60,
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
        s = requests.get(f"{_graph()}/{_ver()}/{cid}", headers=_h(), params={"fields": "status_code"}, timeout=60).json()
        code = s.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram rechazó el video: {s}")
        time.sleep(float(env("IG_POLL_SECONDS", "5")))
    else:
        raise RuntimeError("Instagram no terminó de procesar a tiempo.")

    # 4) publicar
    p = requests.post(f"{_graph()}/{_ver()}/{uid}/media_publish", headers=_h(), data={"creation_id": cid}, timeout=60)
    p.raise_for_status()
    media_id = p.json()["id"]
    jobs.write(job_id, status="publicado", media_id=media_id)
    return media_id


def list_comments(media_id):
    r = requests.get(f"{_graph()}/{_ver()}/{media_id}/comments", headers=_h(), timeout=60,
                     params={"fields": "id,text,username,timestamp", "limit": 50})
    r.raise_for_status()
    return r.json().get("data", [])


def draft_replies(job_id):
    """Guarda los comentarios en comments.json y añade a replies.json una entrada vacía por comentario
    nuevo (text vacío, approved false). Claude redacta; el dueño aprueba. No envía nada."""
    j = jobs.read(job_id)
    if not j.get("media_id"):
        raise SystemExit("Ese trabajo aún no está publicado.")
    d = jobs.path(job_id)
    comments = list_comments(j["media_id"])
    (d / "comments.json").write_text(json.dumps(comments, ensure_ascii=False, indent=2), encoding="utf-8")
    f = d / "replies.json"
    items = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    known = {it["comment_id"] for it in items}
    for c in comments:
        if c["id"] not in known:
            items.append({"comment_id": c["id"], "username": c.get("username"), "comment": c.get("text", ""),
                          "text": "", "approved": False})
    f.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(comments), sum(1 for it in items if not it["text"])


REEL_METRICS = ("views", "reach", "likes", "comments", "shares", "saved", "total_interactions",
                "ig_reels_avg_watch_time", "ig_reels_video_view_total_time")


def insights(job_id):
    """Métricas del reel publicado -> insights.json. Pide cada métrica aparte: si Meta retira una, el resto sigue."""
    j = jobs.read(job_id)
    if not j.get("media_id"):
        raise SystemExit("Ese trabajo aún no está publicado.")
    out, errors = {}, {}
    for m in REEL_METRICS:
        r = requests.get(f"{_graph()}/{_ver()}/{j['media_id']}/insights", headers=_h(), timeout=60,
                         params={"metric": m})
        if r.status_code == 200 and r.json().get("data"):
            vals = r.json()["data"][0].get("values") or [{}]
            out[m] = vals[0].get("value")
        else:
            errors[m] = r.status_code
    out["_fetched"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    if errors:
        out["_errors"] = errors
    (jobs.path(job_id) / "insights.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def performance():
    """Cruza gancho, duración y métricas de todos los reels publicados para afinar la fórmula de gancho.
    Retención aproximada = tiempo medio de visualización / duración del reel."""
    rows = []
    for j in jobs.list_all():
        d = jobs.path(j["id"])
        fi, fr = d / "insights.json", d / "render_report.json"
        if not fi.exists():
            continue
        ins = json.loads(fi.read_text(encoding="utf-8"))
        dur = json.loads(fr.read_text(encoding="utf-8")).get("output_seconds") if fr.exists() else None
        plan = jobs.load_plan(j["id"])
        awt = ins.get("ig_reels_avg_watch_time")
        awt_s = awt / 1000 if isinstance(awt, (int, float)) and awt > 300 else awt  # Meta lo da en ms
        ret = round(awt_s / dur, 2) if awt_s and dur else None
        views = ins.get("views") or 0
        inter = sum(ins.get(k) or 0 for k in ("likes", "comments", "shares", "saved"))
        rows.append({"id": j["id"], "hook": plan.get("hook", ""), "duration": dur, "views": views,
                     "retention": ret, "engagement": round(inter / views, 3) if views else None,
                     "shares": ins.get("shares"), "saved": ins.get("saved")})
    rows.sort(key=lambda r: (r["retention"] or 0, r["views"]), reverse=True)
    return rows


def send_approved_replies(job_id):
    """Envía solo respuestas con "approved": true en replies.json. Formato:
    [{"comment_id":"...","text":"...","approved":false}]. Nunca envía un texto vacío."""
    f = jobs.path(job_id) / "replies.json"
    items = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    sent = 0
    for it in items:
        if it.get("approved") and not it.get("sent") and it.get("text", "").strip():
            r = requests.post(f"{_graph()}/{_ver()}/{it['comment_id']}/replies", headers=_h(),
                              data={"message": it["text"]}, timeout=60)
            r.raise_for_status()
            it["sent"] = True
            sent += 1
    f.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return sent
