# Límites medidos (entorno de Claude, 23-nov-2026)

| Recurso | Valor |
|---|---|
| CPU | 2 núcleos |
| RAM | 7 GB |
| Disco libre | ~31 GB |
| ffmpeg | con libx264, libass, loudnorm, silencedetect |

## Rendimiento medido
- Video sintético 1920x1080 de 8 s → reel 1080x1920 con subtítulos ES/PT: **4,3 s** de render. En proporción, un reel de 60 s debería tardar unos 30–60 s; un video de 10 min, unos 5 min. Se confirma con videos reales.

## Límites prácticos recomendados
- Peso de entrada: hasta ~2 GB. Duración cómoda: hasta ~10 min de material crudo.
- Transcripción gratis: archivo ≤ 25 MB por petición (el motor trocea cada 10 min).
- Instagram: reels de hasta 90 s para máxima compatibilidad; resolución 1080x1920, 9:16.
- Sin GPU: nada de modelos de difusión ni upscalers pesados en local.
