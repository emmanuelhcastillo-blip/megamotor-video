"""Rutas y variables de entorno. Lee .env en la raíz del repo si existe."""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = pathlib.Path(os.environ.get("MEGAMOTOR_DATA", ROOT / "data"))
JOBS = DATA / "jobs"


def _load_dotenv():
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def env(key, default=None):
    return os.environ.get(key, default)


def need(key):
    v = env(key)
    if not v:
        raise SystemExit(f"Falta {key}. Cópialo en .env (mira .env.example y docs/APIS-GRATIS.md).")
    return v
