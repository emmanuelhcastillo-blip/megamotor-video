"""Pruebas de cuts.py sin ffmpeg: propuestas y mapeo de tiempos."""
from megamotor import cuts

W = lambda t, s, e: {"word": t, "start": s, "end": e}
words = [W("Hola", 0.5, 0.8), W("eh", 1.0, 1.3), W("hoy", 1.4, 1.6), W("hoy", 1.7, 1.9),
         W("vamos", 2.0, 2.3), W("a", 2.3, 2.4), W("ver", 2.4, 2.6),
         W("hoy", 2.8, 3.0), W("vamos", 3.0, 3.3), W("a", 3.3, 3.4), W("ver", 3.4, 3.6), W("algo.", 3.6, 4.0),
         W("Fin", 6.0, 6.4)]
p = cuts.propose(words, 7.0)
kinds = {k for c in p for k in c["kind"].split("+")}
assert {"silencio", "muletilla", "tartamudeo", "toma_repetida"} <= kinds, p
assert not any(c["apply"] for c in p), "por defecto no se corta nada"
sil = [c for c in p if c["kind"] == "silencio" and c["start"] > 4]
assert sil and abs(sil[0]["start"] - 4.25) < 1e-6 and abs(sil[0]["end"] - 5.75) < 1e-6, sil
# sin cortes aplicados el mapa es la identidad
assert cuts.keeps(p, 7.0) == [(0.0, 7.0)]
for c in p: c["apply"] = True
segs = cuts.keeps(p, 7.0)
assert cuts.map_time(6.0, segs) is not None and cuts.map_time(5.0, segs) is None
out_words = cuts.remap_words(words, segs)
assert [x["word"] for x in out_words][-6:] == ["hoy", "vamos", "a", "ver", "algo.", "Fin"], out_words
assert all(b["start"] >= a["end"] - 1e-6 for a, b in zip(out_words, out_words[1:]))
inp, g, v, a = cuts.filter_graph(segs, True, "source.mp4")
assert "acrossfade=d=0.03" in g and v == "vc" and inp.count("-i") == len(segs) and "[0:v]trim" in g
print("OK cuts:", len(p), "propuestas,", len(segs), "tramos")
