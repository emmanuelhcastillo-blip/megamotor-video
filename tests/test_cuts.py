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

# ajuste al silencio: el borde busca solo hacia el lado que se corta
import numpy as np
from megamotor import effects
sr = 16000
x = np.full(sr * 3, 0.5, dtype=np.float32)
x[int(1.40 * sr):int(1.46 * sr)] = 0.0          # pausa antes del corte
x[int(1.70 * sr):int(1.76 * sr)] = 0.0          # pausa dentro de lo que se conserva: no debe ir ahí
(s0, e0), (s1, e1) = cuts.snap([(0.0, 1.45), (1.65, 3.0)], x, duration=3.0)
assert 1.40 <= e0 <= 1.47 and 1.50 <= s1 <= 1.67, (e0, s1)
cam = effects.dynamic_track([4.0, 10.0], 20.0, [{"start": 12, "end": 14}])
assert cam[0]["from"] == 1.0 and cam[1]["from"] == 1.10, cam
assert not any(z["start"] < 14 and z["end"] > 12 for z in cam)
assert "gte(t" in effects.zoom_expr(cam)
print("OK snap y cámara dinámica")
