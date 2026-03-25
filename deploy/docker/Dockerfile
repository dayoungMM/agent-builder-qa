ARG PLATFORM_ARCH="linux/amd64"
ARG BASE_IMAGE="aip-harbor.sktai.io/sktai/python-base:3.12-bookworm-ossl3.0.18"
FROM --platform=${PLATFORM_ARCH} ${BASE_IMAGE}

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN addgroup -gid 1000 usergroup && \
    adduser user \
    --disabled-password \
    -u 1000 --gecos "" \
    --ingroup 0 \
    --ingroup usergroup && \
    chown -R user:usergroup /app

COPY --chown=user:usergroup requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user:usergroup app_streamlit/ ./app_streamlit/
COPY --chown=user:usergroup core/ ./core/
COPY --chown=user:usergroup scenarios/ ./scenarios/
COPY --chown=user:usergroup .env.example .env

USER user

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app_streamlit/main.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true"]
