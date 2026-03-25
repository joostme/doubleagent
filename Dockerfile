FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /uvx /bin/

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates wget socat \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project --no-dev

COPY doubleagent/ doubleagent/
COPY scripts/entrypoint.sh /entrypoint.sh
COPY scripts/install-ca.sh /scripts/install-ca.sh
COPY config/ config/
RUN uv sync --locked --no-dev --no-editable \
  && chmod +x /entrypoint.sh /scripts/install-ca.sh

RUN mkdir -p /certs /config

EXPOSE 8080 9000

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:9000/healthz || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["--config", "/config/config.json"]
