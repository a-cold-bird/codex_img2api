from __future__ import annotations

import base64
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


def _parse_chat_response(resp: requests.Response, prompt: str) -> dict:
    image_b64 = None
    revised_prompt = None
    chunks: list[str] = []

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

        for choice in data.get("choices", []):
            delta = choice.get("delta", {})
            content = delta.get("content")
            if isinstance(content, str) and content:
                chunks.append(content)
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "image_url":
                            url = (part.get("image_url") or {}).get("url", "")
                            if url.startswith("data:"):
                                b64_part = url.split(",", 1)[-1] if "," in url else ""
                                if b64_part:
                                    image_b64 = b64_part

    full_content = "".join(chunks)

    if not image_b64 and full_content:
        try:
            parsed = json.loads(full_content)
            if isinstance(parsed, dict):
                for item in parsed.get("data", []):
                    b64 = item.get("b64_json", "")
                    if b64:
                        image_b64 = b64
                        revised_prompt = item.get("revised_prompt")
                        break
        except (json.JSONDecodeError, TypeError):
            pass

    if not image_b64:
        try:
            full_resp = resp.json() if not chunks else None
        except Exception:
            full_resp = None
        if full_resp:
            for choice in full_resp.get("choices", []):
                msg = choice.get("message", {})
                content = msg.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "image_url":
                            url = (part.get("image_url") or {}).get("url", "")
                            if url.startswith("data:"):
                                b64_part = url.split(",", 1)[-1] if "," in url else ""
                                if b64_part:
                                    image_b64 = b64_part

    if not image_b64:
        raise ImageGenerationError("no image returned from upstream (chat)")

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
        f"{base_url}/v1/chat/completions",
        api_key,
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        },
        timeout,
    )

    if resp.status_code == 200:
        return _parse_chat_response(resp, prompt)

    if resp.status_code in (404, 405):
        resp = _do_request(
            f"{base_url}/v1/responses",
            api_key,
            {"model": model, "input": prompt, "stream": True},
            timeout,
        )
        if resp.status_code == 200:
            return _parse_responses_sse(resp, prompt)
        body = resp.text[:500]
        raise ImageGenerationError(f"upstream responses returned HTTP {resp.status_code}: {body}")

    body = resp.text[:500]
    raise ImageGenerationError(f"upstream returned HTTP {resp.status_code}: {body}")
