"""Selector de clips para videos largos.

Corta el texto en frases (words.json), arma ventanas que empiezan y terminan en frontera de frase
y las puntúa con reglas legibles:
- gancho: la primera frase engancha (pregunta, cifra, segunda persona, palabras fuertes, corta y sin aire).
- cierre: termina en frase completa, con pausa después y, mejor, con una conclusión.
- autonomía: no empieza con conector ni referencia a algo anterior ("y", "pero", "eso", "como decía").
- ritmo: poca pausa muerta, velocidad de habla normal.
Escribe clips.json con varios candidatos sin solaparse para que el dueño elija. Claude lee el texto
de cada candidato y puede reordenar; el motor solo propone.
"""
import json
import pathlib
import re

from . import cuts, media

END = re.compile(r"[.!?…]$")
CONNECTORS = {"y", "pero", "entonces", "porque", "que", "o", "ni", "pues", "además", "aunque", "sino", "también"}
ANAPHORA = {"eso", "esto", "esa", "ese", "aquello", "él", "ella", "ellos", "ellas", "lo", "la", "le", "les"}
CALLBACK = ("como decía", "como dije", "lo que te dije", "lo anterior", "antes de eso", "lo de antes")
HOOK_WORDS = {"nadie", "nunca", "siempre", "secreto", "error", "errores", "verdad", "mentira", "dinero", "gratis",
              "peor", "mejor", "nadie", "todos", "deja", "dejar", "evita", "cuidado", "problema", "clave",
              "importante", "increíble", "real", "realmente", "nunca", "jamás", "prohibido", "debes", "necesitas"}
CLOSERS = ("por eso", "así que", "en resumen", "la clave", "al final", "recuerda", "conclusión", "por lo tanto",
           "en pocas palabras", "y punto", "así de simple", "sígueme", "comenta", "guarda")


def sentences(words):
    out, cur = [], []
    for k, w in enumerate(words):
        cur.append(w)
        gap = words[k + 1]["start"] - w["end"] if k + 1 < len(words) else 9
        nxt = words[k + 1]["word"].strip() if k + 1 < len(words) else ""
        if END.search(w["word"].strip()) or gap > 1.2 or (gap > 0.5 and nxt[:1].isupper()):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [{"start": s[0]["start"], "end": s[-1]["end"], "words": s,
             "text": " ".join(w["word"].strip() for w in s)} for s in out]


def _toks(text):
    return [cuts.norm(t) for t in text.split() if cuts.norm(t)]


def score(sents, i, j, after_gap):
    """Puntúa la ventana de frases sents[i..j]. Devuelve (total, desglose)."""
    first, last = sents[i], sents[j]
    ft, lt = _toks(first["text"]), _toks(last["text"])
    low = first["text"].lower()
    hook = 0.0
    hook += 1.5 if first["text"].rstrip().endswith("?") or first["text"].lstrip().startswith("¿") else 0
    hook += 1.0 if re.search(r"\d", first["text"]) else 0
    hook += 0.8 if {"tú", "te", "tu", "ti", "usted"} & set(ft) else 0
    hook += min(1.5, 0.5 * len(HOOK_WORDS & set(ft)))
    hook += 0.7 if len(ft) <= 12 else (-0.5 if len(ft) > 25 else 0)
    auto = 0.0
    auto -= 2.0 if ft and ft[0] in CONNECTORS else 0
    auto -= 1.0 if ft and ft[0] in ANAPHORA else 0
    auto -= 1.5 if any(c in low for c in CALLBACK) else 0
    auto -= 0.5 if first["text"][:1].islower() else 0
    close = 0.0
    close += 1.0 if END.search(last["text"].rstrip()) else -1.0
    close += 0.7 if after_gap > 0.5 else (-0.7 if after_gap < 0.2 else 0)
    close += 1.0 if any(c in last["text"].lower() for c in CLOSERS) else 0
    close -= 1.0 if lt and lt[-1] in CONNECTORS else 0
    dur = last["end"] - first["start"]
    spoken = sum(w["end"] - w["start"] for s in sents[i:j + 1] for w in s["words"])
    nwords = sum(len(s["words"]) for s in sents[i:j + 1])
    rate = nwords / max(dur, 0.1)
    rhythm = 1.0 - 2.0 * max(0.0, (1 - spoken / max(dur, 0.1)) - 0.25)  # >25 % de aire penaliza
    rhythm -= 0.5 if rate < 1.6 or rate > 4.5 else 0
    parts = {"gancho": round(hook, 2), "autonomia": round(auto, 2), "cierre": round(close, 2), "ritmo": round(rhythm, 2)}
    total = 1.4 * hook + 1.2 * auto + 1.0 * close + 0.8 * rhythm
    return round(total, 2), parts


def propose(words, duration, min_s=20.0, max_s=60.0, n=5):
    sents = sentences(words)
    cands = []
    for i in range(len(sents)):
        for j in range(i, len(sents)):
            d = sents[j]["end"] - sents[i]["start"]
            if d > max_s:
                break
            if d < min_s:
                continue
            nxt = sents[j + 1]["start"] if j + 1 < len(sents) else duration
            total, parts = score(sents, i, j, nxt - sents[j]["end"])
            cands.append({"start": round(max(0.0, sents[i]["start"] - 0.15), 2),
                          "end": round(min(duration, sents[j]["end"] + min(0.4, max(0.0, nxt - sents[j]["end"]) * 0.5)), 2),
                          "score": total, "detalle": parts,
                          "gancho": sents[i]["text"][:140], "cierre": sents[j]["text"][-140:]})
    cands.sort(key=lambda c: -c["score"])
    chosen = []
    for c in cands:
        if all(min(c["end"], o["end"]) - max(c["start"], o["start"]) < 0.2 * (c["end"] - c["start"]) for o in chosen):
            chosen.append(c)
        if len(chosen) >= n:
            break
    for k, c in enumerate(chosen):
        c["rank"] = k + 1
        c["duration"] = round(c["end"] - c["start"], 2)
    return chosen


def run(job_dir, min_s=20.0, max_s=60.0, n=5):
    job_dir = pathlib.Path(job_dir)
    words = json.loads((job_dir / "words.json").read_text(encoding="utf-8"))["words"]
    dur = media.probe(next(job_dir.glob("source.*")))["duration"]
    res = {"min_s": min_s, "max_s": max_s, "candidates": propose(words, dur, min_s, max_s, n)}
    (job_dir / "clips.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


def extract(job_dir, k, dst_video):
    """Corta el candidato k (1..n) en un archivo casi sin pérdida (x264 crf 12 + audio PCM)
    y devuelve las palabras con tiempos relativos al clip."""
    job_dir = pathlib.Path(job_dir)
    c = json.loads((job_dir / "clips.json").read_text(encoding="utf-8"))["candidates"][k - 1]
    src = next(job_dir.glob("source.*"))
    media.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{c['start']:.3f}", "-i", str(src), "-t", f"{c['end'] - c['start']:.3f}",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p",
               "-c:a", "pcm_s16le", str(dst_video)])
    words = json.loads((job_dir / "words.json").read_text(encoding="utf-8"))["words"]
    sel = [dict(w, start=round(w["start"] - c["start"], 3), end=round(w["end"] - c["start"], 3))
           for w in words if w["start"] >= c["start"] and w["end"] <= c["end"] + 0.05]
    return c, sel
