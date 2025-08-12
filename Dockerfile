# Use Python 3.9, MeloTTS is most tested there
FROM python:3.9-slim

# System deps: git for clone, ffmpeg/libsndfile for audio IO, curl for health/debug
RUN apt-get update && apt-get install -y --no-install-recommends \
  git build-essential ffmpeg libsndfile1 ca-certificates curl \
  && rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Copy app files first to leverage Docker layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Clone MeloTTS and install it editable (pulls its Python deps)
RUN git clone --depth=1 https://github.com/myshell-ai/MeloTTS.git /app/MeloTTS
WORKDIR /app/MeloTTS
RUN pip install --no-cache-dir -e .

# Japanese tokenizer (safe even if you don't use JP)
RUN python -m unidic download

# Back to app and copy source
WORKDIR /app
COPY app.py /app/app.py

# Env defaults (override in Railway if you want)
ENV MELO_DEFAULT_LANGUAGE=EN
ENV MELO_DEFAULT_SPEAKER=EN-US
ENV MELO_DEFAULT_SPEED=1.0
ENV MELO_PRELOAD_LANGUAGES=EN
ENV MELO_DEVICE=auto

# Railway injects PORT; default to 8000 for local
ENV PORT=8000

# Warm-up on container start by hitting /healthz implicitly when uvicorn boots
# Expose and run
EXPOSE 8000
CMD python -m uvicorn app:app --host 0.0.0.0 --port ${PORT}