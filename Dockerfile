FROM python:3.11-slim

# clingo links against glibc (alpine/musl would segfault); chromadb needs build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first — layer is cached until requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Static read-only assets baked into image
COPY policies/         ./policies/
COPY data/policy_text/ ./data/policy_text/
COPY src/              ./src/
COPY scripts/          ./scripts/
COPY .streamlit/       ./.streamlit/

# These directories are backed by named volumes at runtime
RUN mkdir -p data/chroma logs

EXPOSE 8000 8501 8502
