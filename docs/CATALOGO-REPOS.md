# Catálogo de repos a estudiar e integrar

Investigado el 23-nov-2026 con búsqueda web. **Ninguno está auditado todavía**: antes de ejecutar código de terceros se lee y se clona en una carpeta aparte, no dentro de `engine/`.

## Motion graphics y video como código
| Repo | Qué aporta | Cómo se instala |
|---|---|---|
| remotion-dev/skills | Enseña a Claude a escribir Remotion correcto (`useCurrentFrame`, `interpolate`, `spring`, `Sequence`). Viral en enero 2026. | `npx skills add remotion-dev/skills` |
| digitalsamba/claude-code-video-toolkit (MIT) | Flujo concepto→render con skills de Remotion, ElevenLabs, FFmpeg, Playwright y plantillas. | `git clone` y seguir su README |
| Clipwing/skills | Skills de Claude para motion graphics con Remotion: b-roll, subtítulos, diseño de sonido. | ver su README |
| Vincentwei1021/video-shotcraft | 106 recetas de plano y 161 previsualizaciones de movimiento para Remotion. | `npx skills add Vincentwei1021/video-shotcraft` |
| affaan-m/ecc (skill `remotion-video-creation`) | Detalles de implementación de Remotion. | `npx -y skills add affaan-m/ecc --skill remotion-video-creation --agent claude-code` |

## Clippers de video largo → shorts (alternativas libres a OpusClip)
| Repo | Qué aporta |
|---|---|
| artbyjazi/autoclip (MIT) | Local-first: video largo → clips 9:16 con subtítulos quemados y seguimiento de hablante, con interfaz de revisión. Whisper + Ollama sin conexión. |
| mutonby/openshorts (MIT) | Generador de clips, UGC con actores IA y estudio de YouTube; con Docker. |
| FujiwaraChoki/supoclip | Clipper con selección por IA, subtítulos y API propia. |
| aionixos/openclip | Local-first: descarga con yt-dlp, detección de gancho con LLM, seguimiento de hablante con ffmpeg. |
| Shaarav4795/ClippedAI | Basado en la librería clipsai; transcripción, detección de clips y títulos. |
| NaufalRizqullah/opensource-clipping | Subtítulos karaoke, teasers de gancho, miniaturas y subida a Facebook Reels. |

## Qué tomar de cada familia (plan de integración)
1. **Reencuadre con seguimiento** y **selección de clips por gancho**: estudiar AutoClip y OpenShorts; portar solo la lógica, no su interfaz.
2. **Motion graphics y tipografía cinética**: Remotion + remotion-dev/skills como capa de render para cortes con efectos.
3. **Recetas de plano**: video-shotcraft como biblioteca de movimientos.
4. **Publicación**: la API oficial de Instagram (ver `APIS-GRATIS.md`); NaufalRizqullah/opensource-clipping como referencia de programación de subidas.

## Cómo evaluar un repo antes de integrarlo
Licencia (MIT/Apache ok; sin licencia = no copiar código), actividad reciente, dependencias que pidan pago o GPU, y que respete las reglas duras de `CLAUDE.md` (voz intacta, duración fiel, render < 10 min en 2 CPU).
