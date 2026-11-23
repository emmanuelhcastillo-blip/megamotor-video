# Megamotor · instrucciones para Claude Code

Motor de edición de video para reels (Instagram/TikTok/Shorts). Tú (Claude) eres el director: decides, escribes y revisas. El código hace el trabajo pesado con ffmpeg. El dueño aprueba antes de que algo salga a su cuenta.

## Arranque
```bash
export PYTHONPATH=engine
python3 -m megamotor doctor          # revisa ffmpeg y claves
./tests/smoke_test.sh                # debe terminar en SMOKE OK
```
Claves en `.env` (copia `.env.example`). Cómo conseguirlas gratis: `docs/APIS-GRATIS.md`.

## Flujo de un reel
1. `python3 -m megamotor new video.mp4 --name tema` → crea `data/jobs/<id>/`.
2. `transcribe <id>` → `words.json` (Groq gratis; `--local` usa faster-whisper).
3. **Tú lees `words.json`** y escribes `data/jobs/<id>/plan.json`:
   `{"hook": "...", "caption": "...", "hashtags": ["#..."], "pt_segments": [{"start":0,"end":2,"text":"..."}]}`
   La descripción sale de lo que se dice en el video, con voz del autor, sin sonar a IA.
4. `render <id> --subs es-pt` → `reel.mp4` 1080x1920 + `cover.jpg` + `render_report.json`.
5. Revisa el resultado como director artístico (ver `.claude/skills/megamotor/SKILL.md`). Si falla, corrige y re-renderiza.
6. El dueño revisa en `python3 -m megamotor ui` y aprueba (o `approve <id>`).
7. `publish <id>` solo funciona con estado `aprobado`. Los comentarios: tú redactas `replies.json`, él marca `approved: true`, luego `replies <id>`.

## Reglas duras (no negociables)
- **Nunca** recortar, tapar ni degradar la voz del autor. **Nunca** dejar el reel más corto que el original (el render lo comprueba y falla).
- Si el video ya trae música, **no añadir otra**. Efectos de sonido muy por debajo de la voz.
- Pocos efectos y sin superponerlos. Cortes con intención, no por adorno.
- Render por debajo de **10 minutos** en 2 CPU (`render_report.json` lo registra). Sin bajar calidad.
- **Nada se publica ni se comenta sin aprobación explícita** del dueño en esta conversación o en la UI. Las claves jamás se escriben en el repo ni en el chat.
- Imágenes e información: reales y verificables; no inventar datos ni citas.
- Español para el dueño. Respuestas de trabajo cortas; ahorra tokens.

## Mapa del repo
- `engine/megamotor/` núcleo (transcribe, captions, render, jobs, publish, cli, ui_server).
- `docs/CATALOGO-REPOS.md` repos open source a estudiar/integrar y qué tomar de cada uno.
- `docs/APIS-GRATIS.md` claves y cuotas gratuitas. `docs/LIMITES.md` límites medidos.
- `data/` (ignorado por git) trabajos y videos.

## Pendiente (hoja de ruta, en orden)
1. Probar `publish.py` con una cuenta real (no se ha probado contra Meta).
2. Reencuadre con seguimiento de cara (mediapipe/OpenCV) en vez de recorte centrado (`--crop-x` hoy es manual).
3. Remotion para motion graphics y tipografía cinética en cortes; integrar `remotion-dev/skills`.
4. Detección de silencios → propuesta de cortes que **tú** decides (hoy solo informa).
5. Selector de clips para videos largos (ranking por gancho) al estilo AutoClip/OpenShorts.
6. Análisis de rendimiento (alcance, retención) para afinar la fórmula de gancho.
