"""Efectos de encuadre pedidos en plan.json (tiempos del original; se llevan a la salida si hay cortes).

- "zooms": [{"start": 3.2, "end": 5.0, "scale": 1.12}]  zoom de énfasis, entra y sale suave (0,35 s).
- "pip":   [{"start": 8.0, "end": 11.0, "image": "img/foto.jpg", "circle": true}]
  la imagen ocupa la pantalla (paneo lento) y la persona sigue hablando en un círculo; "circle": false = sin
  círculo (máx. 3,5 s). Imágenes reales, sin repetir.
- "dynamic": true   cámara con ritmo de reel: corte de zoom en cada corte real y acercamiento suave en planos largos.
- "teaser": {"start": 119.5, "end": 125.0, "text": "opcional"} o {"parts": [[a, b], [c, d]], ...}  la frase más fuerte se repite al principio como gancho
  (se añade, no se quita nada); entra con barrido y whoosh si la capa de motion está instalada.
- "color": "natural" | "pop" | {"contrast":1.1,"saturation":1.3,"gamma":0.98,"warmth":0.03,"vignette":true}
  corrección de color sobre la persona (no sobre las imágenes del pip ni los gráficos).
Pocos efectos y sin superponer: se rechazan zooms o pip que se pisen entre sí.
"""
import pathlib

from . import cuts, media

RAMP = 0.35
PIP_D = 440                 # diámetro del círculo
PIP_X, PIP_Y = 580, 1010    # esquina sup. izq.: encima del PT y lejos de la interfaz de Instagram
MAX_IMG = 3.5               # s de imagen a pantalla completa sin la persona
MAX_IMG_CIRCLE = 6.0        # con la persona hablando en el círculo se permite algo más
PAN = 1.08                  # la imagen se escala un 8 % extra para el paneo lento
FACE_BOX = (180, 260, 720)  # x, y, lado del 9:16 que va al círculo si no hay datos de cara (reframe.face_box)


def _even_up(v):
    v = int(-(-v // 1))
    return v + (v % 2)


def scaled_size(w, h, ow=1080, oh=1920):
    sc = max(ow / w, oh / h)
    return max(ow, _even_up(w * sc)), max(oh, _even_up(h * sc))


def _to_out(items, segs, offset=0.0):
    """Tiempos del original -> salida (segs = tramos del cuerpo; offset = duración del teaser)."""
    out = []
    for it in items or []:
        rs = cuts.map_range((float(it["start"]), float(it["end"])), segs) if segs else [(float(it["start"]), float(it["end"]))]
        if rs and rs[-1][1] - rs[0][0] > 0.3:
            out.append(dict(it, start=round(rs[0][0] + offset, 3), end=round(rs[-1][1] + offset, 3)))
    no_overlap(out)
    return out


def no_overlap(items):
    items = sorted(items, key=lambda x: x["start"])
    for a, b in zip(items, items[1:]):
        if b["start"] < a["end"]:
            raise SystemExit(f"Efectos superpuestos en {b['start']:.1f}s: pocos efectos y sin superponer.")


def zoom_expr(zooms):
    """Factor de zoom en función de t (expresión ffmpeg). Tipos de tramo:
    - énfasis {"start","end","scale"[, "ramp"]}: entra y sale suave (ramp s; 0 = seco).
    - cámara {"start","end","from","to"}: del factor from al to en línea recta (empuje lento)."""
    terms = []
    for z in zooms:
        a, b = z["start"], z["end"]
        if "from" in z:
            f0, f1 = float(z["from"]), float(z["to"])
            terms.append(f"gte(t\\,{a:.3f})*lt(t\\,{b:.3f})*({f0 - 1:.4f}+{f1 - f0:.4f}*(t-{a:.3f})/{max(b - a, 0.01):.3f})")
            continue
        s = float(z.get("scale", 1.12))
        if not 1.0 < s <= 1.5:
            raise SystemExit(f"zoom scale {s} fuera de rango (1.0-1.5]")
        r = float(z.get("ramp", RAMP))
        if r <= 0:
            terms.append(f"{s - 1:.3f}*gte(t\\,{a:.3f})*lt(t\\,{b:.3f})")
        else:
            terms.append(f"{s - 1:.3f}*clip(min((t-{a:.3f})/{r}\\,({b:.3f}-t)/{r})\\,0\\,1)")
    return "1+" + "+".join(terms) if terms else "1"


def dynamic_track(joins, total, explicit, level=1.10, long_shot=7.0, push=1.06, min_len=0.6):
    """Cámara con ritmo de reel, solo con intención:
    - en cada corte real (uniones del montaje y cortes de la edición previa) alterna plano abierto / cerrado
      con un corte de zoom seco: disimula el salto de imagen;
    - dentro de un plano el encuadre no se mueve (un empuje continuo escala 2 px por fotograma y tiembla);
    - en planos de más de `long_shot` s, un acercamiento suave a mitad de plano (entra y sale en 0,8 s).
    Respeta los zooms de énfasis explícitos. Todo en tiempo de salida."""
    marks = sorted({0.0, round(total, 3), *[round(j, 3) for j in joins if 0.3 < j < total - 0.3]})
    busy = sorted((z["start"], z["end"]) for z in explicit)
    out, lv = [], 0
    for a, b in zip(marks, marks[1:]):
        if b - a < 0.25:
            continue
        pieces, cur = [], a
        for za, zb in busy:
            if zb <= cur or za >= b:
                continue
            if za > cur:
                pieces.append((cur, za))
            cur = max(cur, zb)
        if cur < b:
            pieces.append((cur, b))
        base = level if lv % 2 else 1.0
        for pa, pb in pieces:
            if pb - pa >= min_len:
                out.append({"start": round(pa, 3), "end": round(pb, 3), "from": base, "to": base})
                if pb - pa >= long_shot:
                    mid = (pa + pb) / 2
                    out.append({"start": round(mid - 1.8, 3), "end": round(mid + 1.8, 3), "scale": push, "ramp": 0.8})
        lv += 1
    return out


def pip_images(job_dir, pips):
    """Valida las imágenes: dentro del trabajo, sin repetir, y que ninguna se quede demasiado."""
    import hashlib
    out, seen = [], {}
    root = pathlib.Path(job_dir).resolve()
    for p in pips:
        img = (root / p["image"]).resolve()
        if root not in img.parents or not img.is_file():
            raise SystemExit(f"Imagen de pip no válida (debe estar dentro del trabajo): {p['image']}")
        h = hashlib.sha1(img.read_bytes()).hexdigest()
        if h in seen:
            raise SystemExit(f"Imagen repetida: {p['image']} ya se usó como {seen[h]}. Variedad, sin repetir.")
        seen[h] = p["image"]
        d = p["end"] - p["start"]
        lim = MAX_IMG_CIRCLE if p.get("circle", True) else MAX_IMG
        if d > lim:
            raise SystemExit(f"La imagen {p['image']} dura {d:.1f}s; máximo {lim}s"
                             + ("" if p.get("circle", True) else " a pantalla completa sin la persona"))
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
    """Grafo de superposición. Entradas desde first_input: máscara, aro y luego una imagen por pip.
    La imagen hace un paneo lento (alterna dirección) para que nunca quede estática.
    Memoria: nada se recorta con trim sobre una rama de la imagen principal (obligaría a encolar
    fotogramas hasta que empieza el pip). El círculo va al mismo paso que el video y se activa con enable;
    las imágenes y la máscara se repiten dentro del grafo (loop) bajo demanda."""
    if not pips:
        return [], base
    mi, ri = first_input, first_input + 1
    bx, by, bs = box or FACE_BOX
    circ = [p for p in pips if p.get("circle", True)]
    parts = []
    cur = base
    if circ:
        parts.append(f"[{base}]split=2[pb0][pf]")
        parts.append(f"[pf]crop={bs}:{bs}:{bx}:{by},scale={PIP_D}:{PIP_D},format=yuva420p[pc]")
        parts.append(f"[{mi}:v]format=gray,loop=loop=-1:size=1,fps={fps}[pm]")
        parts.append(f"[{ri}:v]format=rgba,loop=loop=-1:size=1,fps={fps}[pr]")
        parts.append("[pc][pm]alphamerge[pa]")
        cur = "pb0"
    else:
        parts += [f"[{mi}:v]nullsink", f"[{ri}:v]nullsink"]
    for k, p in enumerate(pips):
        a, b = p["start"], p["end"]
        d = b - a
        ii = first_input + 2 + k
        pan = f"(iw-1080)*t/{d:.3f}" if k % 2 == 0 else f"(iw-1080)*(1-t/{d:.3f})"
        # una sola imagen (sin -loop en la entrada): se escala una vez y se repite bajo demanda
        parts.append(f"[{ii}:v]scale={int(1080 * PAN)}:{int(1920 * PAN)}:force_original_aspect_ratio=increase,setsar=1,"
                     f"loop=loop=-1:size=1,fps={fps},trim=duration={d:.3f},setpts=PTS-STARTPTS,"
                     f"crop=1080:1920:x='{pan}':y='(ih-1920)/2',setpts=PTS+{a:.3f}/TB[pi{k}]")
        parts.append(f"[{cur}][pi{k}]overlay=eof_action=pass[po{k}]")
        cur = f"po{k}"
    if circ:
        on = "+".join(f"between(t,{p['start']:.3f},{p['end']:.3f})" for p in circ)
        parts.append(f"[{cur}][pr]overlay={PIP_X - 8}:{PIP_Y - 8}:enable='{on}':shortest=1[pring]")
        parts.append(f"[pring][pa]overlay={PIP_X}:{PIP_Y}:enable='{on}':shortest=1[pout]")
        cur = "pout"
    return parts, cur


COLOR_PRESETS = {
    "natural": {"contrast": 1.06, "saturation": 1.2, "gamma": 1.0, "warmth": 0.0, "vignette": False},
    # para material plano o lavado: más contraste y color, sombras algo frías y altas cálidas, viñeta suave
    "pop": {"contrast": 1.12, "saturation": 1.45, "gamma": 1.02, "warmth": 0.03, "vignette": True},
}


def grade(spec):
    """Cadena de filtros de color o "" si no se pide."""
    if not spec:
        return ""
    c = dict(COLOR_PRESETS[spec]) if isinstance(spec, str) else dict(COLOR_PRESETS["natural"], **spec)
    if not (0.8 <= c["contrast"] <= 1.4 and 0.5 <= c["saturation"] <= 2.0 and 0.8 <= c["gamma"] <= 1.2):
        raise SystemExit(f"color fuera de rango: {c}")
    w = float(c.get("warmth", 0))
    # calidez con gamma por canal dentro de eq (tabla, barato); colorbalance costaba ~0,8 s por segundo de video
    eq = f"eq=contrast={c['contrast']}:saturation={c['saturation']}:gamma={c['gamma']}"
    if w:
        eq += f":gamma_r={1 + w:.3f}:gamma_b={1 - w:.3f}"
    f = [eq]
    if c.get("vignette"):
        f.append("vignette=PI/9")  # suave: PI/5 oscurecía un 24 % y el QA lo rechazaba
    return ",".join(f)
