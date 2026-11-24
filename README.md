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
- Núcleo en Python + ffmpeg, pensado para 2 CPU y render de menos de 10 minutos (`docs/LIMITES.md`).
- QA automático de salida (`qa_report.json`): congelaciones, negros, oscurecido, picos, silencios nuevos, loudness, duración.
- Cortes propuestos (silencios, muletillas, tartamudeos, tomas repetidas) que solo se aplican con aprobación.
- Reencuadre 9:16 con seguimiento de cara (OpenCV), zoom de énfasis y recorte circular (pip).
- Capa de motion con Remotion (`motion/`): titulares, cifras, tipografía cinética, barridos.
- Sonido: -16 LUFS, reducción de ruido suave, efectos sintetizados y música con ducking (solo si no trae).
- Selector de clips para videos largos. Publicación con chequeo previo, borradores de respuestas y métricas.
- Guía para Claude Code en `CLAUDE.md` y la skill `.claude/skills/megamotor`. Créditos en `docs/CREDITOS.md`.

## Estado
v0.2: las 8 fases de `docs/MISION-CODE.md` implementadas y con prueba automática (`tests/smoke_test.sh`).
Pendiente: probar con la cuenta real de Instagram y con videos reales del dueño.
