FROM python:3.12-slim

# util-linux: nsenter for running ansible in host namespaces
# iproute2 / iputils-ping: diagnostics from inside the container if нужно
# qrencode: hot-fallback for QR; PIL is bundled with qrcode[pil]
RUN apt-get update && apt-get install -y --no-install-recommends \
        util-linux iproute2 iputils-ping qrencode openssl \
 && rm -rf /var/lib/apt/lists/*

COPY ui/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /opt/chain-proxy
COPY ui/ /opt/chain-proxy/ui/
ENV PYTHONUNBUFFERED=1 \
    CHAIN_PROXY_ROOT=/opt/chain-proxy \
    CHAIN_PROXY_DATA=/opt/chain-proxy/data \
    CHAIN_PROXY_PORT=8443 \
    PYTHONPATH=/opt/chain-proxy

EXPOSE 8443

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,ssl; \
ctx=ssl._create_unverified_context(); \
urllib.request.urlopen('https://127.0.0.1:8443/healthz', context=ctx, timeout=3)" \
  || exit 1

CMD ["python", "-m", "ui.main"]
