"""Sonido: normalización a -16 LUFS en dos pasadas, reducción de ruido suave solo si hace falta,
efectos sintetizados muy por debajo de la voz y música solo si el original no la trae.

plan.json:
  "sfx":   [{"t": 3.2, "kind": "whoosh"}]            whoosh | pop | click | riser  (tiempos del original)
  "music": {"file": "musica/tema.mp3", "gain_db": -24}  archivo con licencia, dentro del trabajo
La voz nunca se recorta ni se tapa: la música se comprime con la voz como llave (ducking) y los efectos
van a -20 dB o menos.
"""
import json
import pathlib
import re
import subprocess

from . import cuts, media

TARGET_I, TARGET_TP, TARGET_LRA = -16.0, -1.5, 11.0
NOISE_DB = -52       # ruido de fondo por encima de esto -> reducción suave
SFX_DB = -20         # efectos respecto a escala completa antes de normalizar (voz ~ -20..-14)
SFX_MAX_DB = -14
MUSIC_DB = -24
SFX = {
    "whoosh": "anoisesrc=d=0.6:c=pink:a=0.6,highpass=f=300,lowpass=f=4000,"
              "afade=t=in:d=0.35:curve=exp,afade=t=out:st=0.35:d=0.25",
    "pop": "sine=f=880:d=0.09,afade=t=out:d=0.09:curve=exp",
    "click": "sine=f=2200:d=0.025,afade=t=out:d=0.025",
    "riser": "aevalsrc='0.5*sin(2*PI*(180*t+260*t*t))':d=1.2,afade=t=in:d=1.0:curve=exp,afade=t=out:st=1.1:d=0.1",
}


def _pcm(src, sr=16000):
    import numpy as np
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", str(sr),
                        "-f", "s16le", "-"], capture_output=True)
    return np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768.0


def _db(x):
    import numpy as np
    return 20 * np.log10(np.sqrt(np.mean(x * x)) + 1e-9)


def analyze(src, words):
    """Ruido de fondo, nivel en pausas (¿música?) y medición de loudness para la segunda pasada."""
    sr, hop = 16000, 800  # ventanas de 50 ms
    x = _pcm(src, sr)
    out = {}
    if len(x) >= hop:
        import numpy as np
        n = len(x) // hop
        fr = x[: n * hop].reshape(n, hop)
        db = 20 * np.log10(np.sqrt((fr * fr).mean(axis=1)) + 1e-9)
        out["noise_floor_db"] = round(float(np.percentile(db, 10)), 1)
        out["speech_db"] = round(float(np.percentile(db, 90)), 1)
        gaps, idx = [], []
        edges = [(0.0, 0.0)] + [(w["start"], w["end"]) for w in words] + [(n * hop / sr, n * hop / sr)]
        for (_, a), (b, _) in zip(edges, edges[1:]):
            if b - a > 0.4:
                idx += list(range(int((a + 0.1) * sr / hop), min(n, int((b - 0.1) * sr / hop))))
        gaps = db[idx] if idx else []
        gap = float(np.median(gaps)) if len(gaps) else None
        out["gap_db"] = round(gap, 1) if gap is not None else None
        flat = None
        if idx:
            # planitud espectral en las pausas: el ruido es plano (~0.15-0.5), la música es tonal (< 0.1)
            P = np.abs(np.fft.rfft(fr[idx] * np.hanning(hop), axis=1)) ** 2 + 1e-12
            flat = float(np.median(np.exp(np.log(P).mean(axis=1)) / P.mean(axis=1)))
            out["gap_flatness"] = round(flat, 3)
        # en las pausas sin voz suena algo sostenido y tonal: música. Si dudamos, no se añade otra.
        out["music_likely"] = bool(gap is not None and gap > -45 and flat is not None and flat < 0.1)
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-vn", "-af",
                        f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr)
    if m:
        out["loudness"] = json.loads(m.group(0))
    return out


def run(job_dir, words):
    job_dir = pathlib.Path(job_dir)
    f = job_dir / "sound.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    a = analyze(next(job_dir.glob("source.*")), words)
    f.write_text(json.dumps(a, indent=2), encoding="utf-8")
    return a


def make_sfx(job_dir, kind):
    if kind not in SFX:
        raise SystemExit(f"sfx desconocido {kind!r} (usa {', '.join(SFX)})")
    d = pathlib.Path(job_dir) / "sfx"
    d.mkdir(exist_ok=True)
    f = d / f"{kind}.wav"
    if not f.exists():
        media.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", SFX[kind], "-af", "alimiter=limit=0.89,aformat=sample_rates=48000:channel_layouts=stereo", str(f)])
    return f


def _loudnorm(a):
    L = a.get("loudness")
    base = f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"
    if not L or float(L.get("input_i", "-inf")) < -60:
        return base
    return (base + f":measured_I={L['input_i']}:measured_TP={L['input_tp']}:measured_LRA={L['input_lra']}"
            f":measured_thresh={L['input_thresh']}:offset={L['target_offset']}:linear=true")


def audio_graph(job_dir, ain, plan, analysis, segs, first_input, offset=0.0, out_sfx=()):
    """Devuelve (partes del grafo, entradas extra, informe). La salida se llama [aout]."""
    job_dir = pathlib.Path(job_dir)
    parts, inputs, rep = [], [], {"denoise": False, "sfx": 0, "music": False}
    voice = [f"aresample=48000", "highpass=f=70"]  # quita retumbe; no toca la voz
    nf = analysis.get("noise_floor_db")
    if nf is not None and nf > NOISE_DB:
        voice.append(f"afftdn=nr=10:nf={max(-80, min(-20, round(nf)))}:tn=1")
        rep["denoise"] = True
    parts.append(f"[{ain}]{','.join(voice)}[voz]")
    mix = ["voz"]

    music = plan.get("music")
    if music:
        if analysis.get("music_likely"):
            raise SystemExit("El video original ya parece traer música: no se añade otra (regla dura).")
        mf = (job_dir / music["file"]).resolve()
        if job_dir.resolve() not in mf.parents or not mf.is_file():
            raise SystemExit(f"Música no válida (debe estar dentro del trabajo): {music['file']}")
        g = min(float(music.get("gain_db", MUSIC_DB)), -18)
        k = first_input + inputs.count("-i")
        inputs += ["-stream_loop", "-1", "-i", str(mf.relative_to(job_dir))]
        parts[-1] = parts[-1].replace("[voz]", "[voz0]")
        parts.append("[voz0]asplit=2[voz][llave]")
        parts.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,volume={g}dB[mus0]")
        parts.append("[mus0][llave]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[mus]")
        mix.append("mus")
        rep["music"] = True

    items = []
    for s in plan.get("sfx") or []:
        t = float(s["t"])
        if segs:
            t = cuts.map_time(t, segs)
            if t is None:
                continue
        items.append(dict(s, t=t + offset))
    items += [{"t": t, "kind": kind} for t, kind in out_sfx]   # ya en tiempo de salida
    for k, s in enumerate(items):
        t = s["t"]
        f = make_sfx(job_dir, s.get("kind", "whoosh"))
        g = min(float(s.get("gain_db", SFX_DB)), SFX_MAX_DB)
        i = first_input + inputs.count("-i")
        inputs += ["-i", str(f.relative_to(job_dir))]
        ms = int(round(t * 1000))
        parts.append(f"[{i}:a]volume={g}dB,adelay={ms}|{ms}[sfx{k}]")
        mix.append(f"sfx{k}")
        rep["sfx"] += 1

    if len(mix) > 1:
        # duration=first: la duración la marca la voz; normalize=0: la voz no baja al mezclar
        parts.append("".join(f"[{m}]" for m in mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0[mez]")
        last = "mez"
    else:
        last = "voz"
    parts.append(f"[{last}]{_loudnorm(analysis)}[aout]")
    return parts, inputs, rep
