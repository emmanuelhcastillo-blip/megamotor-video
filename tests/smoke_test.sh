#!/usr/bin/env bash
# Prueba de humo sin claves: video sintético -> render 9:16 con subtítulos ES/PT -> reglas duras -> UI.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/engine"
export MEGAMOTOR_DATA="$(mktemp -d)"
T="$MEGAMOTOR_DATA/prueba.mp4"

ffmpeg -y -v error -f lavfi -i testsrc2=size=1920x1080:rate=30:duration=8 \
  -f lavfi -i sine=frequency=220:duration=8 -c:v libx264 -pix_fmt yuv420p -c:a aac "$T"

ID=$(python3 -m megamotor new "$T" --name prueba | sed -n 1p)
D="$MEGAMOTOR_DATA/jobs/$ID"

cat > "$D/words.json" <<'EOF'
{"engine":"fake","language":"es","text":"hola esto es una prueba","words":[
{"word":"Hola","start":0.4,"end":0.8},{"word":"esto","start":0.9,"end":1.2},{"word":"es","start":1.2,"end":1.4},
{"word":"una","start":1.4,"end":1.6},{"word":"prueba.","start":1.6,"end":2.3},
{"word":"Segunda","start":3.0,"end":3.5},{"word":"frase","start":3.5,"end":4.0}]}
EOF
cat > "$D/plan.json" <<'EOF'
{"caption":"Prueba de humo","hashtags":["#test"],"pt_segments":[{"start":0.4,"end":2.3,"text":"Olá, isto é um teste."},{"start":3.0,"end":4.0,"text":"Segunda frase"}]}
EOF

python3 -m megamotor render "$ID" --subs es-pt
python3 - "$D" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1] + "/render_report.json"))
assert r["resolution"] == "1080x1920", r
assert r["output_seconds"] >= r["source_seconds"] - 0.15, r
assert r["under_10_min"], r
print("OK render:", r)
EOF

# puerta de aprobación: publicar sin aprobar debe fallar
if python3 -m megamotor publish "$ID" 2>/dev/null; then echo "FALLO: publicó sin aprobar"; exit 1; fi
python3 -m megamotor approve "$ID"
python3 -m megamotor status
echo "SMOKE OK"
