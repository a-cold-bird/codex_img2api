from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock


def _detect_extension(image_bytes: bytes, content_type: str) -> str:
    content_type = str(content_type or "").lower()
    if content_type == "image/jpeg" or image_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content_type == "image/webp" or (image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP"):
        return ".webp"
    if content_type == "image/gif" or image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    return ".png"


@dataclass
class StoredImageRecord:
    image_id: str
    file_name: str
    content_type: str
    created_at: str
    expires_at: str
    size_bytes: int


class ImageStore:
    def __init__(self, root_dir: Path, index_file: Path, ttl_seconds: int):
        self.root_dir = root_dir
        self.index_file = index_file
        self.ttl_seconds = ttl_seconds
        self._lock = Lock()

    def _load_index(self) -> dict[str, dict]:
        if not self.index_file.is_file():
            return {}
        try:
            payload = json.loads(self.index_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): value for key, value in payload.items() if isinstance(value, dict)}

    def _save_index(self, index: dict[str, dict]) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def save_image_bytes(self, image_bytes: bytes, content_type: str, metadata: dict | None = None) -> dict:
        image_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc)
        record = asdict(
            StoredImageRecord(
            image_id=image_id,
            file_name=f"{image_id}{_detect_extension(image_bytes, content_type)}",
            content_type=content_type or "image/png",
            created_at=created_at.isoformat(),
            expires_at=(created_at + timedelta(seconds=self.ttl_seconds)).isoformat(),
            size_bytes=len(image_bytes),
            )
        )
        if isinstance(metadata, dict):
            for key, value in metadata.items():
                if key not in record:
                    record[str(key)] = value
        with self._lock:
            self.root_dir.mkdir(parents=True, exist_ok=True)
            (self.root_dir / record["file_name"]).write_bytes(image_bytes)
            index = self._load_index()
            index[record["image_id"]] = record
            self._save_index(index)
        return dict(record)

    def get_record(self, image_id: str) -> dict | None:
        image_id = str(image_id or "").strip()
        if not image_id:
            return None
        with self._lock:
            index = self._load_index()
            record = index.get(image_id)
            if not isinstance(record, dict):
                return None
            return dict(record)

    def get_file_path(self, image_id: str, *, now: datetime | None = None) -> tuple[Path, str] | None:
        record = self.get_record(image_id)
        if not record:
            return None
        current = now or datetime.now(timezone.utc)
        try:
            expires_at = datetime.fromisoformat(str(record.get("expires_at") or ""))
        except Exception:
            expires_at = current - timedelta(seconds=1)
        if current >= expires_at:
            self.cleanup_expired(now=current)
            return None
        path = self.root_dir / str(record.get("file_name") or "")
        if not path.is_file():
            self.cleanup_expired(now=current)
            return None
        return path, str(record.get("content_type") or "image/png")

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(timezone.utc)
        removed = 0
        with self._lock:
            index = self._load_index()
            next_index: dict[str, dict] = {}
            for image_id, record in index.items():
                file_name = str(record.get("file_name") or "")
                path = self.root_dir / file_name
                try:
                    expires_at = datetime.fromisoformat(str(record.get("expires_at") or ""))
                except Exception:
                    expires_at = current - timedelta(seconds=1)
                expired = current >= expires_at
                if expired or not path.is_file():
                    if path.exists():
                        path.unlink(missing_ok=True)
                    removed += 1
                    continue
                next_index[image_id] = record
            self._save_index(next_index)
        return removed

    def list_records(self) -> list[dict]:
        with self._lock:
            index = self._load_index()
            records = [dict(value) for value in index.values() if isinstance(value, dict)]
        records.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return records
