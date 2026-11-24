"""Subtítulos ASS. Karaoke palabra por palabra en español (arriba) y portugués (abajo) opcional.

El portugués lo escribe Claude en plan.json -> "pt_segments": [{"start":0.0,"end":2.4,"text":"..."}]
"""
import re

PUNCT_BREAK = re.compile(r"[.!?;:]$")


def _t(sec):
    cs = int(round(sec * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(txt):
    return txt.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def group_words(words, max_words=3, max_gap=0.55, max_chars=18):
    """Grupos cortos para leer en móvil. max_chars: a 84 px en mayúsculas caben ~18 caracteres en 940 px
    (1080 menos márgenes); con WrapStyle 2 no hay salto de línea, así que el límite evita que se salga."""
    groups, cur = [], []
    for w in words:
        chars = sum(len(x["word"]) + 1 for x in cur) + len(w["word"])
        if cur and (len(cur) >= max_words or chars > max_chars or w["start"] - cur[-1]["end"] > max_gap
                    or PUNCT_BREAK.search(cur[-1]["word"])):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def build_ass(words, pt_segments=None, width=1080, height=1920, font="DejaVu Sans", size=84):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ES,{font},{size},&H0000E5FF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,6,2,8,70,70,300,1
Style: PT,{font},{int(size*0.7)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,5,2,2,70,70,420,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for g in group_words(words):
        start, end = g[0]["start"], g[-1]["end"] + 0.05
        parts = []
        for w in g:
            dur = max(1, int(round((w["end"] - w["start"]) * 100)))
            parts.append(f"{{\\k{dur}}}{_esc(w['word'].upper())}")
        lines.append(f"Dialogue: 0,{_t(start)},{_t(end)},ES,,0,0,0,,{' '.join(parts)}")
    for s in pt_segments or []:
        lines.append(f"Dialogue: 0,{_t(s['start'])},{_t(s['end'])},PT,,0,0,0,,{_esc(s['text'])}")
    return head + "\n".join(lines) + "\n"
