"""OpenRouter-only LLM harness for the CountyIQ intelligence pipeline.

The harness keeps pass assets thin and consistent:
  - OpenRouter transport with rate-limit backoff
  - model-family presets and thinking toggles
  - native PDF input for Pass 0
  - JSON cleanup / extraction
  - raw-output archiving
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_BACKOFF_MAX_ATTEMPTS = 5
_BACKOFF_BASE_SECONDS = 2.0
_BACKOFF_CAP_SECONDS = 60.0
_DEFAULT_INLINE_PDF_MAX_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class HarnessConfig:
    """Configuration for one OpenRouter invocation."""

    model_path: str
    n_ctx: int = 4096
    max_tokens: int = 2048
    temperature: float = 0.7
    top_p: float = 0.95
    top_k: int = 20
    min_p: float = 0.0
    presence_penalty: float = 0.0
    repeat_penalty: float = 1.0
    thinking: bool = False
    model_family: str = "auto"
    archive_label: str | None = None


@dataclass(frozen=True)
class HarnessResult:
    raw_output: str
    parsed: dict | None
    success: bool
    error: str | None = None


MODEL_PRESETS = {
    "qwen_thinking": {
        "temperature": 1.0, "top_p": 0.95, "top_k": 20,
        "min_p": 0.0, "presence_penalty": 1.5, "repeat_penalty": 1.0,
    },
    "qwen_nothink_reasoning": {
        "temperature": 1.0, "top_p": 0.95, "top_k": 20,
        "min_p": 0.0, "presence_penalty": 1.5, "repeat_penalty": 1.0,
    },
    "qwen_nothink_general": {
        "temperature": 0.7, "top_p": 0.8, "top_k": 20,
        "min_p": 0.0, "presence_penalty": 1.5, "repeat_penalty": 1.0,
    },
    "gemma": {
        "temperature": 1.0, "top_p": 0.95, "top_k": 64,
        "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0,
    },
    "ministral_instruct": {
        "temperature": 0.05, "top_p": 1.0, "top_k": -1,
        "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0,
    },
    "ministral_reasoning": {
        "temperature": 0.05, "top_p": 1.0, "top_k": -1,
        "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0,
    },
    "deepseek": {
        "temperature": 1.0, "top_p": 0.95, "top_k": -1,
        "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0,
    },
    "mimo": {
        "temperature": 0.8, "top_p": 0.95, "top_k": -1,
        "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0,
    },
    "grok": {
        "temperature": 0.7, "top_p": 0.95, "top_k": -1,
        "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0,
    },
    "gpt_oss": {
        "temperature": 0.3, "top_p": 0.95, "top_k": -1,
        "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0,
    },
    "mercury": {
        "temperature": 0.75, "top_p": 0.95, "top_k": -1,
        "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0,
    },
    "generic": {
        "temperature": 0.1, "top_p": 0.95, "top_k": 40,
        "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0,
    },
}


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def inline_pdf_max_bytes() -> int:
    """Return the max raw PDF size allowed for inline OpenRouter uploads."""
    return max(_int_env("COUNTYIQ_PASS0_MAX_PDF_BYTES", _DEFAULT_INLINE_PDF_MAX_BYTES), 0)


def validate_inline_pdf_size(pdf_bytes: bytes | None) -> None:
    """Reject oversized PDFs before we base64-expand them into the payload."""
    if pdf_bytes is None:
        return

    limit = inline_pdf_max_bytes()
    if limit <= 0:
        return

    size = len(pdf_bytes)
    if size > limit:
        raise ValueError(
            "PDF too large for inline upload: "
            f"{size} bytes exceeds COUNTYIQ_PASS0_MAX_PDF_BYTES={limit}"
        )


def detect_model_family(model_path: str) -> str:
    """Detect the model family from an OpenRouter model slug."""
    name = model_path.lower()
    if "mercury" in name:
        return "mercury"
    if "gpt-oss" in name or "gpt_oss" in name:
        return "gpt_oss"
    if "deepseek" in name:
        return "deepseek"
    if "mimo" in name:
        return "mimo"
    if "grok" in name:
        return "grok"
    if "qwen" in name:
        return "qwen"
    if "gemma" in name:
        return "gemma"
    if "ministral" in name or "mistral" in name:
        return "mistral"
    return "generic"


def get_preset_for_model(
    model_path: str,
    thinking: bool = False,
    reasoning_task: bool = True,
) -> dict:
    """Return the recommended sampling preset for a model."""
    family = detect_model_family(model_path)
    name = model_path.lower()

    if family == "qwen":
        if thinking:
            return MODEL_PRESETS["qwen_thinking"]
        return MODEL_PRESETS["qwen_nothink_reasoning" if reasoning_task else "qwen_nothink_general"]
    if family == "gemma":
        return MODEL_PRESETS["gemma"]
    if family == "mistral":
        if "reasoning" in name:
            return MODEL_PRESETS["ministral_reasoning"]
        return MODEL_PRESETS["ministral_instruct"]
    if family == "deepseek":
        return MODEL_PRESETS["deepseek"]
    if family == "mimo":
        return MODEL_PRESETS["mimo"]
    if family == "grok":
        return MODEL_PRESETS["grok"]
    if family == "gpt_oss":
        return MODEL_PRESETS["gpt_oss"]
    if family == "mercury":
        return MODEL_PRESETS["mercury"]
    return MODEL_PRESETS["generic"]


def _archive_dir() -> Path:
    env_dir = os.environ.get("COUNTYIQ_ARCHIVE_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.cwd() / "archives"


def archive_raw_output(
    label: str,
    key: str,
    prompt: str,
    raw_output: str,
    metadata: dict | None = None,
) -> str | None:
    """Archive one LLM call's raw output to disk."""
    try:
        archive_root = _archive_dir()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        subdir = archive_root / label / today
        subdir.mkdir(parents=True, exist_ok=True)

        key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
        timestamp = datetime.now(timezone.utc).strftime("%H%M%S_%f")
        path = subdir / f"{key_hash}_{timestamp}.json"
        record = {
            "label": label,
            "key": key,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "prompt": prompt,
            "raw_output": raw_output,
            "metadata": metadata or {},
        }
        path.write_text(json.dumps(record, default=str))
        return str(path)
    except Exception:
        return None


def strip_thinking(text: str | None) -> str:
    """Strip reasoning blocks from model output."""
    if not text:
        return ""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<\|think\|>.*?<\|/think\|>", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


def extract_json_object(text: str) -> str:
    """Best-effort extraction of the first JSON object from text."""
    if not text:
        return text

    start = text.find("{")
    if start == -1:
        return text

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text


def _build_messages(
    config: HarnessConfig,
    prompt: str,
    pdf_bytes: bytes | None = None,
) -> list[dict]:
    """Build OpenRouter messages with family-specific thinking controls."""
    family = config.model_family if config.model_family != "auto" else detect_model_family(config.model_path)
    messages: list[dict] = []
    user_prompt = prompt

    if family == "gemma" and config.thinking:
        messages.append(
            {
                "role": "system",
                "content": (
                    "<|think|>\nYou are a careful real estate intelligence analyst. "
                    "Think through the evidence carefully before producing your "
                    "answer in the required JSON format."
                ),
            }
        )

    if family == "qwen":
        user_prompt = ("/think\n\n" if config.thinking else "/no_think\n\n") + prompt

    if pdf_bytes:
        validate_inline_pdf_size(pdf_bytes)
        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "filename": "document.pdf",
                            "file_data": f"data:application/pdf;base64,{pdf_b64}",
                        },
                    },
                    {"type": "text", "text": user_prompt},
                ],
            }
        )
    else:
        messages.append({"role": "user", "content": user_prompt})

    return messages


def _post_with_backoff(url: str, json_payload: dict, headers: dict, timeout: int):
    """POST to OpenRouter with retry/backoff on 429 and 5xx."""
    import requests

    last_resp = None
    for attempt in range(_BACKOFF_MAX_ATTEMPTS):
        resp = requests.post(url, json=json_payload, headers=headers, timeout=timeout)
        last_resp = resp

        if resp.status_code < 400:
            return resp

        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            if attempt == _BACKOFF_MAX_ATTEMPTS - 1:
                break
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                try:
                    wait = float(retry_after)
                except ValueError:
                    wait = _BACKOFF_BASE_SECONDS ** (attempt + 1)
            else:
                wait = _BACKOFF_BASE_SECONDS ** (attempt + 1)
            wait = min(wait, _BACKOFF_CAP_SECONDS)
            time.sleep(random.uniform(0, wait))
            continue

        resp.raise_for_status()

    if last_resp is not None:
        last_resp.raise_for_status()
    raise RuntimeError("backoff loop exited without response")


def _invoke_openrouter(
    config: HarnessConfig,
    prompt: str,
    pdf_bytes: bytes | None = None,
) -> tuple[str, str | None]:
    """Invoke OpenRouter and return (raw_output, error)."""
    import requests

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return "", "OPENROUTER_API_KEY not set"

    family = config.model_family if config.model_family != "auto" else detect_model_family(config.model_path)
    payload = {
        "model": config.model_path,
        "messages": _build_messages(config, prompt, pdf_bytes=pdf_bytes),
        "temperature": config.temperature,
        "top_p": config.top_p,
        "max_tokens": config.max_tokens,
        "response_format": {"type": "json_object"},
    }

    if config.top_k > 0:
        payload["top_k"] = config.top_k
    if config.min_p > 0:
        payload["min_p"] = config.min_p
    if config.presence_penalty != 0:
        payload["presence_penalty"] = config.presence_penalty
    if config.repeat_penalty != 1.0:
        payload["frequency_penalty"] = config.repeat_penalty - 1.0

    if family == "mimo":
        payload["chat_template_kwargs"] = {"enable_thinking": config.thinking}
    elif family == "deepseek" and config.thinking:
        payload["chat_template_kwargs"] = {"thinking_mode": "thinking"}
    elif family == "grok":
        payload["reasoning"] = {"enabled": config.thinking}
    elif family == "gpt_oss":
        payload["reasoning_effort"] = "high"
    elif family == "mercury":
        payload["reasoning"] = {"effort": "high" if config.thinking else "medium"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://countyiq.local",
        "X-Title": "CountyIQ Intelligence Pipeline",
    }

    resp = None
    try:
        resp = _post_with_backoff(OPENROUTER_URL, payload, headers, timeout=180)
        data = resp.json()
        choice = data["choices"][0]
        message = choice["message"]
        finish = choice.get("finish_reason", "unknown")

        raw_output = message.get("content") or ""
        if not raw_output and "reasoning" in message:
            raw_output = message["reasoning"] or ""
        if not raw_output and "reasoning_content" in message:
            raw_output = message["reasoning_content"] or ""

        if finish == "length":
            return raw_output, (
                f"Response truncated at max_tokens={config.max_tokens} "
                f"(finish_reason=length)"
            )
        if not raw_output:
            return "", f"Empty response content (finish_reason={finish})"
        return raw_output, None
    except requests.exceptions.HTTPError as exc:
        body = resp.text[:500] if resp is not None else ""
        return "", f"HTTP error: {exc} | body: {body}"
    except requests.exceptions.Timeout:
        return "", "Request timeout (180s)"
    except (KeyError, IndexError) as exc:
        return "", f"Unexpected response format: {exc}"
    except Exception as exc:
        return "", str(exc)


def invoke(
    config: HarnessConfig,
    prompt: str,
    archive_key: str | None = None,
    pdf_bytes: bytes | None = None,
) -> HarnessResult:
    """Invoke OpenRouter and return parsed JSON or an error."""
    started = time.time()
    raw_output, error = _invoke_openrouter(config, prompt, pdf_bytes=pdf_bytes)
    elapsed_ms = int((time.time() - started) * 1000)

    if config.archive_label and archive_key and raw_output:
        archive_raw_output(
            label=config.archive_label,
            key=archive_key,
            prompt=prompt,
            raw_output=raw_output,
            metadata={
                "model": config.model_path,
                "temperature": config.temperature,
                "thinking": config.thinking,
                "elapsed_ms": elapsed_ms,
                "error": error,
            },
        )

    if error:
        return HarnessResult(raw_output=raw_output, parsed=None, success=False, error=error)

    clean_output = strip_thinking(raw_output)
    try:
        return HarnessResult(raw_output=raw_output, parsed=json.loads(clean_output), success=True)
    except json.JSONDecodeError:
        pass

    extracted = extract_json_object(clean_output)
    try:
        return HarnessResult(raw_output=raw_output, parsed=json.loads(extracted), success=True)
    except json.JSONDecodeError as exc:
        return HarnessResult(
            raw_output=raw_output,
            parsed=None,
            success=False,
            error=f"JSON parse error: {exc}",
        )


def invoke_with_retry(
    config: HarnessConfig,
    prompt: str,
    retries: int = 1,
    archive_key: str | None = None,
    pdf_bytes: bytes | None = None,
) -> HarnessResult:
    """Invoke OpenRouter with a small retry budget."""
    result = invoke(config, prompt, archive_key=archive_key, pdf_bytes=pdf_bytes)
    if result.success:
        return result

    for _ in range(retries):
        result = invoke(config, prompt, archive_key=archive_key, pdf_bytes=pdf_bytes)
        if result.success:
            return result
    return result
