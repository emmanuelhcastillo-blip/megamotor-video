#!/usr/bin/env bash
# Prueba de humo sin claves: video sintético -> render 9:16 con subtítulos ES/PT -> reglas duras -> UI.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/engine"
export MEGAMOTOR_DATA="$(mktemp -d)"
trap 'rm -rf "$MEGAMOTOR_DATA"' EXIT
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

python3 tests/test_cuts.py
python3 tests/test_reframe.py
python3 tests/test_motion.py
python3 tests/test_clips.py
python3 -m megamotor cuts "$ID"
python3 - "$D" <<'EOF'
import json, sys
c = json.load(open(sys.argv[1] + "/cuts.json"))
assert c["cuts"] and not c["owner_approved"] and not any(x["apply"] for x in c["cuts"]), c
EOF

python3 -m megamotor render "$ID" --subs es-pt
python3 - "$D" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1] + "/render_report.json"))
assert r["resolution"] == "1080x1920", r
assert r["output_seconds"] >= r["source_seconds"] - 0.15, r
assert r["under_10_min"], r
assert r["qa_ok"], r
q = json.load(open(sys.argv[1] + "/qa_report.json"))
assert q["ok"] and len(q["checks"]) >= 8, q["checks"]
print("OK render:", r)
EOF

# QA debe rechazar un reel roto: imagen congelada + negro + audio mudo en medio
cp "$D/reel.mp4" "$D/reel.ok.mp4"
ffmpeg -y -v error -i "$D/reel.ok.mp4" \
  -vf "trim=0:2,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=6.2,drawbox=t=fill:c=black:enable='between(t,5,6.5)'" \
  -af "volume=enable='between(t,3,6)':volume=0" -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -t 8.1 "$D/reel.mp4"
if python3 -m megamotor qa "$ID"; then echo "FALLO: QA aprobó un reel roto"; exit 1; fi
python3 - "$D" <<'EOF'
import json, sys
q = json.load(open(sys.argv[1] + "/qa_report.json"))
bad = {c["check"] for c in q["checks"] if not c["ok"]}
assert {"sin_congelaciones", "sin_negros", "voz_intacta"} <= bad, bad
print("OK QA rechaza:", sorted(bad))
EOF
if python3 -m megamotor approve "$ID" 2>/dev/null; then echo "FALLO: aprobó con QA en rojo"; exit 1; fi
mv "$D/reel.ok.mp4" "$D/reel.mp4"
python3 -m megamotor qa "$ID"

# puerta de aprobación: publicar sin aprobar debe fallar
if python3 -m megamotor publish "$ID" 2>/dev/null; then echo "FALLO: publicó sin aprobar"; exit 1; fi
python3 -m megamotor approve "$ID"
python3 -m megamotor status
# cortes: sin aprobación del dueño no se corta; con aprobación, audio y video siguen en sincronía
ID2=$(python3 -m megamotor new "$T" --name cortes | sed -n 1p)
D2="$MEGAMOTOR_DATA/jobs/$ID2"
cp "$D/words.json" "$D/plan.json" "$D2/"
python3 -m megamotor cuts "$ID2" >/dev/null
python3 - "$D2" <<'EOF'
import json, sys
f = sys.argv[1] + "/cuts.json"; c = json.load(open(f))
c["cuts"] += [{"start": 1.0, "end": 1.5, "kind": "prueba", "text": "", "confidence": "alta", "apply": False},
              {"start": 2.4, "end": 2.9, "kind": "prueba", "text": "", "confidence": "alta", "apply": False}]
json.dump(c, open(f, "w"))
EOF
python3 -m megamotor cuts "$ID2" --select alta
if python3 -m megamotor render "$ID2" --subs es-pt --apply-cuts 2>/dev/null; then echo "FALLO: cortó sin aprobación"; exit 1; fi
python3 -m megamotor cuts "$ID2" --approve >/dev/null
python3 -m megamotor render "$ID2" --subs es-pt --apply-cuts | tail -12
python3 - "$D2" <<'EOF'
import json, subprocess, sys
r = json.load(open(sys.argv[1] + "/render_report.json"))
assert r["qa_ok"] and r["cuts_applied"] == 3 and abs(r["cut_seconds"] - 4.75) < 0.05, r
d = lambda s: float(subprocess.run(["ffprobe", "-v", "error", "-select_streams", s, "-show_entries", "stream=duration",
    "-of", "csv=p=0", sys.argv[1] + "/reel.mp4"], capture_output=True, text=True).stdout)
assert abs(d("v") - d("a")) < 0.1 and abs(d("v") - 3.25) < 0.15, (d("v"), d("a"))
print("OK cortes aprobados:", r)
EOF
# zoom de énfasis + pip circular; efectos superpuestos se rechazan
ID3=$(python3 -m megamotor new "$T" --name efectos | sed -n 1p)
D3="$MEGAMOTOR_DATA/jobs/$ID3"
cp "$D/words.json" "$D3/"; mkdir -p "$D3/img"
ffmpeg -y -v error -f lavfi -i "mandelbrot=size=800x600" -frames:v 1 "$D3/img/foto.jpg"
echo '{"caption":"x","zooms":[{"start":1,"end":3,"scale":1.15}],"pip":[{"start":2.5,"end":5,"image":"img/foto.jpg"}]}' > "$D3/plan.json"
if python3 -m megamotor render "$ID3" --subs es 2>/dev/null; then echo "FALLO: aceptó efectos superpuestos"; exit 1; fi
echo '{"caption":"x","zooms":[{"start":1,"end":2.5,"scale":1.15}],"pip":[{"start":4,"end":6.5,"image":"img/foto.jpg"}]}' > "$D3/plan.json"
python3 -m megamotor render "$ID3" --subs es | tail -1
python3 - "$D3" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1] + "/render_report.json"))
assert r["qa_ok"] and r["zooms"] == 1 and r["pip"] == 1 and r["resolution"] == "1080x1920", r
print("OK efectos:", r)
EOF
echo '{"caption":"x","pip":[{"start":4,"end":6,"image":"../../../etc/passwd"}]}' > "$D3/plan.json"
if python3 -m megamotor render "$ID3" --subs es 2>/dev/null; then echo "FALLO: aceptó imagen fuera del trabajo"; exit 1; fi
echo '{"caption":"x","pip":[{"start":1,"end":2,"image":"img/foto.jpg"},{"start":4,"end":5,"image":"img/foto.jpg"}]}' > "$D3/plan.json"
if python3 -m megamotor render "$ID3" --subs es 2>/dev/null; then echo "FALLO: aceptó imagen repetida"; exit 1; fi
echo '{"caption":"x","pip":[{"start":1,"end":5.5,"image":"img/foto.jpg","circle":false}]}' > "$D3/plan.json"
if python3 -m megamotor render "$ID3" --subs es 2>/dev/null; then echo "FALLO: imagen sola más de 3,5 s"; exit 1; fi

# capa de motion con Remotion (solo si está instalada: cd motion && npm install)
if [ -d motion/node_modules ]; then
  echo '{"caption":"x","pip":[{"start":1,"end":3.5,"image":"img/foto.jpg","circle":false}],"motion":[{"start":0.3,"end":0.8,"kind":"barrido"},{"start":4,"end":5.5,"kind":"cifra","value":80,"suffix":"%","label":"prueba"}]}' > "$D3/plan.json"
  python3 -m megamotor render "$ID3" --subs es | tail -1
  python3 - "$D3" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1] + "/render_report.json"))
assert r["qa_ok"] and r["motion"] == 2 and r["pip"] == 1, r
print("OK motion:", r["render_seconds"], "s")
EOF
else
  echo "AVISO: motion/node_modules no existe; se salta el render con Remotion"
fi
# sonido: "voz" a ráfagas con pausas reales + ruido de fondo; música bajo la voz; whoosh; música doble prohibida
V="$MEGAMOTOR_DATA/voz.mp4"
ffmpeg -y -v error -f lavfi -i testsrc2=size=1920x1080:rate=30:duration=8 \
  -f lavfi -i "aevalsrc='0.3*sin(2*PI*180*t)*sin(2*PI*3*t)*(between(t,0.4,2.3)+between(t,3,4))':d=8" \
  -f lavfi -i "anoisesrc=c=pink:a=0.03:d=8" -filter_complex "[1][2]amix=inputs=2:normalize=0[a]" -map 0:v -map "[a]" \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac "$V"
ID4=$(python3 -m megamotor new "$V" --name sonido | sed -n 1p)
D4="$MEGAMOTOR_DATA/jobs/$ID4"
cp "$D/words.json" "$D4/"; mkdir -p "$D4/musica"
ffmpeg -y -v error -f lavfi -i "aevalsrc='0.2*sin(2*PI*220*t)+0.15*sin(2*PI*277*t)+0.15*sin(2*PI*330*t)':d=3" "$D4/musica/acordes.wav"
echo '{"caption":"x","sfx":[{"t":2.6,"kind":"whoosh"}],"music":{"file":"musica/acordes.wav"}}' > "$D4/plan.json"
python3 -m megamotor render "$ID4" --subs es --no-track | tail -1
python3 - "$D4" <<'EOF'
import json, sys
from megamotor import sound
d = sys.argv[1]
r = json.load(open(d + "/render_report.json"))
s = r["sound"]
assert r["qa_ok"] and s["music"] and s["sfx"] == 1 and s["denoise"] and not s["music_in_source"], r
x = sound._pcm(d + "/reel.mp4")
voz, pausa = sound._db(x[int(0.6 * 16000):int(2.0 * 16000)]), sound._db(x[int(5 * 16000):int(7.5 * 16000)])
assert voz - pausa >= 10, f"la música no queda bajo la voz: voz {voz:.1f} dB, pausa {pausa:.1f} dB"
print(f"OK sonido: voz {voz:.1f} dB, música en pausa {pausa:.1f} dB, {s}")
EOF
cp "$D4/musica/acordes.wav" "$D/acordes.wav"
echo '{"caption":"x","music":{"file":"acordes.wav"}}' > "$D/plan.json"
if python3 -m megamotor render "$ID" --subs es 2>/dev/null; then echo "FALLO: añadió música sobre un audio con música"; exit 1; fi
# selector de clips: proponer, crear trabajo desde el elegido y renderizarlo
python3 -m megamotor clips "$ID" --min 1 --max 5 --n 2
CID=$(python3 -m megamotor clip-new "$ID" 1 | tail -1)
python3 -m megamotor render "$CID" --subs es | tail -1
python3 - "$MEGAMOTOR_DATA/jobs/$CID" <<'EOF'
import json, sys
d = sys.argv[1]
r = json.load(open(d + "/render_report.json")); j = json.load(open(d + "/job.json"))
w = json.load(open(d + "/words.json"))["words"]
lo, hi = j["parent_range"]
assert r["qa_ok"] and abs(r["source_seconds"] - (hi - lo)) < 0.1 and w and w[0]["start"] >= 0, (r, j)
print("OK clip:", j["parent"], j["parent_range"], r["output_seconds"], "s")
EOF
echo "SMOKE OK"
