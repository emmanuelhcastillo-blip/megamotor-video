"""Capa de motion (Remotion): titulares, cifras animadas, tipografía cinética y barridos.

plan.json -> "motion": [
  {"start": 1.2, "end": 3.4, "kind": "titular", "text": "..."},
  {"start": 5.0, "end": 7.0, "kind": "cifra", "value": 80, "suffix": "%", "label": "no ahorra"},
  {"start": 9.0, "end": 11.5, "kind": "cinetica"},          # palabras y tiempos salen de words.json
  {"start": 14.8, "end": 15.3, "kind": "barrido"}]
Tiempos del original. Cada gráfico se renderiza aparte con transparencia (solo sus fotogramas) y se guarda
en caché por contenido; ffmpeg lo superpone en el mismo pase del render.
"""
import glob
import hashlib
import json
import os
import pathlib
import re
import subprocess

from .config import ROOT

MOTION_DIR = ROOT / "motion"
KINDS = {"titular": (0.8, 4.0), "cifra": (0.8, 4.0), "cinetica": (0.8, 5.0), "barrido": (0.3, 0.8)}
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")


def validate(items, words=None):
    """Reglas: tipos conocidos, duraciones razonables, nada de emojis, textos cortos."""
    out = []
    for it in items or []:
        k = it.get("kind")
        if k not in KINDS:
            raise SystemExit(f"motion: tipo desconocido {k!r} (usa {', '.join(KINDS)})")
        d = float(it["end"]) - float(it["start"])
        lo, hi = KINDS[k]
        if not lo <= d <= hi:
            raise SystemExit(f"motion {k} en {it['start']}s dura {d:.1f}s; debe estar entre {lo} y {hi}s")
        txt = " ".join(str(it.get(f, "")) for f in ("text", "label", "prefix", "suffix"))
        if EMOJI.search(txt):
            raise SystemExit(f"motion en {it['start']}s: nada de emojis como elemento visual")
        if len(it.get("text", "")) > 60:
            raise SystemExit(f"motion en {it['start']}s: texto de más de 60 caracteres; resúmelo")
        if k == "cifra" and not isinstance(it.get("value"), (int, float)):
            raise SystemExit(f"motion cifra en {it['start']}s sin 'value' numérico")
        it = dict(it)
        if k == "cinetica" and not it.get("words") and not it.get("text"):
            sel = [w for w in words or [] if it["start"] - 0.05 <= w["start"] < it["end"]]
            if not sel:
                raise SystemExit(f"motion cinetica en {it['start']}s: no hay palabras dichas en ese tramo")
            it["words"] = [{"w": re.sub(r"[.,;:]+$", "", w["word"]), "t": round(w["start"] - it["start"], 2)} for w in sel]
        out.append(it)
    return out


SLOTS = (520, 1180)   # arriba (bajo los subtítulos ES) o abajo (sobre el PT y la interfaz)
SLOT_H = 300


def place(items, box):
    """Si la cara cae en la franja de arriba, el gráfico baja: nunca se tapa la cara."""
    if not box:
        return items
    bx, by, bs = box
    fh = bs / 2.6                       # alto aproximado de la cara dentro del cuadrado del círculo
    fy0, fy1 = by + 0.45 * bs - fh * 0.7, by + 0.45 * bs + fh * 0.7
    out = []
    for it in items:
        if it["kind"] != "barrido" and "top" not in it and "position" not in it:
            free = [y for y in SLOTS if y + SLOT_H < fy0 or y > fy1]
            it = dict(it, top=free[0] if free else SLOTS[0])
        out.append(it)
    return out


def props(it):
    p = {k: v for k, v in it.items() if k in ("kind", "text", "value", "decimals", "prefix", "suffix", "label", "words", "position", "top")}
    p["seconds"] = round(it["end"] - it["start"], 3)
    return p


def _browser():
    if os.environ.get("REMOTION_BROWSER"):
        return os.environ["REMOTION_BROWSER"]
    found = glob.glob("/opt/pw-browsers/chromium_headless_shell-*/*/chrome-headless-shell")
    return found[0] if found else None


def render_clips(job_dir, items):
    """Devuelve una ruta .mov por item, renderizando con Remotion solo los que no están en caché."""
    job_dir = pathlib.Path(job_dir)
    cache = job_dir / "motion"
    cache.mkdir(exist_ok=True)
    paths, todo = [], []
    for it in items:
        pr = props(it)
        h = hashlib.sha1(json.dumps(pr, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
        f = cache / f"{it['kind']}-{h}.mov"
        paths.append(f)
        if not f.exists():
            todo.append({"props": pr, "out": str(f)})
    if todo:
        if not (MOTION_DIR / "node_modules").exists():
            raise SystemExit("Falta la capa de motion: cd motion && npm install")
        jf = cache / "trabajos.json"
        jf.write_text(json.dumps(todo, ensure_ascii=False), encoding="utf-8")
        env = dict(os.environ)
        b = _browser()
        if b:
            env["REMOTION_BROWSER"] = b
        p = subprocess.run(["node", "render.mjs", str(jf)], cwd=MOTION_DIR, env=env, capture_output=True, text=True)
        if p.returncode != 0 or not all(pathlib.Path(t["out"]).exists() for t in todo):
            raise RuntimeError("Remotion falló:\n" + p.stderr[-1500:])
    return paths


def overlay_graph(base, items, paths, first_input):
    parts, cur = [], base
    for k, (it, _) in enumerate(zip(items, paths)):
        # yuva420p + overlay en yuv420: si no, el video entero pasa a 12 bits 4:4:4 (más lento y mide mal el QA)
        parts.append(f"[{first_input + k}:v]format=yuva420p,setpts=PTS-STARTPTS+{it['start']:.3f}/TB[mo{k}]")
        parts.append(f"[{cur}][mo{k}]overlay=eof_action=pass:format=yuv420[mv{k}]")
        cur = f"mv{k}"
    return parts, cur
