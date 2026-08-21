# The API, containerised. Not the Streamlit demo — that runs on Community Cloud from
# app/main.py, which is a fixed entry point and cannot be changed without taking a new
# URL. Both go through the same graph, so neither can behave differently from the other.
#
# CPU TORCH, EXPLICITLY. `pip install torch` on Linux brings the CUDA runtime with it —
# cudnn, nccl, cusparselt, nvshmem, triton — roughly two gigabytes of GPU libraries for
# an image that will never see a GPU. requirements.txt pins the CPU build against
# PyTorch's own index, and this file inherits that.
#
# THE EMBEDDING MODEL IS BAKED IN. Downloading a few hundred megabytes on first request
# would make the first learner wait for it, and a container that needs the network at
# startup fails in a way that looks like the app being broken. It is fetched at build
# time instead, so the image is large and the startup is not.
FROM python:3.12-slim AS base

# SudachiPy needs no system packages, and torch-cpu ships its own libraries. curl is
# here for the healthcheck below and nothing else.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Where sentence-transformers looks. Set before the model is fetched so the build
    # and the runtime agree on one location.
    HF_HOME=/opt/models

# The user is created BEFORE anything is copied. `chown -R` after the fact rewrites
# every file it touches into a new layer — on 2026-08-21 that one line added 2.5GB to
# an image that already contained the same bytes once.
RUN useradd --create-home --uid 10001 coach \
    && mkdir -p /app /opt/models \
    && chown coach /app /opt/models

WORKDIR /app

# Dependencies first, so editing a source file does not reinstall torch.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "fastapi==0.141.1" "uvicorn==0.52.1"

# Fetch the embedding model into the image. Done as its own layer so that changing the
# code does not re-download it.
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('intfloat/multilingual-e5-small')"

# Ownership is set as the files are copied, not afterwards. What arrives is governed
# by .dockerignore — without it the context was 2GB of virtualenv and git history.
COPY --chown=coach . .

# Nothing here writes anything, so the container has no reason to run as root.
USER coach

EXPOSE 8000

# Asks what the build can DO, not whether the process is alive: a container that lost
# retrieval answers with retrieval.available false, and this turns that into an
# unhealthy container rather than a silent downgrade.
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health \
        | python -c "import json,sys; sys.exit(0 if json.load(sys.stdin)['retrieval']['available'] else 1)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
