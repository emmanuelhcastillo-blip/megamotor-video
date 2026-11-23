"""Ayudantes de ffmpeg/ffprobe."""
import json
import re
import subprocess


def run(cmd, **kw):
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        raise RuntimeError(f"Falló: {' '.join(map(str, cmd))}\n{p.stderr[-1500:]}")
    return p


def probe(path):
    p = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    j = json.loads(p.stdout)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), None)
    fps = 30.0
    if v and v.get("r_frame_rate") and "/" in v["r_frame_rate"]:
        n, d = v["r_frame_rate"].split("/")
        fps = float(n) / float(d) if float(d) else 30.0
    return {
        "duration": float(j["format"].get("duration", 0)),
        "width": int(v["width"]) if v else 0,
        "height": int(v["height"]) if v else 0,
        "fps": fps,
        "has_audio": a is not None,
        "size_mb": round(int(j["format"].get("size", 0)) / 1e6, 2),
    }


def extract_audio(src, dst):
    """Audio mono 16 kHz mp3 a 32 kbps: ~0.24 MB por minuto, cabe en el límite de 25 MB de Groq (~100 min)."""
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
         "-b:a", "32k", str(dst)])


def split_audio(audio, outdir, seconds=600):
    """Parte el audio en trozos de `seconds` para videos largos."""
    outdir.mkdir(parents=True, exist_ok=True)
    pat = str(outdir / "part_%03d.mp3")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(audio), "-f", "segment", "-segment_time", str(seconds),
         "-c", "copy", pat])
    return sorted(outdir.glob("part_*.mp3"))


def detect_silences(src, noise_db=-35, min_dur=0.6):
    """Devuelve [(inicio, fin)] de silencios. Solo informa: el motor NO corta por defecto."""
    p = subprocess.run(["ffmpeg", "-i", str(src), "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}",
                        "-f", "null", "-"], capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", p.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", p.stderr)]
    return list(zip(starts, ends))


def thumbnail(src, dst, at=1.0):
    run(["ffmpeg", "-y", "-v", "error", "-ss", str(at), "-i", str(src), "-frames:v", "1", "-q:v", "2", str(dst)])
