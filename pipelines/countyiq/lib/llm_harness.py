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
import dataclasses
import hashlib
import json
import logging
import os
import random
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

_telemetry_log = logging.getLogger("countyiq.llm")


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_BACKOFF_MAX_ATTEMPTS = 5
_BACKOFF_BASE_SECONDS = 2.0
_BACKOFF_CAP_SECONDS = 60.0
_DEFAULT_INLINE_PDF_MAX_BYTES = 8 * 1024 * 1024
_DEFAULT_LLM_ARCHIVE_RETENTION_DAYS = 90
_ARCHIVE_FILENAME_RE = re.compile(r"^[0-9a-f]{16}_\d{6}_\d{6}\.json$")
_ARCHIVE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_last_archive_prune_date: str | None = None


@dataclass(frozen=True)
class HarnessConfig:
    """Configuration for one OpenRouter invocation."""

    model_path: str
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
    # Explicit OpenRouter reasoning effort; supported values depend on the model.
    # When set, it overrides the family-derived thinking heuristics —
    # exp H showed "low" wins on Pass 2 and higher efforts just burn
    # output tokens. None = keep the per-family default behavior.
    reasoning_effort: str | None = None
    # Strict structured output: when set, response_format becomes
    # json_schema with strict=true (instead of bare json_object) and
    # provider routing requires endpoints that support it. Fail closed unless
    # schema fallback is explicitly enabled for a separately evaluated workflow.
    json_schema: dict | None = None
    schema_name: str = "response"
    allow_schema_fallback: bool = False
    # Static instruction block emitted as a system message — providers
    # with implicit prompt caching (OpenAI, DeepSeek, Gemini, ...) can
    # cache it across calls when it stays byte-identical.
    system_prompt: str | None = None
    # Provider routing preferences (docs: openrouter.ai provider-routing).
    # max_price units are $/M tokens; they guard against promotional
    # prices expiring into a silently larger bill.
    require_parameters: bool = False
    max_price_prompt: float | None = None
    max_price_completion: float | None = None
    zdr: bool = False
    # Restrict routing to providers serving these quantizations (e.g.
    # ("fp8", "bf16", "fp16")). Needed where OpenRouter's cheapest
    # providers serve degraded FP4/NVFP4 weights — documented for GLM-5.2
    # (multi-byte decode failures on FP4 hosts; see docs/decisions.md).
    provider_quantizations: tuple[str, ...] | None = None
    provider_only: tuple[str, ...] | None = None
    provider_order: tuple[str, ...] | None = None
    provider_allow_fallbacks: bool | None = None
    # PDF parsing engine pinned for inline file uploads. Unpinned PDFs can
    # silently route to OpenRouter's OCR parser at ~$2/1,000 pages (the
    # cost trap in docs/cost.md); "native" sends the file to the model's
    # own file input at ordinary token pricing. Only emitted when a PDF is
    # actually attached.
    pdf_engine: str | None = None


@dataclass(frozen=True)
class HarnessResult:
    raw_output: str
    parsed: dict | None
    success: bool
    error: str | None = None
    # Provider-returned usage/cost metadata plus local timing. Keeping this on
    # the result lets evals enforce a run budget instead of scraping logs or
    # trusting a stale price sheet.
    metadata: dict = dataclasses.field(default_factory=dict)


MODEL_PRESETS = {
    "qwen_thinking": {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "repeat_penalty": 1.0,
    },
    "qwen_nothink_reasoning": {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "repeat_penalty": 1.0,
    },
    "qwen_nothink_general": {
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "repeat_penalty": 1.0,
    },
    "gemma": {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 64,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
    },
    "ministral_instruct": {
        "temperature": 0.05,
        "top_p": 1.0,
        "top_k": -1,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
    },
    "ministral_reasoning": {
        "temperature": 0.05,
        "top_p": 1.0,
        "top_k": -1,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
    },
    "deepseek": {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": -1,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
    },
    # GLM-5.3-Flash publisher/OpenRouter defaults, verified 2026-09-05.
    # Do not impose the generic family's unvalidated top-k/temperature.
    "glm_flash": {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": -1,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
    },
    "mimo": {
        "temperature": 0.8,
        "top_p": 0.95,
        "top_k": -1,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
    },
    "grok": {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": -1,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
    },
    "gpt_oss": {
        "temperature": 0.3,
        "top_p": 0.95,
        "top_k": -1,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
    },
    "mercury": {
        "temperature": 0.75,
        "top_p": 0.95,
        "top_k": -1,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
    },
    # OpenAI reasoning endpoints (gpt-5.x) accept NO sampling parameters —
    # the OpenRouter listing for gpt-5.6-luna exposes only max_tokens,
    # reasoning, response_format, structured_outputs, seed, tools (verified
    # 2026-08-06). Neutral values here; build_openrouter_payload omits
    # temperature/top_p entirely for this family.
    "openai": {
        "temperature": 1.0,
        "top_p": 1.0,
        "top_k": -1,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
    },
    "generic": {
        "temperature": 0.1,
        "top_p": 0.95,
        "top_k": 40,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
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
    return max(
        _int_env("COUNTYIQ_PASS0_MAX_PDF_BYTES", _DEFAULT_INLINE_PDF_MAX_BYTES), 0
    )


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
    if name.startswith("z-ai/glm-5.3-flash"):
        return "glm_flash"
    if "mercury" in name:
        return "mercury"
    if "gpt-oss" in name or "gpt_oss" in name:
        return "gpt_oss"
    if name.startswith("openai/") or "gpt-5" in name or "gpt-4" in name:
        return "openai"
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
        return MODEL_PRESETS[
            "qwen_nothink_reasoning" if reasoning_task else "qwen_nothink_general"
        ]
    if family == "gemma":
        return MODEL_PRESETS["gemma"]
    if family == "mistral":
        if "reasoning" in name:
            return MODEL_PRESETS["ministral_reasoning"]
        return MODEL_PRESETS["ministral_instruct"]
    if family == "deepseek":
        return MODEL_PRESETS["deepseek"]
    if family == "glm_flash":
        return MODEL_PRESETS["glm_flash"]
    if family == "mimo":
        return MODEL_PRESETS["mimo"]
    if family == "grok":
        return MODEL_PRESETS["grok"]
    if family == "gpt_oss":
        return MODEL_PRESETS["gpt_oss"]
    if family == "openai":
        return MODEL_PRESETS["openai"]
    if family == "mercury":
        return MODEL_PRESETS["mercury"]
    return MODEL_PRESETS["generic"]


def validate_reasoning_effort(model_path: str, effort: str | None) -> None:
    """Reject GLM efforts that the provider would silently reinterpret as max."""
    if detect_model_family(model_path) == "glm_flash" and effort not in (
        None,
        "low",
        "high",
        "max",
    ):
        raise ValueError("GLM-5.3-Flash reasoning effort must be low, high, or max")


def build_harness_config(
    *,
    model_path: str,
    thinking: bool = False,
    reasoning_task: bool = True,
    reasoning_effort: str | None = None,
    max_tokens: int | None = None,
    default_max_tokens: int = 2048,
    **options,
) -> HarnessConfig:
    """Shared model defaults for production passes and calibration tools.

    GLM always reasons. Give its answer room after that reasoning, while honoring
    an explicit output limit. These are starting budgets, not quality approvals.
    """
    validate_reasoning_effort(model_path, reasoning_effort)
    if detect_model_family(model_path) == "deepseek" and reasoning_effort == "none":
        reasoning_effort = None
    if max_tokens is None:
        max_tokens = default_max_tokens
        if detect_model_family(model_path) == "glm_flash":
            reasoning_budget = 8192 if reasoning_effort in ("high", "max") else 4096
            max_tokens = max(max_tokens, reasoning_budget)
    return HarnessConfig(
        model_path=model_path,
        thinking=thinking,
        reasoning_effort=reasoning_effort,
        max_tokens=max_tokens,
        **get_preset_for_model(model_path, thinking, reasoning_task),
        **options,
    )


def _archive_dir() -> Path:
    env_dir = os.environ.get("COUNTYIQ_ARCHIVE_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.cwd() / "archives"


def llm_archive_strict() -> bool:
    """Return whether transcript archival failures must abort inference."""

    return os.environ.get("COUNTYIQ_ARCHIVE_STRICT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def probe_llm_archive_destination() -> dict[str, str | bool]:
    """Write, fsync, and remove a small archive probe without calling a model."""

    configured = os.environ.get("COUNTYIQ_ARCHIVE_DIR", "").strip()
    if not configured:
        return {
            "ok": False,
            "path": "",
            "reason": "COUNTYIQ_ARCHIVE_DIR is not explicitly configured",
        }

    archive_root = Path(configured).expanduser().resolve()
    probe_path: Path | None = None
    try:
        archive_root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".countyiq-archive-probe-",
            dir=archive_root,
        )
        probe_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as probe:
            probe.write(b"countyiq archive readiness probe\n")
            probe.flush()
            os.fsync(probe.fileno())
        probe_path.unlink()
        return {"ok": True, "path": str(archive_root), "reason": "write probe passed"}
    except Exception as exc:
        if probe_path is not None:
            try:
                probe_path.unlink(missing_ok=True)
            except OSError:
                pass
        return {
            "ok": False,
            "path": str(archive_root),
            "reason": f"{type(exc).__name__}: {exc}",
        }


def llm_archive_retention_days() -> int:
    """Return archive retention in days; zero explicitly disables pruning."""
    return max(
        _int_env(
            "COUNTYIQ_LLM_ARCHIVE_RETENTION_DAYS",
            _DEFAULT_LLM_ARCHIVE_RETENTION_DAYS,
        ),
        0,
    )


def prune_llm_archives(
    archive_root: Path | None = None,
    *,
    retention_days: int | None = None,
    now: datetime | None = None,
) -> int:
    """Delete expired harness JSON files, leaving unrelated files untouched."""
    root = (archive_root or _archive_dir()).resolve()
    days = llm_archive_retention_days() if retention_days is None else retention_days
    if days <= 0 or not root.is_dir():
        return 0

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    cutoff = current - timedelta(days=days)
    removed = 0
    for label_dir in root.iterdir():
        if not label_dir.is_dir() or label_dir.is_symlink():
            continue
        for date_dir in label_dir.iterdir():
            if (
                not date_dir.is_dir()
                or date_dir.is_symlink()
                or not _ARCHIVE_DATE_RE.fullmatch(date_dir.name)
            ):
                continue
            for path in date_dir.iterdir():
                if (
                    not path.is_file()
                    or path.is_symlink()
                    or not _ARCHIVE_FILENAME_RE.fullmatch(path.name)
                ):
                    continue
                modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                if modified < cutoff:
                    path.unlink()
                    removed += 1
            try:
                date_dir.rmdir()
            except OSError:
                pass
        try:
            label_dir.rmdir()
        except OSError:
            pass
    return removed


def _prune_archives_once_per_day(archive_root: Path) -> None:
    global _last_archive_prune_date
    today = datetime.now(timezone.utc).date().isoformat()
    if _last_archive_prune_date == today:
        return
    try:
        removed = prune_llm_archives(archive_root)
        _last_archive_prune_date = today
        if removed:
            _telemetry_log.info("pruned %d expired LLM archive files", removed)
    except Exception as exc:
        _telemetry_log.warning("LLM archive retention prune failed: %s", exc)


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
        _prune_archives_once_per_day(archive_root)
        return str(path)
    except Exception as exc:
        message = f"LLM transcript archive failed for {label}: {exc}"
        if llm_archive_strict():
            raise RuntimeError(message) from exc
        _telemetry_log.warning(message)
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
    family = (
        config.model_family
        if config.model_family != "auto"
        else detect_model_family(config.model_path)
    )
    messages: list[dict] = []
    user_prompt = prompt

    if config.system_prompt:
        messages.append({"role": "system", "content": config.system_prompt})

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


def build_openrouter_payload(
    config: HarnessConfig,
    prompt: str,
    pdf_bytes: bytes | None = None,
) -> dict:
    """Build the OpenRouter request payload for a config.

    Split out from ``_invoke_openrouter`` so the reasoning/thinking wiring
    is unit-testable without a network call — the effort setting silently
    ran at "high" for months because nothing asserted on the payload.
    """
    family = (
        config.model_family
        if config.model_family != "auto"
        else detect_model_family(config.model_path)
    )
    if config.json_schema:
        response_format: dict = {
            "type": "json_schema",
            "json_schema": {
                "name": config.schema_name,
                "strict": True,
                "schema": config.json_schema,
            },
        }
    else:
        response_format = {"type": "json_object"}

    payload = {
        "model": config.model_path,
        "messages": _build_messages(config, prompt, pdf_bytes=pdf_bytes),
        "temperature": config.temperature,
        "top_p": config.top_p,
        "max_tokens": config.max_tokens,
        "response_format": response_format,
    }

    provider_prefs: dict = {}
    # Strict schemas are only honored by providers that support them —
    # route only to those. (docs: structured-outputs + require_parameters)
    if config.require_parameters or config.json_schema:
        provider_prefs["require_parameters"] = True
    if config.max_price_prompt is not None or config.max_price_completion is not None:
        max_price: dict = {}
        if config.max_price_prompt is not None:
            max_price["prompt"] = config.max_price_prompt
        if config.max_price_completion is not None:
            max_price["completion"] = config.max_price_completion
        provider_prefs["max_price"] = max_price
    if config.zdr:
        provider_prefs["zdr"] = True
    if config.provider_quantizations:
        provider_prefs["quantizations"] = list(config.provider_quantizations)
    if config.provider_only:
        provider_prefs["only"] = list(config.provider_only)
    if config.provider_order:
        provider_prefs["order"] = list(config.provider_order)
    if config.provider_allow_fallbacks is not None:
        provider_prefs["allow_fallbacks"] = config.provider_allow_fallbacks
    if provider_prefs:
        payload["provider"] = provider_prefs

    if pdf_bytes and config.pdf_engine:
        payload["plugins"] = [
            {"id": "file-parser", "pdf": {"engine": config.pdf_engine}}
        ]

    if config.top_k > 0:
        payload["top_k"] = config.top_k
    if config.min_p > 0:
        payload["min_p"] = config.min_p
    if config.presence_penalty != 0:
        payload["presence_penalty"] = config.presence_penalty
    if config.repeat_penalty != 1.0:
        payload["frequency_penalty"] = config.repeat_penalty - 1.0

    # OpenAI reasoning endpoints accept no sampling params at all; sending
    # temperature/top_p with require_parameters=true would exclude every
    # provider and 404 each strict-schema call (verified against the
    # OpenRouter listing 2026-08-06).
    if family == "openai":
        payload.pop("temperature", None)
        payload.pop("top_p", None)

    if family == "mimo":
        payload["chat_template_kwargs"] = {"enable_thinking": config.thinking}
    elif family == "glm_flash":
        # This model has mandatory reasoning and defaults to max if omitted.
        # Keep extraction/brief calls bounded even when thinking=False.
        payload["reasoning"] = {"effort": "low"}
    elif family == "deepseek" and "deepseek-v4" in config.model_path.lower():
        # OpenRouter's unified control is translated by the selected provider;
        # a serving-engine chat_template_kwargs flag is not portable.
        payload["reasoning"] = {"enabled": config.thinking}
    elif family == "deepseek" and config.thinking:
        payload["chat_template_kwargs"] = {"thinking_mode": "thinking"}
    elif family == "grok":
        # grok-4.5+ endpoints have MANDATORY reasoning — {"enabled": false}
        # is a hard 400 ("Reasoning is mandatory for this endpoint"). Send
        # the flag only to enable; omit it otherwise and accept the default.
        if config.thinking:
            payload["reasoning"] = {"enabled": True}
    elif family == "gpt_oss":
        payload["reasoning_effort"] = "high"
    elif family == "mercury":
        payload["reasoning"] = {"effort": "high" if config.thinking else "medium"}

    # Explicit per-pass effort beats every family heuristic above.
    validate_reasoning_effort(config.model_path, config.reasoning_effort)
    if config.reasoning_effort:
        payload.pop("reasoning_effort", None)
        payload["reasoning"] = {"effort": config.reasoning_effort}

    if (
        family == "deepseek"
        and "deepseek-v4" in config.model_path.lower()
        and (config.thinking or config.reasoning_effort not in (None, "", "none"))
    ):
        # DeepSeek thinking ignores sampling controls. Omitting them also
        # avoids excluding otherwise compatible strict-schema providers.
        for key in (
            "temperature",
            "top_p",
            "top_k",
            "min_p",
            "presence_penalty",
            "frequency_penalty",
        ):
            payload.pop(key, None)

    return payload


def _invoke_openrouter(
    config: HarnessConfig,
    prompt: str,
    pdf_bytes: bytes | None = None,
) -> tuple[str, str | None, dict]:
    """Invoke OpenRouter and return (raw_output, error, telemetry_meta)."""
    import requests

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return "", "OPENROUTER_API_KEY not set", {}

    payload = build_openrouter_payload(config, prompt, pdf_bytes=pdf_bytes)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://countyiq.local",
        "X-Title": "CountyIQ Intelligence Pipeline",
    }

    resp = None
    request_metadata = {
        "effective_request": {
            key: value for key, value in payload.items() if key != "messages"
        },
        "request_sha256": hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
    }
    meta: dict = dict(request_metadata)
    try:
        resp = _post_with_backoff(OPENROUTER_URL, payload, headers, timeout=180)
        data = resp.json()

        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        meta = {
            **request_metadata,
            "provider": data.get("provider"),
            "served_model": data.get("model"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": details.get("reasoning_tokens"),
            "cached_tokens": (usage.get("prompt_tokens_details") or {}).get(
                "cached_tokens"
            ),
            # OpenRouter reports the actual routed-call charge when usage
            # accounting is available. Persist it instead of estimating from
            # a model price sheet that may not match the selected provider.
            "cost": usage.get("cost"),
            "cost_details": usage.get("cost_details"),
        }

        choice = data["choices"][0]
        message = choice["message"]
        finish = choice.get("finish_reason", "unknown")

        raw_output = message.get("content") or ""
        if not raw_output and "reasoning" in message:
            raw_output = message["reasoning"] or ""
        if not raw_output and "reasoning_content" in message:
            raw_output = message["reasoning_content"] or ""

        if finish == "length":
            return (
                raw_output,
                (
                    f"Response truncated at max_tokens={config.max_tokens} "
                    f"(finish_reason=length)"
                ),
                meta,
            )
        if not raw_output:
            return "", f"Empty response content (finish_reason={finish})", meta
        return raw_output, None, meta
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        # A routing failure must not silently weaken the output contract.
        # Explicit relaxed mode retains the schema in the instructions and
        # records both request identities; provider/price restrictions survive.
        if (
            status == 404
            and config.json_schema is not None
            and config.allow_schema_fallback
        ):
            downgraded = dataclasses.replace(
                config,
                json_schema=None,
                require_parameters=False,
                system_prompt=(config.system_prompt or "")
                + "\nReturn JSON matching this schema:\n"
                + json.dumps(config.json_schema, sort_keys=True),
            )
            raw_output, error, meta = _invoke_openrouter(
                downgraded, prompt, pdf_bytes=pdf_bytes
            )
            meta["schema_fallback"] = True
            meta["strict_request_sha256"] = request_metadata["request_sha256"]
            return raw_output, error, meta
        error_response = exc.response if exc.response is not None else resp
        body = error_response.text[:2000] if error_response is not None else ""
        return "", f"HTTP error: {exc} | body: {body}", meta
    except requests.exceptions.Timeout:
        return "", "Request timeout (180s)", meta
    except (KeyError, IndexError) as exc:
        return "", f"Unexpected response format: {exc}", meta
    except Exception as exc:
        return "", str(exc), meta


def invoke(
    config: HarnessConfig,
    prompt: str,
    archive_key: str | None = None,
    pdf_bytes: bytes | None = None,
) -> HarnessResult:
    """Invoke OpenRouter and return parsed JSON or an error."""
    if config.archive_label and not archive_key and llm_archive_strict():
        raise RuntimeError(
            f"LLM transcript archive key is missing for {config.archive_label}"
        )
    started = time.time()
    raw_output, error, meta = _invoke_openrouter(config, prompt, pdf_bytes=pdf_bytes)
    elapsed_ms = int((time.time() - started) * 1000)
    result_meta = {
        **meta,
        "requested_model": config.model_path,
        "elapsed_ms": elapsed_ms,
    }

    _telemetry_log.info(
        "llm call model=%s provider=%s in=%s out=%s reasoning=%s cached=%s "
        "cost=%s effort=%s strict=%s fallback=%s ms=%d err=%s",
        config.model_path,
        meta.get("provider"),
        meta.get("prompt_tokens"),
        meta.get("completion_tokens"),
        meta.get("reasoning_tokens"),
        meta.get("cached_tokens"),
        meta.get("cost"),
        config.reasoning_effort,
        bool(config.json_schema),
        meta.get("schema_fallback", False),
        elapsed_ms,
        (error or "")[:120] or None,
    )

    if config.archive_label and raw_output:
        if not archive_key:
            message = (
                f"LLM transcript archive key is missing for {config.archive_label}"
            )
            if llm_archive_strict():
                raise RuntimeError(message)
            _telemetry_log.warning(message)
        else:
            archive_raw_output(
                label=config.archive_label,
                key=archive_key,
                prompt=prompt,
                raw_output=raw_output,
                metadata={
                    "model": config.model_path,
                    "temperature": config.temperature,
                    "thinking": config.thinking,
                    "reasoning_effort": config.reasoning_effort,
                    "strict_schema": bool(config.json_schema),
                    "elapsed_ms": elapsed_ms,
                    "error": error,
                    **result_meta,
                },
            )

    if error:
        return HarnessResult(
            raw_output=raw_output,
            parsed=None,
            success=False,
            error=error,
            metadata=result_meta,
        )

    clean_output = strip_thinking(raw_output)
    try:
        return HarnessResult(
            raw_output=raw_output,
            parsed=json.loads(clean_output),
            success=True,
            metadata=result_meta,
        )
    except json.JSONDecodeError:
        pass

    extracted = extract_json_object(clean_output)
    try:
        return HarnessResult(
            raw_output=raw_output,
            parsed=json.loads(extracted),
            success=True,
            metadata=result_meta,
        )
    except json.JSONDecodeError as exc:
        return HarnessResult(
            raw_output=raw_output,
            parsed=None,
            success=False,
            error=f"JSON parse error: {exc}",
            metadata=result_meta,
        )


# Truncation marker emitted by _invoke_openrouter on finish_reason=length.
_TRUNCATION_MARKER = "finish_reason=length"
# Ceiling for adaptive budget doubling. Generous on purpose: for reasoning
# models you pay for generated tokens either way — a tight max_tokens doesn't
# save money, it just decides whether the JSON answer fits AFTER the
# reasoning spend. Cost is controlled by reasoning effort and provider
# max_price, not by starving the completion budget.
_ADAPTIVE_MAX_TOKENS = 16384
_EFFORT_STEP_DOWN = {"high": "medium", "medium": "low", "low": "low"}
_GLM_EFFORT_STEP_DOWN = {"max": "high", "high": "low", "low": "low"}
_USAGE_TOTAL_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "cached_tokens",
    "cost",
    "elapsed_ms",
)


def _is_deterministic_failure(error: str | None) -> bool:
    """Failures that will recur identically — retrying burns money for nothing."""
    return bool(error) and "OPENROUTER_API_KEY not set" in error


def _aggregate_attempt_metadata(attempts: list[dict]) -> dict:
    """Combine retry usage so callers see the full cost, not only the last call."""
    if not attempts:
        return {"attempt_count": 0}

    aggregate = dict(attempts[-1])
    for field in _USAGE_TOTAL_FIELDS:
        values = [m.get(field) for m in attempts]
        numeric = [v for v in values if isinstance(v, (int, float))]
        if numeric:
            aggregate[field] = sum(numeric)
    aggregate["attempt_count"] = len(attempts)
    if len(attempts) > 1:
        aggregate["attempts"] = attempts
    return aggregate


def _with_attempt_metadata(
    result: HarnessResult,
    attempts: list[dict],
) -> HarnessResult:
    return dataclasses.replace(
        result,
        metadata=_aggregate_attempt_metadata(attempts),
    )


def invoke_with_retry(
    config: HarnessConfig,
    prompt: str,
    retries: int = 1,
    archive_key: str | None = None,
    pdf_bytes: bytes | None = None,
) -> HarnessResult:
    """Invoke OpenRouter with a small, failure-aware retry budget.

    Truncation (finish_reason=length) is deterministic for an identical
    config — the answer cannot fit after the reasoning spend — so the retry
    doubles max_tokens and steps reasoning effort down a notch instead of
    repeating the same failure. This is what turned DeepSeek V4 Flash's
    "50% parse failure" in expL2 into a config artifact rather than a
    capability measurement; see docs/decisions.md.
    """
    result = invoke(config, prompt, archive_key=archive_key, pdf_bytes=pdf_bytes)
    attempt_metadata = [result.metadata]
    if result.success:
        return _with_attempt_metadata(result, attempt_metadata)

    attempt_config = config
    for _ in range(retries):
        if _is_deterministic_failure(result.error):
            return _with_attempt_metadata(result, attempt_metadata)
        if result.error and _TRUNCATION_MARKER in result.error:
            effort_steps = (
                _GLM_EFFORT_STEP_DOWN
                if detect_model_family(attempt_config.model_path) == "glm_flash"
                else _EFFORT_STEP_DOWN
            )
            stepped_effort = (
                effort_steps.get(attempt_config.reasoning_effort, "low")
                if attempt_config.reasoning_effort
                else "low"
            )
            attempt_config = dataclasses.replace(
                attempt_config,
                max_tokens=min(attempt_config.max_tokens * 2, _ADAPTIVE_MAX_TOKENS),
                reasoning_effort=stepped_effort,
            )
            _telemetry_log.info(
                "truncation retry model=%s max_tokens->%d effort->%s",
                attempt_config.model_path,
                attempt_config.max_tokens,
                stepped_effort,
            )
        result = invoke(
            attempt_config, prompt, archive_key=archive_key, pdf_bytes=pdf_bytes
        )
        attempt_metadata.append(result.metadata)
        if result.success:
            return _with_attempt_metadata(result, attempt_metadata)
    return _with_attempt_metadata(result, attempt_metadata)
