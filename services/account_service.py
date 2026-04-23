from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any


class AccountService:
    def __init__(self, store_file: Path):
        self.store_file = store_file
        self._lock = Lock()
        self._index = 0
        self._accounts = self._load_accounts()

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value or "").strip()

    def _find_index(self, api_key: str) -> int:
        for i, item in enumerate(self._accounts):
            if self._clean(item.get("api_key")) == api_key:
                return i
        return -1

    def _normalize(self, item: dict) -> dict | None:
        if not isinstance(item, dict):
            return None
        api_key = self._clean(item.get("api_key"))
        base_url = self._clean(item.get("base_url")).rstrip("/")
        if not api_key or not base_url:
            return None
        return {
            "base_url": base_url,
            "api_key": api_key,
            "status": self._clean(item.get("status")) or "正常",
            "success": max(0, int(item.get("success") or 0)),
            "fail": max(0, int(item.get("fail") or 0)),
            "last_used_at": item.get("last_used_at"),
            "created_at": self._clean(item.get("created_at")) or datetime.now().isoformat(timespec="seconds"),
        }

    def _load_accounts(self) -> list[dict]:
        if not self.store_file.exists():
            return []
        try:
            data = json.loads(self.store_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        return [n for item in data if (n := self._normalize(item)) is not None]

    def _save(self) -> None:
        self.store_file.parent.mkdir(parents=True, exist_ok=True)
        self.store_file.write_text(
            json.dumps(self._accounts, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _mask_key(api_key: str) -> str:
        if len(api_key) <= 8:
            return api_key[:2] + "***"
        return api_key[:4] + "***" + api_key[-4:]

    def _public_item(self, account: dict) -> dict:
        api_key = self._clean(account.get("api_key"))
        return {
            "id": hashlib.sha1(api_key.encode()).hexdigest()[:16],
            "base_url": account.get("base_url"),
            "api_key_masked": self._mask_key(api_key),
            "status": account.get("status") or "正常",
            "success": int(account.get("success") or 0),
            "fail": int(account.get("fail") or 0),
            "last_used_at": account.get("last_used_at"),
            "created_at": account.get("created_at"),
        }

    @staticmethod
    def _is_available(account: dict) -> bool:
        return isinstance(account, dict) and account.get("status") not in {"禁用", "异常"}

    def list_accounts(self) -> list[dict]:
        with self._lock:
            return [self._public_item(a) for a in self._accounts]

    def count_available(self) -> int:
        with self._lock:
            return sum(1 for a in self._accounts if self._is_available(a))

    def next_upstream(self, excluded: set[str] | None = None) -> dict:
        with self._lock:
            excluded_keys = {self._clean(k) for k in (excluded or set()) if self._clean(k)}
            candidates = [
                a for a in self._accounts
                if self._is_available(a) and self._clean(a.get("api_key")) not in excluded_keys
            ]
            if not candidates:
                raise RuntimeError("no available upstream")
            selected = candidates[self._index % len(candidates)]
            self._index += 1
            return dict(selected)

    def add_accounts(self, items: list[dict]) -> dict:
        with self._lock:
            indexed = {self._clean(a.get("api_key")): a for a in self._accounts}
            added = 0
            for item in items:
                n = self._normalize(item)
                if n is None:
                    continue
                key = self._clean(n.get("api_key"))
                if key not in indexed:
                    indexed[key] = n
                    added += 1
            self._accounts = list(indexed.values())
            self._save()
            return {"added": added, "total": len(self._accounts)}

    def delete_accounts(self, api_keys: list[str]) -> dict:
        target = {self._clean(k) for k in api_keys if self._clean(k)}
        with self._lock:
            before = len(self._accounts)
            self._accounts = [a for a in self._accounts if self._clean(a.get("api_key")) not in target]
            removed = before - len(self._accounts)
            if self._accounts:
                self._index %= len(self._accounts)
            else:
                self._index = 0
            if removed:
                self._save()
            return {"removed": removed, "total": len(self._accounts)}

    def delete_accounts_by_ids(self, ids: list[str]) -> dict:
        target = {self._clean(i) for i in ids if self._clean(i)}
        with self._lock:
            before = len(self._accounts)
            self._accounts = [
                a for a in self._accounts
                if hashlib.sha1(self._clean(a.get("api_key")).encode()).hexdigest()[:16] not in target
            ]
            removed = before - len(self._accounts)
            if self._accounts:
                self._index %= len(self._accounts)
            else:
                self._index = 0
            if removed:
                self._save()
            return {"removed": removed, "total": len(self._accounts)}

    def mark_result(self, api_key: str, *, success: bool) -> dict | None:
        api_key = self._clean(api_key)
        if not api_key:
            return None
        with self._lock:
            idx = self._find_index(api_key)
            if idx < 0:
                return None
            a = dict(self._accounts[idx])
            a["last_used_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if success:
                a["success"] = int(a.get("success") or 0) + 1
            else:
                a["fail"] = int(a.get("fail") or 0) + 1
            n = self._normalize(a)
            if n is None:
                return None
            self._accounts[idx] = n
            self._save()
            return dict(n)

    def update_status(self, api_key: str, status: str) -> dict | None:
        api_key = self._clean(api_key)
        if not api_key:
            return None
        with self._lock:
            idx = self._find_index(api_key)
            if idx < 0:
                return None
            a = dict(self._accounts[idx])
            a["status"] = self._clean(status) or "正常"
            n = self._normalize(a)
            if n is None:
                return None
            self._accounts[idx] = n
            self._save()
            return dict(n)

    def get_upstream_by_id(self, upstream_id: str) -> dict | None:
        upstream_id = self._clean(upstream_id)
        if not upstream_id:
            return None
        with self._lock:
            for a in self._accounts:
                key = self._clean(a.get("api_key"))
                if hashlib.sha1(key.encode()).hexdigest()[:16] == upstream_id:
                    return dict(a)
        return None

    def get_all_upstreams(self) -> list[dict]:
        with self._lock:
            return [dict(a) for a in self._accounts]
