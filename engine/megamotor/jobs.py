"""Trabajos: una carpeta por video en data/jobs/<id>/ con job.json de estado.

Estados: nuevo -> transcrito -> renderizado (o qa_fallido) -> aprobado -> publicado
"""
import datetime
import json
import re
import shutil

from .config import JOBS

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,60}$")


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:50] or "video"


def path(job_id):
    if not ID_RE.match(job_id):
        raise SystemExit(f"id inválido: {job_id}")
    p = JOBS / job_id
    if not p.exists():
        raise SystemExit(f"no existe el trabajo {job_id}")
    return p


def read(job_id):
    return json.loads((path(job_id) / "job.json").read_text(encoding="utf-8"))


def write(job_id, **changes):
    j = read(job_id)
    j.update(changes)
    j["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    (path(job_id) / "job.json").write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
    return j


def create(src, name=None):
    import pathlib
    src = pathlib.Path(src)
    jid = slug(name or src.stem)
    base, n = jid, 2
    while (JOBS / jid).exists():
        jid = f"{base}-{n}"
        n += 1
    d = JOBS / jid
    d.mkdir(parents=True)
    shutil.copy2(src, d / f"source{src.suffix.lower()}")
    now = datetime.datetime.now().isoformat(timespec="seconds")
    (d / "job.json").write_text(json.dumps({"id": jid, "status": "nuevo", "created": now, "updated": now,
                                            "original_name": src.name}, ensure_ascii=False, indent=2), encoding="utf-8")
    return jid


def list_all():
    if not JOBS.exists():
        return []
    out = []
    for d in sorted(JOBS.iterdir(), reverse=True):
        f = d / "job.json"
        if f.exists():
            j = json.loads(f.read_text(encoding="utf-8"))
            j["has_reel"] = (d / "reel.mp4").exists()
            j["has_cover"] = (d / "cover.jpg").exists()
            out.append(j)
    return out


def load_plan(job_id):
    f = path(job_id) / "plan.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def save_plan(job_id, plan):
    (path(job_id) / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")


def approve(job_id):
    plan = load_plan(job_id)
    if not plan.get("caption"):
        raise SystemExit("Falta 'caption' en plan.json: no se puede aprobar sin descripción.")
    if not (path(job_id) / "reel.mp4").exists():
        raise SystemExit("Falta reel.mp4: renderiza antes de aprobar.")
    qa_file = path(job_id) / "qa_report.json"
    if not qa_file.exists() or not json.loads(qa_file.read_text(encoding="utf-8")).get("ok"):
        raise SystemExit("QA en rojo o sin correr (megamotor qa <id>): no se puede aprobar.")
    return write(job_id, status="aprobado", approved_at=datetime.datetime.now().isoformat(timespec="seconds"))
