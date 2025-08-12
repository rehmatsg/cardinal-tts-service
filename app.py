import os
import io
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

# MeloTTS
from melo.api import TTS

# ---------- Settings ----------
DEFAULT_LANGUAGE = os.getenv("MELO_DEFAULT_LANGUAGE", "EN")
DEFAULT_SPEAKER = os.getenv("MELO_DEFAULT_SPEAKER", "EN-US")
DEFAULT_SPEED = float(os.getenv("MELO_DEFAULT_SPEED", "1.0"))
PRELOAD_LANGUAGES = [s.strip() for s in os.getenv("MELO_PRELOAD_LANGUAGES", "EN").split(",") if s.strip()]
DEVICE = os.getenv("MELO_DEVICE", "auto")  # auto|cpu|cuda|mps

app = FastAPI(title="MeloTTS API", version="1.0.0")

# Cache TTS models per language
_models: Dict[str, TTS] = {}
_speakers: Dict[str, Dict[str, int]] = {}

class SynthesizeIn(BaseModel):
  text: str = Field(..., min_length=1, max_length=2000)
  language: Optional[str] = Field(default=DEFAULT_LANGUAGE)
  speaker: Optional[str] = Field(default=DEFAULT_SPEAKER)
  speed: Optional[float] = Field(default=DEFAULT_SPEED, ge=0.5, le=2.0)

def load_language(lang: str) -> TTS:
  lang = lang.upper()
  if lang in _models:
    return _models[lang]
  try:
    model = TTS(language=lang, device=DEVICE)
  except Exception as e:
    raise HTTPException(status_code=400, detail=f"Failed to load language '{lang}': {e}")
  _models[lang] = model
  _speakers[lang] = model.hps.data.spk2id
  return model

@app.on_event("startup")
def warmup():
  # Preload configured languages and prime a short synthesis to download weights
  for lang in PRELOAD_LANGUAGES:
    model = load_language(lang)
    # Prime default speaker where possible
    spk_map = _speakers.get(lang, {})
    prime_spk = None
    # Prefer env default if it matches this language
    if DEFAULT_SPEAKER in spk_map:
      prime_spk = DEFAULT_SPEAKER
    # If not, pick any speaker
    if not prime_spk and spk_map:
      prime_spk = next(iter(spk_map.keys()))
    # Short prime to trigger model download/caches (errors ignored)
    if prime_spk:
      try:
        buf = io.BytesIO()
        model.tts_to_file("warmup", spk_map[prime_spk], buf, speed=DEFAULT_SPEED)
      except Exception:
        pass

@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
  return "ok"

@app.get("/voices")
def voices():
  result = {}
  # Ensure at least default language is loaded for listing
  load_language(DEFAULT_LANGUAGE)
  for lang, spk_map in _speakers.items():
    result[lang] = sorted(list(spk_map.keys()))
  return JSONResponse(result)

@app.post("/synthesize")
def synthesize(body: SynthesizeIn):
  lang = body.language.upper()
  model = load_language(lang)
  spk_map = _speakers.get(lang, {})
  if body.speaker not in spk_map:
    # Try to fallback to any available speaker
    if spk_map:
      fallback = next(iter(spk_map.keys()))
      body.speaker = fallback
    else:
      raise HTTPException(status_code=400, detail=f"No speakers available for language '{lang}'")

  # Generate to in-memory buffer as WAV
  wav_buf = io.BytesIO()
  try:
    model.tts_to_file(body.text, spk_map[body.speaker], wav_buf, speed=body.speed)
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"TTS failed: {e}")

  wav_buf.seek(0)
  headers = {"Content-Disposition": 'inline; filename="speech.wav"'}
  return StreamingResponse(wav_buf, media_type="audio/wav", headers=headers)