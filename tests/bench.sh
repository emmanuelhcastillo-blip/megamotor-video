#!/usr/bin/env bash
# Rendimiento: video sintético de N minutos (1080p, cara en movimiento, voz a ráfagas) con todo el motor activo
# (seguimiento, subtítulos ES/PT, cortes aprobados, zoom, pip, motion, sonido) limitado a 2 CPU.
# Uso: tests/bench.sh 1 5 10    -> tabla para docs/LIMITES.md
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/engine"
export MEGAMOTOR_DATA="$(mktemp -d)"
trap 'rm -rf "$MEGAMOTOR_DATA"' EXIT
# BENCH_FACE: foto con una cara para medir el seguimiento (no se versiona por derechos de imagen)
FACE="${BENCH_FACE:-}"
echo "| Duración | Generar fuente | Render (2 CPU) | x tiempo real | Memoria máx. | Seguimiento | QA |"
echo "|---|---|---|---|---|---|---|"
for MIN in "$@"; do
  S=$((MIN * 60)); SRC="$MEGAMOTOR_DATA/src$MIN.mp4"
  t0=$(date +%s)
  if [ -n "$FACE" ]; then
    ffmpeg -y -v error -f lavfi -i "testsrc2=size=1920x1080:rate=30:duration=$S" -loop 1 -i "$FACE" \
      -f lavfi -i "aevalsrc='0.3*sin(2*PI*180*t)*sin(2*PI*3*t)*lt(mod(t\,7)\,5.5)':d=$S" \
      -filter_complex "[1:v]scale=420:-2[f];[0:v][f]overlay=x='760+500*sin(t/4)':y=300:shortest=1[v]" \
      -map "[v]" -map 2 -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p -c:a aac "$SRC"
  else
    ffmpeg -y -v error -f lavfi -i "testsrc2=size=1920x1080:rate=30:duration=$S" \
      -f lavfi -i "aevalsrc='0.3*sin(2*PI*180*t)*sin(2*PI*3*t)*lt(mod(t\,7)\,5.5)':d=$S" \
      -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p -c:a aac "$SRC"
  fi
  gen=$(( $(date +%s) - t0 ))
  ID=$(python3 -m megamotor new "$SRC" --name "bench$MIN" | sed -n 1p); D="$MEGAMOTOR_DATA/jobs/$ID"
  python3 - "$D" "$S" <<'PY'
import json, sys
d, S = sys.argv[1], float(sys.argv[2])
w, t, k = [], 0.0, 0
while t < S - 1:
    if (t % 7) < 5.4:
        w.append({"word": f"palabra{k}" + ("." if k % 9 == 8 else ""), "start": round(t, 2), "end": round(t + 0.3, 2)}); k += 1
    t += 0.35
json.dump({"words": w}, open(d + "/words.json", "w"))
pt = [{"start": i * 7.0, "end": i * 7.0 + 5.4, "text": "Frase em português"} for i in range(int(S // 7))]
plan = {"caption": "bench", "pt_segments": pt,
        "zooms": [{"start": 10, "end": 12, "scale": 1.12}],
        "pip": [{"start": 20, "end": 23, "image": "img/foto.png"}],
        "motion": [{"start": 2, "end": 4, "kind": "titular", "text": "Titular de prueba"},
                   {"start": 30, "end": 32, "kind": "cifra", "value": 80, "suffix": "%"}],
        "sfx": [{"t": 2, "kind": "whoosh"}]}
json.dump(plan, open(d + "/plan.json", "w"))
cuts = {"owner_approved": True, "cuts": [{"start": 40 + 60 * i, "end": 41 + 60 * i, "kind": "silencio", "text": "",
         "confidence": "alta", "apply": True} for i in range(int(S // 60))]}
json.dump(cuts, open(d + "/cuts.json", "w"))
PY
  mkdir -p "$D/img"; ffmpeg -y -v error -f lavfi -i "mandelbrot=size=1200x900" -frames:v 1 "$D/img/foto.png"
  [ -d motion/node_modules ] || python3 - "$D" <<'PY'
import json, sys
p = json.load(open(sys.argv[1] + "/plan.json")); p.pop("motion"); json.dump(p, open(sys.argv[1] + "/plan.json", "w"))
PY
  t0=$(date +%s)
  python3 - "$MEGAMOTOR_DATA/mem$MIN" taskset -c 0,1 python3 -m megamotor render "$ID" --subs es-pt --apply-cuts <<'PY'
import resource, subprocess, sys
r = subprocess.run(sys.argv[2:], stdout=subprocess.DEVNULL)
open(sys.argv[1], "w").write(str(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss // 1024))
sys.exit(r.returncode)
PY
  tot=$(( $(date +%s) - t0 ))
  python3 - "$D" "$MIN" "$gen" "$tot" "$(cat "$MEGAMOTOR_DATA/mem$MIN")" <<'PY'
import json, sys
d, m, gen, tot, mem = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
r = json.load(open(d + "/render_report.json"))
print(f"| {m} min | {gen} s | {tot} s (ffmpeg {r['render_seconds']} s, QA {r['qa_seconds']} s) | "
      f"{tot / r['source_seconds']:.2f} | {mem} MB | {r['reframe']} | {'verde' if r['qa_ok'] else 'ROJO'} |")
PY
done
