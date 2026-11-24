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
   Video largo: `transcribe`, luego `clips <id>` (candidatos por gancho/cierre/autonomía en `clips.json`); **tú lees
   el texto de cada uno**, recomiendas, el dueño elige y `clip-new <id> <n>` crea el trabajo del clip.
2. `transcribe <id>` → `words.json` (Groq gratis; `--local` usa faster-whisper).
3. **Tú lees `words.json`** y escribes `data/jobs/<id>/plan.json`:
   `{"hook": "...", "caption": "...", "hashtags": ["#..."], "pt_segments": [{"start":0,"end":2,"text":"..."}]}`
   La descripción sale de lo que se dice en el video, con voz del autor, sin sonar a IA.
   Opcional, con medida (tiempos del original, nada superpuesto):
   - `"zooms": [{"start","end","scale":1.12}]` zoom de énfasis.
   - `"pip": [{"start","end","image":"img/x.jpg","circle":true}]` imagen real a pantalla completa con la persona en círculo
     (máx. 6 s; sin círculo máx. 3,5 s; sin repetir imágenes). Las imágenes van dentro del trabajo.
   - `"motion": [{"start","end","kind":"titular|cifra|cinetica|barrido", ...}]` (Remotion, `cd motion && npm install`).
     Sin emojis. La cinética toma las palabras de `words.json`.
   - `"sfx": [{"t","kind":"whoosh|pop|click|riser"}]` y `"music": {"file":"musica/x.mp3"}` (solo si el original no trae).
4. Cortes (opcional): `cuts <id>` propone silencios, muletillas, tartamudeos y tomas repetidas en `cuts.json`.
   **No se corta nada** salvo que el dueño lo pida para ese video: `cuts <id> --select alta|0,3`, él aprueba
   (`cuts <id> --approve`) y se renderiza con `--apply-cuts`.
5. `render <id> --subs es-pt` → `reel.mp4` 1080x1920 (seguimiento de cara si hay OpenCV; `--no-track` lo apaga)
   + `cover.jpg` + `render_report.json` + `qa_report.json`. Si el QA sale en rojo el reel no pasa al dueño.
6. Revisa el resultado como director artístico (ver `.claude/skills/megamotor/SKILL.md`): fotogramas a ojo.
7. El dueño revisa en `python3 -m megamotor ui` y aprueba (o `approve <id>`; exige QA en verde).
8. `publish <id> --check` (no publica) y luego `publish <id>` solo con estado `aprobado`.
   Comentarios: `comments <id> --draft`, tú redactas `text` en `replies.json`, él marca `approved: true`, `replies <id>`.
   Métricas: `insights <id>` y `performance` (retención por gancho) para afinar la fórmula.

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
1. Probar `publish.py` con la cuenta real (`publish --check` primero). Probado solo contra un Graph API simulado.
2. Validar todo con videos reales del dueño (hasta ahora: videos sintéticos y fotos de prueba). Afinar umbrales de
   `qa.py`, `sound.py` (detección de música) y `clips.py` con esos videos.
3. Reencuadre: Haar de OpenCV es básico; probar un detector mejor (YuNet, MIT) si falla con caras de perfil o poca luz.
4. Imágenes reales para `pip`: hoy las pone el dueño o Claude a mano dentro del trabajo; falta un buscador con licencia.
