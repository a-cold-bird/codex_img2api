from __future__ import annotations

import base64
import hashlib
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Event, Thread
from typing import Literal

import requests as http_client

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from services.account_service import AccountService
from services.backend_service import BackendService
from services.config import config, get_auth_key, DATA_DIR
from services.image_service import ImageGenerationError, SUPPORTED_MODELS
from services.image_store import ImageStore
from services.version import get_app_version


account_service = AccountService(DATA_DIR / "accounts.json")
image_store = ImageStore(
    root_dir=config.generated_images_dir,
    index_file=config.generated_images_index_file,
    ttl_seconds=config.image_ttl_seconds,
)

BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIST_DIR = BASE_DIR / "web_dist"


# --- Request models ---

class ImageGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    model: str = "gpt-draw-1024x1536"
    n: int = Field(default=1, ge=1, le=4)
    size: str | None = None
    response_format: str = "b64_json"


class ChatMessage(BaseModel):
    role: str
    content: str | list = ""


class ChatCompletionRequest(BaseModel):
    model: str = "gpt-draw-1024x1536"
    messages: list[ChatMessage] = Field(..., min_length=1)
    n: int = Field(default=1, ge=1, le=4)
    stream: bool = False


class AccountAddRequest(BaseModel):
    upstreams: list[dict] = Field(default_factory=list)


class AccountDeleteRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)


class AccountCheckRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)


# --- Helpers ---

def extract_bearer_token(authorization: str | None) -> str:
    scheme, _, value = str(authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return ""
    return value.strip()


def require_auth_key(authorization: str | None) -> None:
    if extract_bearer_token(authorization) != get_auth_key():
        raise HTTPException(status_code=401, detail={"error": "authorization is invalid"})


def resolve_public_base_url(configured: str, request_base_url: str) -> str:
    base = str(configured or "").strip().rstrip("/")
    if base:
        return base
    return str(request_base_url or "").strip().rstrip("/")


def build_public_image_url(base_url: str, image_id: str) -> str:
    return f"{base_url.rstrip('/')}/files/images/{image_id}"


def persist_generated_images(
    response: dict,
    *,
    prompt: str,
    requested_model: str,
    request_base_url: str,
) -> dict:
    public_base_url = resolve_public_base_url(config.public_base_url, request_base_url)
    for item in response.get("data") or []:
        b64_json = str((item or {}).get("b64_json") or "").strip()
        if not b64_json:
            continue
        image_bytes = base64.b64decode(b64_json)
        metadata = {
            "kind": "generated",
            "prompt": prompt,
            "requested_model": requested_model,
            "revised_prompt": item.get("revised_prompt"),
        }
        record = image_store.save_image_bytes(image_bytes, "image/png", metadata=metadata)
        item["image_id"] = record["image_id"]
        item["url"] = build_public_image_url(public_base_url, record["image_id"])
        item["expires_at"] = record["expires_at"]
    return response


def extract_chat_prompt(messages: list[ChatMessage]) -> str:
    for msg in reversed(messages):
        if msg.role == "user":
            if isinstance(msg.content, str):
                return msg.content.strip()
            if isinstance(msg.content, list):
                parts = []
                for part in msg.content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        parts.append(str(part.get("text", "")))
                    elif isinstance(part, str):
                        parts.append(part)
                return " ".join(parts).strip()
    return ""


def build_model_item(model_id: str) -> dict:
    return {"id": model_id, "object": "model", "created": 0, "owned_by": "img2api"}


def resolve_web_asset(requested_path: str) -> Path | None:
    if not WEB_DIST_DIR.exists():
        return None
    clean_path = requested_path.strip("/")
    if not clean_path:
        candidates = [WEB_DIST_DIR / "index.html"]
    else:
        relative_path = Path(clean_path)
        candidates = [
            WEB_DIST_DIR / relative_path,
            WEB_DIST_DIR / relative_path / "index.html",
            WEB_DIST_DIR / f"{clean_path}.html",
        ]
    for candidate in candidates:
        try:
            candidate.relative_to(WEB_DIST_DIR)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


# --- Background watchers ---

def start_image_cleanup_watcher(stop_event: Event) -> Thread:
    def worker() -> None:
        while not stop_event.is_set():
            try:
                removed = image_store.cleanup_expired()
                if removed:
                    print(f"[image-cleanup] removed={removed}")
            except Exception as exc:
                print(f"[image-cleanup] fail {exc}")
            stop_event.wait(config.image_cleanup_interval_seconds)

    thread = Thread(target=worker, name="image-cleanup", daemon=True)
    thread.start()
    return thread


# --- App factory ---

def create_app() -> FastAPI:
    service = BackendService(account_service)
    app_version = get_app_version()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        stop_event = Event()
        cleanup_thread = start_image_cleanup_watcher(stop_event)
        try:
            yield
        finally:
            stop_event.set()
            cleanup_thread.join(timeout=1)

    app = FastAPI(title="img2api", version=app_version, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    router = APIRouter()

    # --- Model routes ---

    @router.get("/v1/models")
    async def list_models():
        return {
            "object": "list",
            "data": [build_model_item(m) for m in SUPPORTED_MODELS],
        }

    # --- Image generation ---

    @router.post("/v1/images/generations")
    async def generate_images(
        body: ImageGenerationRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        require_auth_key(authorization)
        try:
            response = await run_in_threadpool(
                service.generate_with_pool,
                body.prompt,
                body.model,
                body.n,
            )
            return persist_generated_images(
                response,
                prompt=body.prompt,
                requested_model=body.model,
                request_base_url=str(request.base_url),
            )
        except ImageGenerationError as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

    # --- Chat completions (compatibility) ---

    @router.post("/v1/chat/completions")
    async def chat_completions(
        body: ChatCompletionRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        require_auth_key(authorization)
        prompt = extract_chat_prompt(body.messages)
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "no user message found"})

        try:
            response = await run_in_threadpool(
                service.generate_with_pool,
                prompt,
                body.model,
                body.n,
            )
            persisted = persist_generated_images(
                response,
                prompt=prompt,
                requested_model=body.model,
                request_base_url=str(request.base_url),
            )
        except ImageGenerationError as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        images = persisted.get("data", [])
        content_parts = []
        for img in images:
            url = img.get("url", "")
            if url:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": url},
                })

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content_parts if content_parts else None,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

    # --- Account management ---

    @router.get("/api/accounts")
    async def get_accounts(authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        return {
            "items": account_service.list_accounts(),
            "available": account_service.count_available(),
        }

    @router.post("/api/accounts")
    async def add_accounts(
        body: AccountAddRequest,
        authorization: str | None = Header(default=None),
    ):
        require_auth_key(authorization)
        items = []
        for u in body.upstreams:
            base_url = str(u.get("base_url") or u.get("base-url") or "").strip()
            api_key = str(u.get("api_key") or u.get("api-key") or "").strip()
            if base_url and api_key:
                items.append({"base_url": base_url, "api_key": api_key})
        if not items:
            raise HTTPException(status_code=400, detail={"error": "upstreams is required"})
        result = account_service.add_accounts(items)
        return {**result, "items": account_service.list_accounts()}

    @router.delete("/api/accounts")
    async def delete_accounts(
        body: AccountDeleteRequest,
        authorization: str | None = Header(default=None),
    ):
        require_auth_key(authorization)
        if not body.ids:
            raise HTTPException(status_code=400, detail={"error": "ids is required"})
        result = account_service.delete_accounts_by_ids(body.ids)
        return {**result, "items": account_service.list_accounts()}

    @router.post("/api/accounts/check")
    async def check_accounts(
        body: AccountCheckRequest,
        authorization: str | None = Header(default=None),
    ):
        require_auth_key(authorization)

        def _do_check() -> dict:
            if body.ids:
                upstreams = []
                for uid in body.ids:
                    u = account_service.get_upstream_by_id(uid)
                    if u:
                        upstreams.append(u)
            else:
                upstreams = account_service.get_all_upstreams()

            results = []
            for u in upstreams:
                api_key = str(u.get("api_key") or "").strip()
                base_url = str(u.get("base_url") or "").strip()
                uid = hashlib.sha1(api_key.encode()).hexdigest()[:16]
                start = time.monotonic()
                try:
                    resp = http_client.get(
                        f"{base_url}/v1/models",
                        headers={"Authorization": f"Bearer {api_key}"},
                        timeout=10,
                    )
                    latency_ms = int((time.monotonic() - start) * 1000)
                    if resp.status_code == 200:
                        status = "正常"
                    else:
                        status = "异常"
                except Exception:
                    latency_ms = int((time.monotonic() - start) * 1000)
                    status = "异常"
                account_service.update_status(api_key, status)
                results.append({"id": uid, "status": status, "latency_ms": latency_ms})
            return {"results": results}

        return await run_in_threadpool(_do_check)

    # --- Auth ---

    @router.post("/auth/login")
    async def login(authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        return {"ok": True, "version": app_version}

    @router.get("/version")
    async def get_version():
        return {"version": app_version}

    # --- Image history & files ---

    @router.get("/api/images/history")
    async def get_images_history(
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        require_auth_key(authorization)
        public_base_url = resolve_public_base_url(config.public_base_url, str(request.base_url))
        items = []
        for record in image_store.list_records():
            if str(record.get("kind") or "generated") == "reference":
                continue
            item = dict(record)
            item["url"] = build_public_image_url(public_base_url, str(record.get("image_id") or ""))
            items.append(item)
        return {"items": items}

    @router.get("/files/images/{image_id}")
    async def get_image(image_id: str):
        stored = image_store.get_file_path(image_id)
        if stored is None:
            raise HTTPException(status_code=404, detail={"error": "image not found"})
        file_path, content_type = stored
        return FileResponse(file_path, media_type=content_type)

    app.include_router(router)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_web(full_path: str):
        asset = resolve_web_asset(full_path)
        if asset is not None:
            return FileResponse(asset)
        fallback = resolve_web_asset("")
        if fallback is None:
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(fallback)

    return app
