# AutoResearch GPU image for the Glasslab cluster
#
# Builds karpathy/autoresearch pinned to a specific upstream commit (see
# AUTORESEARCH_COMMIT) instead of cloning a moving branch, so the image is
# reproducible. torch is intentionally NOT installed separately here:
# upstream's own pyproject.toml/uv.lock already pin a specific cu128 torch
# build (see its [tool.uv.sources] / [[tool.uv.index]] entries), so a second
# manual torch install would only be silently discarded by `uv sync` anyway.
# `uv sync --frozen` installs exactly what's committed in uv.lock and fails
# loudly instead of silently re-resolving if the lock and pyproject.toml
# ever disagree.
#
# The FA3->SDPA attention patch for pre-Hopper GPUs (node02's A4000) is
# still applied at job runtime (see the Job YAML), not baked in here,
# pending a live GPU verification pass. A patches/ subdirectory belongs
# here if that ever becomes a build-time source patch instead.
FROM nvidia/cuda:12.8.2-base-ubuntu22.04

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/root/.local/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Pinned to the karpathy/autoresearch master HEAD as of this change. Bump
# deliberately, not automatically: prepare.py's cache in the Job YAML is
# keyed by this commit, and uv.lock (including its torch pin) travels with
# whatever commit is checked out below.
ARG AUTORESEARCH_COMMIT=228791fb499afffb54b46200aca536f79142f117
ENV AUTORESEARCH_COMMIT=${AUTORESEARCH_COMMIT}

RUN git clone https://github.com/karpathy/autoresearch.git /app/autoresearch \
    && cd /app/autoresearch \
    && git checkout "${AUTORESEARCH_COMMIT}"

WORKDIR /app/autoresearch

RUN uv sync --frozen

ARG GLASSLAB_GIT_SHA=unknown
ARG GLASSLAB_BUILD_SOURCE=unspecified
LABEL org.opencontainers.image.revision="${GLASSLAB_GIT_SHA}"
LABEL org.opencontainers.image.source="https://github.com/ccny-glasslab/glasslab-cluster-config"
LABEL io.glasslab.build-source="${GLASSLAB_BUILD_SOURCE}"
LABEL io.glasslab.autoresearch-commit="${AUTORESEARCH_COMMIT}"

CMD ["python3", "-c", "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"]
