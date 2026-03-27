FROM python:3.11-slim
ARG GLASSLAB_GIT_SHA=unknown
ARG GLASSLAB_BUILD_SOURCE=unspecified
LABEL org.opencontainers.image.revision="${GLASSLAB_GIT_SHA}"
LABEL io.glasslab.build-source="${GLASSLAB_BUILD_SOURCE}"
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GLASSLAB_WORKFLOW_API_BUILD_SOURCE_REVISION=${GLASSLAB_GIT_SHA} \
    GLASSLAB_WORKFLOW_API_BUILD_SOURCE_LABEL=${GLASSLAB_BUILD_SOURCE}
COPY services/workflow-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/common /app/services/common
COPY services/workflow-registry /app/services/workflow-registry
COPY services/workflow-api/app /app/app
EXPOSE 8080
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
