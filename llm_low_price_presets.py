"""Opt-in Low Price presets for the existing LLM node."""

import base64

from . import seedance_low_price_nodes as api
from .h3_turbo_low_price_nodes import get_config

MODELS = [
    "zhenzhen/g6.2-astra", "zhenzhen/g6.2-sol",
    "zhenzhen/gm-4-hydrogen", "zhenzhen/gm-4-carbon", "zhenzhen/gm-4-neon", "zhenzhen/hy-4-flash",
]
PRESETS = ["custom", *MODELS]
API_MODEL_IDS = {"zhenzhen/hy-4-flash": "tencent/hy4-flash"}


def call_g62(model, prompt, role, api_key="", api_config=None, image=None, video=None,
             stream=False, max_tokens=512):
    if model not in MODELS:
        raise api.SeedanceLowPriceError("Unsupported Low Price model preset")
    if not isinstance(prompt, str) or not prompt.strip() or not isinstance(role, str):
        raise api.SeedanceLowPriceError("A non-empty text prompt and text role are required")
    if video is not None:
        raise api.SeedanceLowPriceError("Low Price LLM presets on this node accept text and one image, not VIDEO")
    if type(stream) is not bool or type(max_tokens) is not int or not 1 <= max_tokens <= 32768:
        raise api.SeedanceLowPriceError("Invalid streaming option or max_tokens (1-32768)")
    if api_config is not None:
        config = get_config(api_config)
        if config["base_url"] != api.DEFAULT_BASE_URL:
            raise api.SeedanceLowPriceError("This preset requires the Low Price API Settings channel")
        key = config["api_key"]
    else:
        key = str(api_key or "").strip()
        if not key:
            raise api.SeedanceLowPriceError("Enter this workflow's Low Price API key or connect Low Price API Settings")
    content = prompt
    if image is not None:
        if not isinstance(image, api.torch.Tensor) or image.ndim != 4 or image.shape[0] != 1 or image.shape[-1] not in (3, 4) or not api.torch.isfinite(image).all():
            raise api.SeedanceLowPriceError("This node requires one finite RGB/RGBA reference image")
        encoded = base64.b64encode(api.image_to_png_bytes(image)).decode("ascii")
        content = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}}]
    messages = [{"role": "user", "content": content}]
    if role.strip():
        messages.insert(0, {"role": "system", "content": role})
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=api.DEFAULT_BASE_URL + "/v1", timeout=180.0, max_retries=0)
    result = None
    try:
        result = client.chat.completions.create(model=API_MODEL_IDS.get(model, model), messages=messages, stream=stream, max_tokens=max_tokens)
        if stream:
            text = "".join(choice.delta.content or "" for chunk in result for choice in chunk.choices)
        else:
            text = result.choices[0].message.content or ""
        if not isinstance(text, str) or not text.strip():
            raise api.SeedanceLowPriceError("The model returned no final text; reasoning alone is not a result")
        return text
    except Exception as error:
        raise api.SeedanceLowPriceError(str(error).replace(key, "[REDACTED]")[:1000]) from None
    finally:
        if stream and result is not None:
            result.close()
        client.close()
