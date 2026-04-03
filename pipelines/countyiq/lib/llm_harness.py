"""LLM harness for CountyIQ intelligence pipeline."""
import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class HarnessConfig:
    model_path: str
    n_ctx: int = 4096
    n_gpu_layers: int = -1  # -1 = all layers on GPU, 0 = CPU only
    temperature: float = 0.1
    max_tokens: int = 2048


class HarnessResult:
    def __init__(self, raw_output: str, parsed: dict | None, success: bool, error: str | None = None):
        self.raw_output = raw_output
        self.parsed = parsed
        self.success = success
        self.error = error


# Model cache - reuse loaded models across calls within a session
_model_cache: dict[str, object] = {}


def get_model(config: HarnessConfig):
    """Get or create a cached Llama model instance."""
    if config.model_path not in _model_cache:
        from llama_cpp import Llama  # lazy import — only needed at runtime
        _model_cache[config.model_path] = Llama(
            model_path=config.model_path,
            n_ctx=config.n_ctx,
            n_gpu_layers=config.n_gpu_layers,
            verbose=False,
        )
    return _model_cache[config.model_path]


def invoke(config: HarnessConfig, prompt: str, image_path: str | None = None) -> HarnessResult:
    """Invoke the LLM with a prompt and optional image."""
    model = get_model(config)

    messages = []
    if image_path:
        import base64  # lazy import
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        messages.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                {"type": "text", "text": prompt},
            ],
        })
    else:
        messages.append({"role": "user", "content": prompt})

    try:
        response = model.create_chat_completion(
            messages=messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            response_format={"type": "json_object"},
        )
        raw_output = response["choices"][0]["message"]["content"]
        parsed = json.loads(raw_output)
        return HarnessResult(raw_output=raw_output, parsed=parsed, success=True)
    except json.JSONDecodeError as e:
        return HarnessResult(raw_output=raw_output, parsed=None, success=False, error=f"JSON parse error: {e}")
    except Exception as e:
        return HarnessResult(raw_output="", parsed=None, success=False, error=str(e))


def invoke_with_retry(config: HarnessConfig, prompt: str, image_path: str | None = None, retries: int = 1) -> HarnessResult:
    """Invoke with retry on failure."""
    result = invoke(config, prompt, image_path)
    if result.success:
        return result
    for _ in range(retries):
        result = invoke(config, prompt, image_path)
        if result.success:
            return result
    return result
