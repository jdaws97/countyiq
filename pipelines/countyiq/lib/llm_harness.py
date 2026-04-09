"""LLM harness for CountyIQ intelligence pipeline.

Supports two backends:
  - llama_cpp: local GGUF inference via llama-cpp-python (dev on 4090, prod on VPS)
  - openrouter: remote inference via OpenRouter API (production prod path)

Per-model-family sampling params and thinking mode enablement:
  - Qwen3.5: soft toggle via /think or /no_think prefix in user message
  - Gemma 4: <|think|> token at start of system prompt
  - Mistral/Ministral: separate Reasoning variant model (no toggle)

Raw LLM outputs are archived to disk on every successful call, so
backfill results survive even if Postgres is lost. Archive path controlled
by COUNTYIQ_ARCHIVE_DIR env var (default: ./archives relative to cwd).
In production (Docker VPS), set COUNTYIQ_ARCHIVE_DIR explicitly to a
mounted volume path like /var/lib/countyiq/archives.
"""
import hashlib
import json
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class HarnessConfig:
    """Configuration for an LLM harness invocation.

    All sampling params default to sensible values but should be
    overridden per-model using MODEL_PRESETS when possible.
    """
    model_path: str  # For llama_cpp: GGUF file path. For openrouter: model slug like "qwen/qwen3.5-9b"
    n_ctx: int = 4096
    n_gpu_layers: int = -1  # -1 = all layers on GPU, 0 = CPU only (llama_cpp only)
    max_tokens: int = 2048

    # Sampling parameters
    temperature: float = 0.7
    top_p: float = 0.95
    top_k: int = 20
    min_p: float = 0.0
    presence_penalty: float = 0.0
    repeat_penalty: float = 1.0

    # Thinking mode control
    thinking: bool = False

    # Model family — "auto" detects from model_path
    # Explicit values: "qwen", "gemma", "mistral", "generic"
    model_family: str = "auto"

    # Backend: "llama_cpp" (local) or "openrouter" (remote API)
    backend: str = "llama_cpp"

    # Archival: None disables, otherwise a label like "pass2" that determines subdirectory
    archive_label: str | None = None

    # Tool calling (OpenRouter only).
    # tools: list of tool definitions in OpenAI function-calling format.
    # tool_handler: callable that takes (tool_name, arguments_dict) and returns a JSON-serializable result.
    # max_tool_iterations: cap on tool-call round trips per invoke() (prevents runaway loops).
    tools: tuple | None = None
    tool_handler: object = None  # callable but can't type frozen dataclass fields with Callable cleanly
    max_tool_iterations: int = 5


class HarnessResult:
    def __init__(self, raw_output: str, parsed: dict | None, success: bool, error: str | None = None):
        self.raw_output = raw_output
        self.parsed = parsed
        self.success = success
        self.error = error


# ----------------------------------------------------------------------
# Model presets — recommended sampling params per model family + mode
#
# Sources:
#   Qwen3.5: https://unsloth.ai/docs/models/qwen3.5
#   Gemma 4: https://unsloth.ai/docs/models/gemma-4
#   Ministral 3: model card on HuggingFace
# ----------------------------------------------------------------------

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
    # DeepSeek V3.2 — docs recommend temp=1.0, top_p=0.95 for local deploy
    "deepseek": {
        "temperature": 1.0, "top_p": 0.95, "top_k": -1,
        "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0,
    },
    # MiMo V2 Flash — temp=0.8 for general, 0.3 for agentic
    "mimo": {
        "temperature": 0.8, "top_p": 0.95, "top_k": -1,
        "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0,
    },
    # Grok 4.1 Fast — default temp 0.7, top_p 0.95
    "grok": {
        "temperature": 0.7, "top_p": 0.95, "top_k": -1,
        "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0,
    },
    # GPT-OSS 120B — MoE with mandatory reasoning; low-temp reasoning profile
    "gpt_oss": {
        "temperature": 0.3, "top_p": 0.95, "top_k": -1,
        "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0,
    },
    # Mercury 2 — diffusion-based reasoning LLM; default temp 0.75
    # Supports reasoning_effort: none/low/medium/high (default medium)
    "mercury": {
        "temperature": 0.75, "top_p": 0.95, "top_k": -1,
        "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0,
    },
    "generic": {
        "temperature": 0.1, "top_p": 0.95, "top_k": 40,
        "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0,
    },
}


def detect_model_family(model_path: str) -> str:
    """Detect model family from filename or model slug.

    Accepts both GGUF filenames (Qwen3.5-9B-Q4_K_M.gguf) and OpenRouter
    slugs (qwen/qwen3.5-9b, deepseek/deepseek-v3.2, xiaomi/mimo-v2-flash).
    """
    name = model_path.lower()  # Use full path/slug, not just basename
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


def get_preset_for_model(model_path: str, thinking: bool = False, reasoning_task: bool = True) -> dict:
    """Return the recommended sampling preset for a model + mode."""
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


# ----------------------------------------------------------------------
# Raw output archival — protects backfill investment
# ----------------------------------------------------------------------

def _archive_dir() -> Path:
    """Directory for raw LLM output archives.

    Resolution order:
      1. COUNTYIQ_ARCHIVE_DIR env var (recommended for production)
      2. ./archives relative to the current working directory (dev default)
    """
    env_dir = os.environ.get("COUNTYIQ_ARCHIVE_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.cwd() / "archives"


def archive_raw_output(label: str, key: str, prompt: str, raw_output: str, metadata: dict | None = None) -> str | None:
    """Archive a single LLM call's raw output to disk.

    Files are organized as:
        {archive_dir}/{label}/{YYYY-MM-DD}/{key_hash}_{timestamp}.json

    Returns the path written, or None if archival is disabled/failed.
    """
    try:
        archive_root = _archive_dir()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        subdir = archive_root / label / today
        subdir.mkdir(parents=True, exist_ok=True)

        # Hash the key so arbitrary identifiers (including :signal_key suffixes)
        # produce a safe filename
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
        timestamp = datetime.now(timezone.utc).strftime("%H%M%S_%f")
        filename = f"{key_hash}_{timestamp}.json"

        record = {
            "label": label,
            "key": key,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "prompt": prompt,
            "raw_output": raw_output,
            "metadata": metadata or {},
        }

        path = subdir / filename
        path.write_text(json.dumps(record, default=str))
        return str(path)
    except Exception:
        # Archival must never break the main flow
        return None


# ----------------------------------------------------------------------
# llama.cpp backend (local inference)
# ----------------------------------------------------------------------

_model_cache: dict[tuple, object] = {}


def get_model(config: HarnessConfig):
    """Get or create a cached Llama model instance.

    Cache key includes model_path, n_ctx, and n_gpu_layers so that
    loading the same model with a different context size (e.g., Pass 0
    at 4096 vs Pass 4 at 8192) creates separate instances.
    """
    cache_key = (config.model_path, config.n_ctx, config.n_gpu_layers)
    if cache_key not in _model_cache:
        from llama_cpp import Llama  # lazy import — only needed at runtime
        _model_cache[cache_key] = Llama(
            model_path=config.model_path,
            n_ctx=config.n_ctx,
            n_gpu_layers=config.n_gpu_layers,
            verbose=False,
        )
    return _model_cache[cache_key]


def strip_thinking(text: str | None) -> str:
    """Strip thinking/thought blocks from model output. Safe against None."""
    if not text:
        return ""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<\|think\|>.*?<\|/think\|>", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


def extract_json_object(text: str) -> str:
    """Best-effort extraction of the first JSON object from text.

    Some models (especially Qwen3.5 in non-thinking mode) emit a 'Thinking
    Process:' preamble before the actual JSON despite instructions. This
    helper finds the outermost {...} block using bracket counting.
    """
    if not text:
        return text

    start = text.find("{")
    if start == -1:
        return text  # No JSON found, return as-is so caller sees original error

    # Walk forward counting brackets, skipping strings
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
    return text  # Unmatched braces, return original


def _build_messages(
    config: HarnessConfig,
    prompt: str,
    image_path: str | None,
    pdf_bytes: bytes | None = None,
) -> list:
    """Build the messages array with per-model-family thinking control."""
    family = config.model_family if config.model_family != "auto" else detect_model_family(config.model_path)

    messages = []
    user_prompt = prompt

    # Gemma 4: thinking via system message token
    if family == "gemma" and config.thinking:
        messages.append({
            "role": "system",
            "content": "<|think|>\nYou are a careful real estate intelligence analyst. Think through the evidence carefully before producing your answer in the required JSON format.",
        })

    # Qwen3.5: thinking via /think or /no_think soft toggle
    if family == "qwen":
        if config.thinking:
            user_prompt = "/think\n\n" + prompt
        else:
            user_prompt = "/no_think\n\n" + prompt

    # Build user message (with optional PDF, image, or text-only)
    if pdf_bytes:
        import base64 as b64mod
        pdf_b64 = b64mod.b64encode(pdf_bytes).decode("utf-8")
        messages.append({
            "role": "user",
            "content": [
                {"type": "file", "file": {"filename": "document.pdf", "data": f"data:application/pdf;base64,{pdf_b64}"}},
                {"type": "text", "text": user_prompt},
            ],
        })
    elif image_path:
        import base64  # lazy import
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        messages.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                {"type": "text", "text": user_prompt},
            ],
        })
    else:
        messages.append({"role": "user", "content": user_prompt})

    return messages


def _invoke_llama_cpp(config: HarnessConfig, prompt: str, image_path: str | None) -> tuple[str, str | None]:
    """Invoke local llama.cpp model. Returns (raw_output, error)."""
    model = get_model(config)
    messages = _build_messages(config, prompt, image_path)

    try:
        response = model.create_chat_completion(
            messages=messages,
            temperature=config.temperature,
            top_p=config.top_p,
            top_k=config.top_k,
            min_p=config.min_p,
            presence_penalty=config.presence_penalty,
            repeat_penalty=config.repeat_penalty,
            max_tokens=config.max_tokens,
            response_format={"type": "json_object"},
        )
        raw_output = response["choices"][0]["message"]["content"]
        return raw_output, None
    except Exception as exc:
        return "", str(exc)


# ----------------------------------------------------------------------
# OpenRouter backend (remote inference)
# ----------------------------------------------------------------------

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Rate-limit backoff configuration
_BACKOFF_MAX_ATTEMPTS = 5        # per-HTTP-call attempts before giving up
_BACKOFF_BASE_SECONDS = 2.0      # exponential base: 2, 4, 8, 16, 32 (capped)
_BACKOFF_CAP_SECONDS = 60.0      # never sleep longer than this


def _post_with_backoff(url: str, json_payload: dict, headers: dict, timeout: int):
    """POST to OpenRouter with exponential backoff on 429 and 5xx.

    Honors the Retry-After header when present. Raises on non-retryable
    errors or after exhausting attempts. Returns the requests.Response.
    """
    import requests

    last_resp = None
    for attempt in range(_BACKOFF_MAX_ATTEMPTS):
        resp = requests.post(url, json=json_payload, headers=headers, timeout=timeout)
        last_resp = resp

        # Success: return immediately
        if resp.status_code < 400:
            return resp

        # Retryable: 429 (rate limit) or any 5xx server error
        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            # If this was the last attempt, fall through to raise_for_status
            if attempt == _BACKOFF_MAX_ATTEMPTS - 1:
                break
            # Honor Retry-After header if present
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                try:
                    wait = float(retry_after)
                except ValueError:
                    wait = _BACKOFF_BASE_SECONDS ** (attempt + 1)
            else:
                wait = _BACKOFF_BASE_SECONDS ** (attempt + 1)
            wait = min(wait, _BACKOFF_CAP_SECONDS)
            # Full jitter
            wait = random.uniform(0, wait)
            time.sleep(wait)
            continue

        # Non-retryable (4xx other than 429) — raise immediately
        resp.raise_for_status()

    # Exhausted retries — raise from the last response
    if last_resp is not None:
        last_resp.raise_for_status()
    raise RuntimeError("backoff loop exited without response")


def _invoke_openrouter(config: HarnessConfig, prompt: str, image_path: str | None, pdf_bytes: bytes | None = None) -> tuple[str, str | None]:
    """Invoke OpenRouter API. Returns (raw_output, error).

    Handles:
      - Model-specific thinking mode enablement
      - Tool calling loop (if config.tools + config.tool_handler are set)
      - Rate-limit backoff on 429 and 5xx (exponential with Retry-After)
      - Explicit truncation error on finish_reason='length' (avoids wasting
        retry budget on a deterministic JSON parse failure)
      - Response parsing with fallback for reasoning_content field
    """
    import requests

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return "", "OPENROUTER_API_KEY not set"

    family = config.model_family if config.model_family != "auto" else detect_model_family(config.model_path)
    messages = _build_messages(config, prompt, image_path, pdf_bytes=pdf_bytes)

    payload = {
        "model": config.model_path,  # For openrouter backend, model_path is the model slug
        "messages": messages,
        "temperature": config.temperature,
        "top_p": config.top_p,
        "max_tokens": config.max_tokens,
        "response_format": {"type": "json_object"},
    }

    # Generic sampling params (if provider supports)
    if config.top_k > 0:
        payload["top_k"] = config.top_k
    if config.min_p > 0:
        payload["min_p"] = config.min_p
    if config.presence_penalty != 0:
        payload["presence_penalty"] = config.presence_penalty
    if config.repeat_penalty != 1.0:
        payload["frequency_penalty"] = config.repeat_penalty - 1.0

    # Model-specific thinking mode enablement via API parameters
    if family == "mimo":
        payload["chat_template_kwargs"] = {"enable_thinking": config.thinking}
    elif family == "deepseek":
        if config.thinking:
            payload["chat_template_kwargs"] = {"thinking_mode": "thinking"}
    elif family == "grok":
        payload["reasoning"] = {"enabled": config.thinking}
    elif family == "gpt_oss":
        payload["reasoning_effort"] = "high"
    elif family == "mercury":
        # Mercury 2: reasoning_effort with none/low/medium/high (default medium)
        # Use "high" when thinking=True, "medium" when False
        payload["reasoning"] = {
            "effort": "high" if config.thinking else "medium"
        }

    # Tool calling (OpenAI function-calling format)
    if config.tools and config.tool_handler:
        payload["tools"] = list(config.tools)
        payload["tool_choice"] = "auto"
        # When tools are in play, we can't force response_format=json_object
        # because the model needs the freedom to emit tool_calls OR content.
        payload.pop("response_format", None)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://countyiq.local",
        "X-Title": "CountyIQ Intelligence Pipeline",
    }

    tool_handler = config.tool_handler
    resp = None

    try:
        # Tool-calling loop: keep round-tripping until the model stops asking
        # for tool calls or we hit the iteration cap.
        for iteration in range(config.max_tool_iterations):
            resp = _post_with_backoff(OPENROUTER_URL, payload, headers, timeout=180)
            data = resp.json()
            choice = data["choices"][0]
            message = choice["message"]
            finish = choice.get("finish_reason", "unknown")

            # If the model called tools, execute them and continue the loop
            tool_calls = message.get("tool_calls") or []
            if tool_calls and tool_handler:
                # Append the assistant message (with tool_calls) to conversation
                payload["messages"].append({
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": tool_calls,
                })
                # Execute each tool and append results
                for tc in tool_calls:
                    tc_id = tc.get("id")
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    try:
                        fn_args = json.loads(fn.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        fn_args = {}
                    try:
                        tool_result = tool_handler(fn_name, fn_args)
                    except Exception as tool_exc:
                        tool_result = {"error": f"tool execution failed: {tool_exc}"}
                    payload["messages"].append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "name": fn_name,
                        "content": json.dumps(tool_result, default=str),
                    })
                # Continue loop for next model turn
                continue

            # No tool calls — extract the final content
            raw_output = message.get("content") or ""
            if not raw_output and "reasoning" in message:
                raw_output = message["reasoning"] or ""
            if not raw_output and "reasoning_content" in message:
                raw_output = message["reasoning_content"] or ""

            # Truncation detection: if the model hit max_tokens, the output
            # is almost certainly incomplete JSON. Return an explicit error
            # so invoke_with_retry doesn't waste attempts on a deterministic
            # parse failure.
            if finish == "length":
                return raw_output, (
                    f"Response truncated at max_tokens={config.max_tokens} "
                    f"(finish_reason=length)"
                )

            if not raw_output:
                return "", f"Empty response content (finish_reason={finish})"

            return raw_output, None

        # Hit iteration cap without a final response
        return "", f"Tool call loop exceeded {config.max_tool_iterations} iterations"

    except requests.exceptions.HTTPError as exc:
        body = resp.text[:500] if resp is not None else ""
        return "", f"HTTP error: {exc} | body: {body}"
    except requests.exceptions.Timeout:
        return "", "Request timeout (180s)"
    except (KeyError, IndexError) as exc:
        return "", f"Unexpected response format: {exc}"
    except Exception as exc:
        return "", str(exc)


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def invoke(
    config: HarnessConfig,
    prompt: str,
    image_path: str | None = None,
    archive_key: str | None = None,
    pdf_bytes: bytes | None = None,
) -> HarnessResult:
    """Invoke the LLM via the configured backend.

    Args:
        config: HarnessConfig specifying backend, model, sampling params.
        prompt: Full prompt text.
        image_path: Optional image path for multimodal vision input.
        archive_key: Optional identifier for archival (e.g., pidn or cluster_id).
                     Required if config.archive_label is set.
        pdf_bytes: Optional raw PDF bytes. Sent as a file content block to
                   models that support native PDF input (e.g., Grok 4.1).

    Returns:
        HarnessResult with parsed JSON output or error details.
    """
    t_start = time.time()

    # Dispatch to backend
    if config.backend == "openrouter":
        raw_output, error = _invoke_openrouter(config, prompt, image_path, pdf_bytes=pdf_bytes)
    else:
        raw_output, error = _invoke_llama_cpp(config, prompt, image_path)

    elapsed_ms = int((time.time() - t_start) * 1000)

    # Archive raw output if labeled (regardless of parse success)
    if config.archive_label and archive_key and raw_output:
        archive_raw_output(
            label=config.archive_label,
            key=archive_key,
            prompt=prompt,
            raw_output=raw_output,
            metadata={
                "model": config.model_path,
                "backend": config.backend,
                "temperature": config.temperature,
                "thinking": config.thinking,
                "elapsed_ms": elapsed_ms,
                "error": error,
            },
        )

    if error:
        return HarnessResult(raw_output=raw_output, parsed=None, success=False, error=error)

    # Strip thinking blocks before parsing — we want only the final answer
    clean_output = strip_thinking(raw_output)

    # Try direct parse first
    try:
        parsed = json.loads(clean_output)
        return HarnessResult(raw_output=raw_output, parsed=parsed, success=True)
    except json.JSONDecodeError:
        pass

    # Fallback: extract first {...} block (handles "Thinking Process:\n{...}" prefixes)
    extracted = extract_json_object(clean_output)
    try:
        parsed = json.loads(extracted)
        return HarnessResult(raw_output=raw_output, parsed=parsed, success=True)
    except json.JSONDecodeError as e:
        return HarnessResult(raw_output=raw_output, parsed=None, success=False, error=f"JSON parse error: {e}")


def invoke_with_retry(
    config: HarnessConfig,
    prompt: str,
    image_path: str | None = None,
    retries: int = 1,
    archive_key: str | None = None,
    pdf_bytes: bytes | None = None,
) -> HarnessResult:
    """Invoke with retry on failure."""
    result = invoke(config, prompt, image_path, archive_key=archive_key, pdf_bytes=pdf_bytes)
    if result.success:
        return result
    for _ in range(retries):
        result = invoke(config, prompt, image_path, archive_key=archive_key, pdf_bytes=pdf_bytes)
        if result.success:
            return result
    return result
