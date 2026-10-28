# Image for the voice bot (Railway, Render, Fly.io or any Docker host).
FROM python:3.12-slim

# git is needed to install Pipecat from its pinned commit.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Hosts pass the port to listen on in $PORT.
ENV PORT=7860 PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
CMD ["sh", "-c", "python demo_openai1.py --host 0.0.0.0 --port ${PORT} -t webrtc"]
