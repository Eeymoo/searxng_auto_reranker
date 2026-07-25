FROM searxng/searxng:latest

# Base image is Void Linux (no apk / apt-get). SearXNG runs in a venv at
# /usr/local/searxng/.venv; install plugin deps into THAT venv so the plugin
# can import them at runtime.
USER root
RUN /usr/local/searxng/.venv/bin/python -m ensurepip --upgrade \
 && /usr/local/searxng/.venv/bin/python -m pip install --no-cache-dir \
      psycopg2-binary httpx
