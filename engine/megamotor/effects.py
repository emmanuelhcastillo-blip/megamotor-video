"""Efectos de encuadre pedidos en plan.json (tiempos del original; se llevan a la salida si hay cortes).

- "zooms": [{"start": 3.2, "end": 5.0, "scale": 1.12}]  zoom de énfasis, entra y sale suave (0,35 s).
- "pip":   [{"start": 8.0, "end": 11.0, "image": "img/foto.jpg"}]
  la imagen ocupa la pantalla y la persona sigue hablando en un círculo (no se le quita la voz ni la cara).
Pocos efectos y sin superponer: se rechazan zooms o pip que se pisen entre sí.
"""
import pathlib

from . import cuts, media

RAMP = 0.35
PIP_D = 440                 # diámetro del círculo
PIP_X, PIP_Y = 580, 1010    # esquina sup. izq.: encima del PT y lejos de la interfaz de Instagram
FACE_BOX = (180, 260, 720)  # x, y, lado del 9:16 que va al círculo si no hay datos de cara (reframe.face_box)


def _even_up(v):
    v = int(-(-v // 1))
    return v + (v % 2)


def scaled_size(w, h, ow=1080, oh=1920):
    sc = max(ow / w, oh / h)
    return max(ow, _even_up(w * sc)), max(oh, _even_up(h * sc))


def _to_out(items, segs):
    out = []
    for it in items or []:
        rs = cuts.map_range((float(it["start"]), float(it["end"])), segs) if segs else [(float(it["start"]), float(it["end"]))]
        if rs and rs[-1][1] - rs[0][0] > 0.3:
            out.append(dict(it, start=rs[0][0], end=rs[-1][1]))
    no_overlap(out)
    return out


def no_overlap(items):
    items = sorted(items, key=lambda x: x["start"])
    for a, b in zip(items, items[1:]):
        if b["start"] < a["end"]:
            raise SystemExit(f"Efectos superpuestos en {b['start']:.1f}s: pocos efectos y sin superponer.")


def zoom_expr(zooms):
    """Factor de zoom en función de t (expresión ffmpeg)."""
    terms = []
    for z in zooms:
        s = float(z.get("scale", 1.12))
        if not 1.0 < s <= 1.5:
            raise SystemExit(f"zoom scale {s} fuera de rango (1.0-1.5]")
        a, b = z["start"], z["end"]
        terms.append(f"{s - 1:.3f}*clip(min((t-{a:.3f})/{RAMP}\\,({b:.3f}-t)/{RAMP})\\,0\\,1)")
    return "1+" + "+".join(terms) if terms else "1"


def pip_images(job_dir, pips):
    out = []
    root = pathlib.Path(job_dir).resolve()
    for p in pips:
        img = (root / p["image"]).resolve()
        if root not in img.parents or not img.is_file():
            raise SystemExit(f"Imagen de pip no válida (debe estar dentro del trabajo): {p['image']}")
        out.append(img)
    return out


def make_masks(job_dir):
    """Máscara circular y aro blanco, una sola vez por trabajo."""
    job_dir = pathlib.Path(job_dir)
    r = PIP_D / 2
    m, ring = job_dir / "pip_mask.png", job_dir / "pip_ring.png"
    if not m.exists():
        media.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=black:s={PIP_D}x{PIP_D}", "-frames:v", "1",
                    "-vf", f"format=gray,geq=lum='255*lte(hypot(X-{r - 0.5}\\,Y-{r - 0.5})\\,{r - 1})'", str(m)])
    if not ring.exists():
        R = r + 8
        media.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=white:s={2 * R:.0f}x{2 * R:.0f}", "-frames:v", "1",
                    "-vf", f"format=rgba,geq=r=255:g=255:b=255:a='255*lte(hypot(X-{R - 0.5}\\,Y-{R - 0.5})\\,{R - 1})'", str(ring)])
    return m, ring


def pip_graph(base, pips, first_input, fps, box=None):
    """Grafo de superposición. Entradas desde first_input: máscara, aro y luego una imagen por pip."""
    if not pips:
        return [], base
    mi, ri = first_input, first_input + 1
    bx, by, bs = box or FACE_BOX
    parts = [f"[{base}]split={len(pips) + 1}[pb0]" + "".join(f"[pf{k}]" for k in range(len(pips))),
             f"[{mi}:v]format=gray,split={len(pips)}" + "".join(f"[pm{k}]" for k in range(len(pips))),
             f"[{ri}:v]format=rgba,split={len(pips)}" + "".join(f"[pr{k}]" for k in range(len(pips)))]
    cur = "pb0"
    for k, p in enumerate(pips):
        a, b = p["start"], p["end"]
        ii = first_input + 2 + k
        shift = f"setpts=PTS-STARTPTS+{a:.3f}/TB"
        parts.append(f"[{ii}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,"
                     f"fps={fps},trim=duration={b - a:.3f},{shift}[pi{k}]")
        parts.append(f"[pf{k}]trim={a:.3f}:{b:.3f},crop={bs}:{bs}:{bx}:{by},scale={PIP_D}:{PIP_D},format=rgba,{shift}[pc{k}]")
        parts.append(f"[pm{k}]loop=-1:1,trim=duration={b - a:.3f},fps={fps},{shift}[pmk{k}]")
        parts.append(f"[pr{k}]loop=-1:1,trim=duration={b - a:.3f},fps={fps},{shift}[prk{k}]")
        parts.append(f"[pc{k}][pmk{k}]alphamerge[pa{k}]")
        parts.append(f"[{cur}][pi{k}]overlay=eof_action=pass[po{k}a]")
        parts.append(f"[po{k}a][prk{k}]overlay={PIP_X - 8}:{PIP_Y - 8}:eof_action=pass[po{k}b]")
        parts.append(f"[po{k}b][pa{k}]overlay={PIP_X}:{PIP_Y}:eof_action=pass[po{k}]")
        cur = f"po{k}"
    return parts, cur
