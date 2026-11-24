"""Pruebas de reframe.py sin OpenCV: suavizado, zona muerta, cambios de plano y sendcmd."""
import pathlib, tempfile
from megamotor import reframe

# 1920x1080 -> escalado 3414x1920. Cara quieta con temblor, luego se desplaza, luego un cambio de plano.
s = []
for k in range(100):
    t = k / 5
    cx = 0.30 + (0.004 if k % 2 else -0.004) if t < 6 else (0.30 + (t - 6) * 0.05 if t < 10 else 0.80)
    if k == 20: cx = 0.95                 # detección suelta equivocada
    if t >= 15: cx = 0.20                 # plano nuevo
    s.append([t, None if k in (40, 41) else cx, 0.1])
a = {"width": 1920, "height": 1080, "samples": s, "shots": [0.0, 15.0]}
sw, path = reframe.build_path(a)
assert sw == 3414, sw
xs = dict(path)
still = [x for t, x in path if 1 <= t < 5.4]
assert max(still) - min(still) < 1, "con la cara quieta el encuadre no tiembla"
assert abs(xs[4.0] - (0.30 * sw - 540)) < 60, xs[4.0]   # la detección suelta de t=4 no arrastra
assert all(abs(b[1] - a[1]) <= reframe.MAX_SPEED / 5 + 1 for a, b in zip(path, path[1:]) if b[0] < 15)
assert abs(xs[15.0] - (0.20 * sw - 540)) < 1, "en un cambio de plano el encuadre salta al sujeto"
f = pathlib.Path(tempfile.mkdtemp()) / "crop.cmd"
n = reframe.write_sendcmd(path, a["shots"], f, 30, 20)
lines = f.read_text().splitlines()
assert n == len(lines) and lines[0].startswith("0.000 crop@rf x ")
xv = [(float(l.split()[0]), int(l.split()[3].rstrip(";").split("*")[0])) for l in lines]
jump = [(t, x) for t, x in xv if 14.9 < t < 15.1]
assert jump and jump[-1][1] == round(0.20 * sw - 540), jump
print("OK reframe:", n, "comandos")
