# Megamotor

Motor de edición de video para reels, hecho para trabajar con Claude Code. Convierte un video crudo en un reel vertical con subtítulos, descripción y etiquetas, lo deja listo para revisar y, solo con aprobación, lo publica en Instagram.

```
video crudo → transcribir → plan (Claude) → render 9:16 → revisión → aprobar → publicar → comentarios
```

## Empezar
```bash
cp .env.example .env            # pon tus claves (docs/APIS-GRATIS.md)
export PYTHONPATH=engine
python3 -m megamotor doctor
./tests/smoke_test.sh           # sin claves, debe terminar en SMOKE OK

python3 -m megamotor new mi_video.mp4 --name tema
python3 -m megamotor transcribe tema
# Claude escribe data/jobs/tema/plan.json (gancho, descripción, etiquetas, portugués)
python3 -m megamotor render tema --subs es-pt
python3 -m megamotor ui         # revisar y aprobar en http://127.0.0.1:8765
```

## Qué hay
- Núcleo en Python (solo `requests` + ffmpeg), pensado para 2 CPU y render de menos de 10 minutos.
- Subtítulos karaoke ES arriba y PT abajo, reencuadre 9:16, volumen normalizado, duración fiel al original.
- Interfaz local de aprobación. Publicación por la API oficial de Instagram con puerta de aprobación.
- Guía para Claude Code en `CLAUDE.md` y la skill `.claude/skills/megamotor`.
- Catálogo de repos open source a integrar en `docs/CATALOGO-REPOS.md`.

## Estado
v0.1: núcleo, interfaz y pruebas de humo funcionando. La publicación en Instagram está escrita pero **sin probar contra Meta**. Hoja de ruta en `CLAUDE.md`.
