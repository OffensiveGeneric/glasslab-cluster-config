FROM python:3.11-slim

ARG OPENCODE_VERSION=1.18.14
ARG HERMES_VERSION=v2026.8.3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git nodejs npm ca-certificates curl \
    && npm install --global "opencode-ai@${OPENCODE_VERSION}" \
    && curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- \
        --branch "${HERMES_VERSION}" --skip-setup --skip-browser --no-skills \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

ARG GLASSLAB_GIT_SHA=unknown
ARG GLASSLAB_BUILD_SOURCE=unspecified
LABEL org.opencontainers.image.revision="${GLASSLAB_GIT_SHA}"
LABEL org.opencontainers.image.source="https://github.com/OffensiveGeneric/glasslab-cluster-config"
LABEL io.glasslab.build-source="${GLASSLAB_BUILD_SOURCE}"

COPY app ./app
COPY prompts ./prompts
COPY evaluation-contracts ./evaluation-contracts

RUN useradd --uid 10001 --create-home orchestrator \
    && mkdir -p /var/lib/glasslab-research-orchestrator \
    && chown -R orchestrator:orchestrator /var/lib/glasslab-research-orchestrator

USER 10001:10001
EXPOSE 8080 4210 4211 4310 4311

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
