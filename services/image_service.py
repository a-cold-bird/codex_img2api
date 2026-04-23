from __future__ import annotations

import json
import random
import time

import requests


DRAW_MODELS = ("gpt-draw-1024x1024", "gpt-draw-1024x1536", "gpt-draw-1536x1024")
SUPPORTED_MODELS = (*DRAW_MODELS, "gpt-image-2")


class ImageGenerationError(Exception):
    pass


def validate_model(model: str) -> str:
    normalized = str(model or "").strip() or DRAW_MODELS[0]
    if normalized == "gpt-image-2":
        normalized = random.choice(DRAW_MODELS)
    if normalized not in DRAW_MODELS:
        raise ImageGenerationError(f"unsupported model: {normalized}, must be one of {SUPPORTED_MODELS}")
    return normalized


def _do_request(url: str, api_key: str, body: dict, timeout: int) -> requests.Response:
    try:
        return requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
            stream=True,
            timeout=timeout,
        )
    except requests.exceptions.Timeout:
        raise ImageGenerationError(f"upstream request timed out ({timeout}s)")
    except requests.exceptions.ConnectionError as exc:
        raise ImageGenerationError(f"upstream connection failed: {exc}") from exc


def _parse_responses_sse(resp: requests.Response, prompt: str) -> dict:
    image_b64 = None
    revised_prompt = None

    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data_str = line[6:]
        if data_str.strip() == "[DONE]":
            break
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        event_type = data.get("type", "")
        if event_type == "response.output_item.done":
            item = data.get("item", {})
            if item.get("type") == "image_generation_call" and item.get("result"):
                image_b64 = item["result"]
        if event_type == "response.output_text.done":
            text = data.get("text", "")
            if text:
                revised_prompt = text

    if not image_b64:
        raise ImageGenerationError("no image returned from upstream")

    return {
        "created": int(time.time()),
        "data": [{"b64_json": image_b64, "revised_prompt": revised_prompt or prompt}],
    }


def generate_image(
    base_url: str,
    api_key: str,
    prompt: str,
    model: str,
    timeout: int = 300,
) -> dict:
    model = validate_model(model)
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ImageGenerationError("prompt is required")

    resp = _do_request(
        f"{base_url}/v1/responses",
        api_key,
        {"model": model, "input": prompt, "stream": True},
        timeout,
    )

    if resp.status_code != 200:
        body = resp.text[:500]
        raise ImageGenerationError(f"upstream returned HTTP {resp.status_code}: {body}")

    return _parse_responses_sse(resp, prompt)
