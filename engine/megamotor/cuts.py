"""Cortes inteligentes con aprobación.

El motor PROPONE cortes a partir de words.json (silencios, muletillas, tartamudeos, tomas repetidas)
y los escribe en cuts.json con "apply": false. Por defecto no se corta nada.
Solo se aplican si el dueño aprueba ese video (`cuts <id> --approve`) y se renderiza con --apply-cuts.
Uniones con crossfade de audio de 30 ms para no pinchar la voz.
"""
import json
import pathlib
import re

XFADE = 0.03
SILENCE_GAP = 0.9     # hueco entre palabras para proponer corte
SILENCE_KEEP = 0.25   # aire que se deja a cada lado del silencio
FILLERS = {"eh", "ehh", "ehm", "em", "emm", "mm", "mmm", "ah", "ahh", "um", "uh", "hum"}
SOFT_FILLERS = {"este", "o sea", "bueno", "pues"}  # palabras reales: solo si van aisladas por pausas
TAKE_MIN = 3          # palabras repetidas para considerar toma repetida
TAKE_WINDOW = 25      # palabras máximo entre las dos tomas


def norm(w):
    return re.sub(r"[^\wáéíóúüñç]", "", w.lower())


def propose(words, duration):
    w = [dict(x, n=norm(x["word"])) for x in words]
    cuts = []

    def add(start, end, kind, text, conf):
        start, end = max(0.0, round(start, 3)), min(duration, round(end, 3))
        if end - start >= 0.12:
            cuts.append({"start": start, "end": end, "kind": kind, "text": text, "confidence": conf, "apply": False})

    # silencios (incluye el inicio y el final)
    edges = [(0.0, 0.0)] + [(x["start"], x["end"]) for x in w] + [(duration, duration)]
    for (_, a_end), (b_start, _) in zip(edges, edges[1:]):
        if b_start - a_end > SILENCE_GAP:
            keep_a = 0.0 if a_end == 0.0 else SILENCE_KEEP
            keep_b = 0.0 if b_start == duration else SILENCE_KEEP
            add(a_end + keep_a, b_start - keep_b, "silencio", f"{b_start - a_end:.1f}s", "alta")

    for i, x in enumerate(w):
        prev_end = w[i - 1]["end"] if i else 0.0
        next_start = w[i + 1]["start"] if i + 1 < len(w) else duration
        if x["n"] in FILLERS:
            add(max(prev_end, x["start"] - 0.03), min(next_start, x["end"] + 0.03), "muletilla", x["word"], "alta")
        elif x["n"] in SOFT_FILLERS and x["start"] - prev_end > 0.3 and next_start - x["end"] > 0.3:
            add(x["start"] - 0.03, x["end"] + 0.03, "muletilla", x["word"], "baja")
        # tartamudeo: misma palabra repetida o fragmento que empieza la siguiente ("pro- problema")
        if i + 1 < len(w) and x["n"]:
            nx = w[i + 1]["n"]
            if x["n"] == nx and nx not in {"no", "sí", "si", "muy"} or (len(x["n"]) <= 4 and len(nx) > len(x["n"]) and nx.startswith(x["n"]) and x["word"].rstrip().endswith("-")):
                add(x["start"], w[i + 1]["start"], "tartamudeo", f"{x['word']} {w[i + 1]['word']}", "media")

    # tomas repetidas: la misma frase de >= TAKE_MIN palabras arranca otra vez poco después -> se corta la primera
    i = 0
    while i < len(w):
        best = None
        for j in range(i + 1, min(len(w), i + TAKE_WINDOW + 1)):
            L = 0
            while j + L < len(w) and i + L < j and w[i + L]["n"] and w[i + L]["n"] == w[j + L]["n"]:
                L += 1
            if L >= TAKE_MIN and (best is None or L > best[1]):
                best = (j, L)
        if best:
            j, L = best
            add(w[i]["start"], w[j]["start"], "toma_repetida",
                " ".join(x["word"] for x in w[i:j]), "media")
            i = j
        else:
            i += 1
    return merge(cuts)


def merge(cuts):
    out = []
    for c in sorted(cuts, key=lambda c: c["start"]):
        if out and c["start"] <= out[-1]["end"]:
            o = out[-1]
            o["end"] = max(o["end"], c["end"])
            if c["kind"] not in o["kind"].split("+"):
                o["kind"] += "+" + c["kind"]
            o["text"] += " | " + c["text"]
            o["confidence"] = min(o["confidence"], c["confidence"], key=["baja", "media", "alta"].index)
        else:
            out.append(dict(c))
    return out


def keeps(cuts, duration):
    """Tramos que se conservan [(a, b)] dados los cortes aplicados."""
    segs, t = [], 0.0
    for c in merge([c for c in cuts if c.get("apply")]):
        if c["start"] > t:
            segs.append((t, c["start"]))
        t = max(t, c["end"])
    if t < duration:
        segs.append((t, duration))
    return [(round(a, 3), round(b, 3)) for a, b in segs if b - a > 0.05]


def map_time(t, segs):
    """Tiempo del original -> tiempo de salida. None si cae dentro de un corte."""
    acc = 0.0
    for a, b in segs:
        if t < a:
            return None
        if t <= b:
            return acc + t - a
        acc += b - a
    return None


def unmap_time(t, segs):
    """Tiempo de salida -> tiempo del original."""
    acc = 0.0
    for a, b in segs:
        if t <= acc + b - a:
            return a + t - acc
        acc += b - a
    return segs[-1][1] if segs else t


def map_range(r, segs):
    """Rango del original -> lista de rangos en la salida (puede partirse)."""
    out, acc = [], 0.0
    for a, b in segs:
        lo, hi = max(r[0], a), min(r[1], b)
        if hi > lo:
            out.append((round(acc + lo - a, 2), round(acc + hi - a, 2)))
        acc += b - a
    return out


def remap_words(words, segs):
    out = []
    for x in words:
        s, e = map_time(x["start"], segs), map_time(x["end"], segs)
        if s is not None and e is not None:
            out.append(dict(x, start=s, end=e))
    return out


def remap_segments(segments, segs):
    out = []
    for x in segments or []:
        rs = map_range((x["start"], x["end"]), segs)
        if rs:
            out.append(dict(x, start=rs[0][0], end=rs[-1][1]))
    return out


def filter_graph(segs, has_audio, src_name):
    """Una entrada por tramo con búsqueda precisa (-ss/-t antes de -i) y concat.
    No se usa trim sobre una sola entrada: ffmpeg encolaría los fotogramas decodificados de los tramos
    que concat aún no lee y con varios cortes se queda sin memoria.
    Devuelve (entradas, grafo, etiqueta_video, etiqueta_audio); las entradas van primero (índices 0..n-1)."""
    inputs, parts = [], []
    n = len(segs)
    for k, (a, b) in enumerate(segs):
        last = k == n - 1
        # el audio necesita XFADE s extra para que el crossfade no acorte el audio frente al video
        dur = b - a if last or not has_audio else b - a + XFADE
        inputs += ["-ss", f"{a:.3f}", "-t", f"{dur:.3f}", "-i", src_name]
        parts.append(f"[{k}:v]trim=duration={b - a:.3f},setpts=PTS-STARTPTS[v{k}]")
        if has_audio:
            parts.append(f"[{k}:a]asetpts=PTS-STARTPTS[a{k}]")
    parts.append("".join(f"[v{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0[vc]")
    alab = None
    if has_audio:
        cur = "a0"
        for k in range(1, n):
            parts.append(f"[{cur}][a{k}]acrossfade=d={XFADE}:c1=tri:c2=tri[ax{k}]")
            cur = f"ax{k}"
        alab = cur
    return inputs, ";".join(parts), "vc", alab


def load(job_dir):
    f = pathlib.Path(job_dir) / "cuts.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def save(job_dir, data):
    (pathlib.Path(job_dir) / "cuts.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
