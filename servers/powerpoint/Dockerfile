# PowerPoint MCP Server — hardened image
FROM python:3.12-slim

# Build deps for Pillow / fonttools (kept minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user
RUN useradd --system --create-home --shell /usr/sbin/nologin mcp
WORKDIR /app

# Install deps first so they cache independently of source
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes=no -r requirements.txt

# App code (.dockerignore excludes .git, .env, .venv, __pycache__, samples)
COPY --chown=mcp:mcp . .

USER mcp
ENV PPT_WORKSPACE_ROOT=/app/workspace
RUN mkdir -p /app/workspace

ENTRYPOINT ["python", "ppt_mcp_server.py"]
