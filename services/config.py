from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "config.json"


@dataclass(frozen=True)
class AppSettings:
    auth_key: str
    host: str
    port: int
    generated_images_dir: Path
    generated_images_index_file: Path
    public_base_url: str
    image_ttl_seconds: int
    image_cleanup_interval_seconds: int
    request_timeout: int


def _parse_int(value: object, *, default: int, field_name: str) -> int:
    if value is None or str(value).strip() == "":
        return default
    try:
        parsed = int(str(value).strip())
    except Exception as exc:
        raise ValueError(f"config '{field_name}' must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"config '{field_name}' must be > 0")
    return parsed


def _load_settings() -> AppSettings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw_config: dict[str, object] = {}

    if CONFIG_FILE.is_file():
        text = CONFIG_FILE.read_text(encoding="utf-8").strip()
        if text:
            loaded = json.loads(text)
            if not isinstance(loaded, dict):
                raise ValueError("config.json must be a JSON object")
            raw_config = loaded

    auth_key = str(os.getenv("AUTH_KEY") or raw_config.get("auth-key") or "").strip()
    if not auth_key:
        print("[config] WARNING: auth-key is not set, using default 'img2api'. Please set 'auth-key' in config.json or AUTH_KEY env.", file=sys.stderr)
        auth_key = "img2api"

    public_base_url = str(os.getenv("PUBLIC_BASE_URL") or raw_config.get("public-base-url") or "").strip()
    image_ttl_hours = _parse_int(
        os.getenv("IMAGE_TTL_HOURS", raw_config.get("image-ttl-hours")),
        default=24 * 15,
        field_name="image-ttl-hours",
    )
    cleanup_interval_seconds = _parse_int(
        os.getenv("IMAGE_CLEANUP_INTERVAL_SECONDS", raw_config.get("image-cleanup-interval-seconds")),
        default=300,
        field_name="image-cleanup-interval-seconds",
    )
    request_timeout = _parse_int(
        os.getenv("REQUEST_TIMEOUT", raw_config.get("request-timeout")),
        default=300,
        field_name="request-timeout",
    )
    generated_images_dir = DATA_DIR / "generated"

    return AppSettings(
        auth_key=auth_key,
        host="0.0.0.0",
        port=9099,
        generated_images_dir=generated_images_dir,
        generated_images_index_file=generated_images_dir / "index.json",
        public_base_url=public_base_url,
        image_ttl_seconds=image_ttl_hours * 3600,
        image_cleanup_interval_seconds=cleanup_interval_seconds,
        request_timeout=request_timeout,
    )


config = _load_settings()

_DEFAULT_AUTH_KEY = "img2api"


def get_auth_key() -> str:
    env_key = os.getenv("AUTH_KEY", "").strip()
    if env_key:
        return env_key
    if CONFIG_FILE.is_file():
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                value = str(raw.get("auth-key") or "").strip()
                if value:
                    return value
        except Exception:
            pass
    return config.auth_key or _DEFAULT_AUTH_KEY
