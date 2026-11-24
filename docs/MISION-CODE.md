# Misión para Claude Code: llevar el Megamotor al nivel de video-use, OpenEdit y los clippers comerciales

Objetivo: un motor propio, original y gratuito que convierta video crudo en reels listos para publicar, mejor que `video-use`, `OpenEdit`, `MakeMyClip` y los clippers de pago en lo que le importa al dueño: **voz intacta, duración fiel, calidad verificada, render < 10 min en 2 CPU y nada se publica sin su aprobación.**

## Cómo trabajar
- Lee `CLAUDE.md` y `docs/CATALOGO-REPOS.md` primero. Un cambio = un commit pequeño. Corre `./tests/smoke_test.sh` antes de cada commit.
- **Estudia los repos de terceros, no los copies.** Lee su licencia. Si es MIT/Apache puedes reutilizar ideas y pequeñas partes citando la fuente en `docs/CREDITOS.md`; si no hay licencia o es no comercial (p. ej. ButterCut), solo aprende la idea y reimplementa desde cero.
- Clona los repos ajenos en una carpeta temporal fuera de `engine/` y léelos antes de ejecutar nada.
- Cada fase termina con una prueba automática y con un video real revisado a ojo (fotogramas) antes de dar la fase por cerrada.

## Fases (en orden)
1. **QA automático de salida** (primero, protege todo lo demás). `ffmpeg` con `freezedetect`, `blackdetect`, `signalstats` (brillo medio para no oscurecer), picos de audio y comparación de duración. Un reel que falle no llega al dueño. Informe `qa_report.json`.
2. **Cortes inteligentes con aprobación.** A partir de `words.json`: silencios, muletillas, tartamudeos y tomas repetidas. El motor **propone** una lista de cortes (`cuts.json`); por defecto no corta. Solo si el dueño lo pide para ese video se aplica, con crossfade de audio de 30 ms para no pinchar la voz.
3. **Reencuadre 9:16 con seguimiento de cara** (OpenCV/mediapipe), suave, sin saltos, con zoom de énfasis opcional y recorte circular PIP.
4. **Capa de motion con Remotion** (tipografía cinética, titulares, cifras animadas, transiciones). Imágenes reales de lo que se menciona, variadas, sin repetir; nunca emojis como elemento visual. Ritmo rápido: ninguna imagen se queda más de ~3 s salvo que hable a cámara.
5. **Sonido.** Normalización, reducción de ruido suave, efectos sintetizados muy por debajo de la voz. Música solo si el video original no trae y acorde al contenido.
6. **Selector de clips para videos largos.** Ranking por gancho, cierre y autonomía del clip; salida de varios candidatos para que el dueño elija.
7. **Publicación y comunidad.** Probar `publish.py` en una cuenta real, con aprobación. Borradores de respuestas a comentarios. Lectura de métricas para afinar ganchos.
8. **Rendimiento.** Medir con videos reales de 1, 5 y 10 min; todo debajo de 10 min de render. Documentar en `docs/LIMITES.md`.

## Criterio de terminado
Un video crudo de 60 s sale como reel 1080x1920 con subtítulos ES/PT, sin congelaciones ni oscurecido, con `qa_report.json` en verde, en menos de 10 minutos, y publicable con un clic tras aprobar.
