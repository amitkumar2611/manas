# MANAS — single-stage image. Kernel is featherweight; no GPU needed.
# Local LLM inference (ollama) runs as a SEPARATE container/host, not here.
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY manas ./manas
COPY prompts ./prompts
RUN pip install --no-cache-dir -e .

# State (memory, audit, plans) lives on a mounted volume, not in the image.
ENV MANAS_HOME=/data
VOLUME /data
EXPOSE 8420

# Default: HTTP API. Override CMD for the CLI (docker run ... manas status).
CMD ["uvicorn", "manas.api:app", "--host", "0.0.0.0", "--port", "8420"]
