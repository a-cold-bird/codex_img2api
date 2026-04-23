from __future__ import annotations

from fastapi import HTTPException

from services.account_service import AccountService
from services.config import config
from services.image_service import ImageGenerationError, generate_image


class BackendService:
    def __init__(self, account_service: AccountService):
        self.account_service = account_service

    def generate_with_pool(self, prompt: str, model: str, n: int = 1) -> dict:
        attempted: set[str] = set()
        last_error: Exception | None = None

        while True:
            try:
                upstream = self.account_service.next_upstream(excluded=attempted)
            except RuntimeError as exc:
                if last_error:
                    raise HTTPException(status_code=502, detail={"error": str(last_error)}) from last_error
                raise HTTPException(status_code=503, detail={"error": str(exc)}) from exc

            api_key = upstream["api_key"]
            base_url = upstream["base_url"]
            attempted.add(api_key)

            print(f"[generate] start upstream={base_url} model={model} n={n}")

            all_data: list[dict] = []
            try:
                for _ in range(n):
                    result = generate_image(
                        base_url=base_url,
                        api_key=api_key,
                        prompt=prompt,
                        model=model,
                        timeout=config.request_timeout,
                    )
                    all_data.extend(result.get("data", []))

                self.account_service.mark_result(api_key, success=True)
                print(f"[generate] success upstream={base_url} images={len(all_data)}")
                return {"created": result["created"], "data": all_data}

            except ImageGenerationError as exc:
                self.account_service.mark_result(api_key, success=False)
                last_error = exc
                print(f"[generate] fail upstream={base_url} error={exc}")
                continue
