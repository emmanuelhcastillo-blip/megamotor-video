"""Pruebas de clips.py: frases, puntuación y candidatos sin solaparse."""
from megamotor import clips


def frase(texto, t0, ritmo=0.35):
    out, t = [], t0
    for w in texto.split():
        out.append({"word": w, "start": round(t, 2), "end": round(t + ritmo - 0.05, 2)})
        t += ritmo
    return out, t


words, t = [], 0.0
guion = [
    "y entonces eso que te decía antes sigue igual.",                     # mal arranque: conector + anáfora
    "¿Sabes por qué nunca ahorras dinero aunque ganes más?",              # buen gancho
    "El 80 por ciento de la gente gasta todo lo que entra cada mes.",
    "No es falta de dinero, es falta de un sistema simple.",
    "Separa un diez por ciento el mismo día que cobras.",
    "Así que la clave no es ganar más, es decidir primero.",              # buen cierre
    "pero bueno eso lo vemos otro día porque",                            # cierre colgado
    "Hoy te cuento otra cosa distinta sobre recetas de cocina.",
    "La receta lleva arroz, pollo y verduras de temporada.",
]
for g in guion:
    w, t = frase(g, t)
    words += w
    t += 0.6
s = clips.sentences(words)
assert len(s) == len(guion), [x["text"] for x in s]
c = clips.propose(words, t, min_s=10, max_s=25, n=3)
assert c and c[0]["gancho"].startswith("¿Sabes"), c[0]
assert c[0]["cierre"].endswith("decidir primero."), c[0]
assert all(not x["gancho"].startswith("y entonces") for x in c[:2])
for a in c:
    for b in c:
        if a is not b:
            assert min(a["end"], b["end"]) - max(a["start"], b["start"]) < 0.2 * a["duration"], (a, b)
print("OK clips:", [(x["rank"], x["score"], x["gancho"][:25]) for x in c])
