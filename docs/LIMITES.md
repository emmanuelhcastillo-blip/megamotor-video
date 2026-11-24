# Límites medidos (entorno de Claude, 23-nov-2026)

| Recurso | Valor |
|---|---|
| CPU | 2 núcleos |
| RAM | 7 GB |
| Disco libre | ~31 GB |
| ffmpeg | con libx264, libass, loudnorm, silencedetect |

## Rendimiento medido (24-nov-2026, `tests/bench.sh`, 2 CPU con taskset)
Fuente sintética 1920x1080 30 fps con una cara en movimiento y voz a ráfagas; motor completo: seguimiento de cara,
subtítulos ES/PT, un corte aprobado por minuto, zoom, pip, dos gráficos de Remotion, efecto de sonido y QA.

| Duración | Render total | x tiempo real | Memoria máx. | QA |
|---|---|---|---|---|
| 1 min | 73 s (ffmpeg 44,5 s) | 1,22 | 620 MB | verde |
| 5 min | 269 s (ffmpeg 200 s) | 0,90 | 945 MB | verde |
| 10 min | 526 s (ffmpeg 411 s) | 0,88 | 1,4 GB | verde |

Primer video real (`casino online.mp4`, 3 min, 1080x1920, 14 Mbit/s, con teaser, color "pop", 4 zooms y 7 gráficos):
**168 s** de render, QA verde.

Lecciones (cada una corrigió un fallo medido):
- Recortar en la fuente y luego escalar; escalar todo a 3414x1920 primero costaba ~20 % más.
- No usar `trim` varias veces sobre la misma entrada ni `-loop 1` en imágenes: ffmpeg encola fotogramas
  decodificados y se queda sin memoria (5 min con cortes: proceso matado; pip: 2,3 GB). Una entrada con
  `-ss/-t` por tramo y `loop` dentro del grafo.
- Superponer gráficos en `yuv420`; con `format=auto` todo el video pasaba a 12 bits 4:4:4.
- `colorbalance` cuesta ~0,8 s por segundo de video: la calidez va en `eq` (gamma por canal).
- El QA de la salida va en una rama del propio render y el del original comparte decodificación con el
  seguimiento de cara: el QA pasó de ~11 s/min a <1 s/min.

## Límites prácticos recomendados
- Peso de entrada: hasta ~2 GB. Duración cómoda: hasta ~10 min de material crudo.
- Transcripción gratis: archivo ≤ 25 MB por petición (el motor trocea cada 10 min).
- Instagram: reels de hasta 90 s para máxima compatibilidad; resolución 1080x1920, 9:16.
- Sin GPU: nada de modelos de difusión ni upscalers pesados en local.
