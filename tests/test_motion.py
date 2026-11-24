"""Pruebas de motion.py sin Node: validación, palabras de la cinética, colocación y caché."""
from megamotor import motion


def falla(items, words=None):
    try:
        motion.validate(items, words)
    except SystemExit:
        return True
    return False


assert falla([{"start": 0, "end": 2, "kind": "explosion"}])
assert falla([{"start": 0, "end": 9, "kind": "titular", "text": "largo"}])
assert falla([{"start": 0, "end": 2, "kind": "titular", "text": "Ahorra ya \U0001F4B0"}]), "emojis prohibidos"
assert falla([{"start": 0, "end": 2, "kind": "cifra"}])
assert falla([{"start": 0, "end": 2, "kind": "cinetica"}], [])
W = [{"word": "Nadie", "start": 4.0, "end": 4.3}, {"word": "te", "start": 4.3, "end": 4.5},
     {"word": "obliga.", "start": 4.5, "end": 5.0}, {"word": "Fuera", "start": 6.0, "end": 6.2}]
[k] = motion.validate([{"start": 4.0, "end": 5.6, "kind": "cinetica"}], W)
assert k["words"] == [{"w": "Nadie", "t": 0.0}, {"w": "te", "t": 0.3}, {"w": "obliga", "t": 0.5}], k
# cara en la franja de arriba -> el gráfico baja; cara abajo -> se queda arriba
[a] = motion.place([{"start": 0, "end": 2, "kind": "titular", "text": "x"}], [208, 300, 664])
[b] = motion.place([{"start": 0, "end": 2, "kind": "titular", "text": "x"}], [208, 1200, 600])
assert a["top"] == motion.SLOTS[1] and b["top"] == motion.SLOTS[0], (a, b)
p = motion.props({"start": 1, "end": 3.5, "kind": "titular", "text": "x", "top": 520})
assert p == {"kind": "titular", "text": "x", "top": 520, "seconds": 2.5}, p
print("OK motion: validación y colocación")
