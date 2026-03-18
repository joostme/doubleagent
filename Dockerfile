FROM python:3.12-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates wget socat \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY doubleagent/ doubleagent/
COPY scripts/entrypoint.sh /entrypoint.sh
COPY scripts/install-ca.sh /scripts/install-ca.sh
COPY config/ config/
COPY README.md README.md
RUN chmod +x /entrypoint.sh /scripts/install-ca.sh

RUN mkdir -p /certs /config

EXPOSE 8080 9000

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:9000/healthz || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["--config", "/config/config.json"]
