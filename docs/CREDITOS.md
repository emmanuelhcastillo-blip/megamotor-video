# Créditos

Repos de terceros estudiados. No se ha copiado código; donde se tomó una idea se reimplementó desde cero.

| Repo | Licencia | Qué se aprendió | Dónde |
|---|---|---|---|
| [artbyjazi/autoclip](https://github.com/artbyjazi/autoclip) | MIT | Recorrido de recorte por planos; suavizado con zona muerta y límite de velocidad; muestreo de caras a 5 fps. Aquí el suavizado es offline (mediana + media centrada, sin retardo) en vez de su filtro 1€ causal. | `engine/megamotor/reframe.py` |
| [mutonby/openshorts](https://github.com/mutonby/openshorts) | MIT | Revisado; nada incorporado por ahora. | — |

Herramientas: [FFmpeg](https://ffmpeg.org) (freezedetect, blackdetect, signalstats, silencedetect, acrossfade, sendcmd) y [OpenCV](https://opencv.org) (clasificadores Haar, Apache 2.0).
