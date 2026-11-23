"""Transcripción con palabras y tiempos. Groq (gratis) primero; faster-whisper local como respaldo."""
import json
import time

import requests

from . import media
from .config import env, need

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def _groq_one(path, lang, offset):
    key = need("GROQ_API_KEY")
    model = env("GROQ_STT_MODEL", "whisper-large-v3-turbo")
    for attempt in range(4):
        with open(path, "rb") as f:
            r = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {key}"},
                files={"file": (path.name, f)},
                data={"model": model, "response_format": "verbose_json",
                      "timestamp_granularities[]": "word", **({"language": lang} if lang else {})},
                timeout=300,
            )
        if r.status_code == 429:  # límite gratis: 20 peticiones/min
            time.sleep(int(r.headers.get("retry-after", 10)))
            continue
        r.raise_for_status()
        j = r.json()
        words = [{"word": w["word"].strip(), "start": w["start"] + offset, "end": w["end"] + offset}
                 for w in j.get("words", [])]
        return words, j.get("text", "")
    raise RuntimeError("Groq siguió respondiendo 429 (límite de la capa gratis).")


def transcribe_groq(src, workdir, lang="es"):
    audio = workdir / "audio.mp3"
    media.extract_audio(src, audio)
    size_mb = audio.stat().st_size / 1e6
    parts = [audio] if size_mb < 24 else media.split_audio(audio, workdir / "parts", 600)
    words, text = [], []
    for i, p in enumerate(parts):
        w, t = _groq_one(p, lang, offset=i * 600 if len(parts) > 1 else 0)
        words += w
        text.append(t)
    return {"engine": "groq", "language": lang, "text": " ".join(text).strip(), "words": words}


def transcribe_local(src, workdir, lang="es"):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit("Instala el respaldo local: pip install faster-whisper")
    audio = workdir / "audio.mp3"
    media.extract_audio(src, audio)
    model = WhisperModel(env("LOCAL_WHISPER_MODEL", "small"), compute_type="int8")
    segs, _ = model.transcribe(str(audio), language=lang, word_timestamps=True)
    words, text = [], []
    for s in segs:
        text.append(s.text.strip())
        for w in s.words or []:
            words.append({"word": w.word.strip(), "start": w.start, "end": w.end})
    return {"engine": "faster-whisper", "language": lang, "text": " ".join(text), "words": words}


def run(src, workdir, lang="es", local=False):
    res = transcribe_local(src, workdir, lang) if local else transcribe_groq(src, workdir, lang)
    (workdir / "words.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res
