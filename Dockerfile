# Stage 1: build frontend
FROM node:22-alpine AS web-builder

WORKDIR /web

COPY web/package.json web/package-lock.json* ./
RUN npm ci --ignore-scripts

COPY web/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

COPY main.py ./
COPY services ./services
COPY VERSION ./VERSION
COPY config.example.json ./config.json

COPY --from=web-builder /web/out ./web_dist

EXPOSE 9099

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9099", "--access-log"]
