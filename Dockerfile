FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
# yt-dlp runs YouTube's JavaScript challenge with Node; without it most YouTube
# links fail with "This video is not available".
COPY --from=node:22-trixie-slim /usr/local/bin/node /usr/local/bin/node
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY main.py ./
COPY beacontube ./beacontube

RUN useradd --uid 1000 --no-create-home --home-dir /data --shell /usr/sbin/nologin tube \
    && mkdir -p /data && chown tube /data
USER tube

ENV DATA_DIR=/data PORT=8802 PATH="/app/.venv/bin:$PATH"
VOLUME /data
EXPOSE 8802
HEALTHCHECK --interval=60s --timeout=5s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=4)"

CMD ["python", "main.py"]
