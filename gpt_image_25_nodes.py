"""GPT Image 2.5 nodes for the Zhenzhen AI Workshop channel."""

from __future__ import annotations

import base64
import copy
import io
import json
from typing import Any, Iterable

import numpy as np
import torch
from PIL import Image

try:
    from . import zhenzhen_http as requests
    from .media_download import download_image_with_retry
    from .utils import pil2tensor
    from .zhenzhen_http import PRIMARY_BASE_URL
except ImportError:  # Support direct imports in the unit tests.
    import zhenzhen_http as requests
    from media_download import download_image_with_retry
    from utils import pil2tensor
    from zhenzhen_http import PRIMARY_BASE_URL

try:
    import comfy.utils

    COMFYUI_AVAILABLE = True
except ImportError:
    COMFYUI_AVAILABLE = False


GPT_IMAGE_25_MODELS = (
    "gpt-image-2.5-flare",
    "gpt-image-2.5-flare-2k",
    "gpt-image-2.5-flare-4k",
    "gpt-image-2.5-sunburst",
    "gpt-image-2.5-sunburst-2k",
    "gpt-image-2.5-sunburst-4k",
)
GPT_IMAGE_25_QUALITY = ("auto", "low", "medium", "high", "xhigh", "max")
GPT_IMAGE_25_SIZES = (
    "1024x1024",
    "1536x1024",
    "1024x1536",
    "2048x2048",
    "2048x1152",
    "1152x2048",
    "3840x2160",
    "2160x3840",
    "custom",
)
GPT_IMAGE_25_BACKGROUNDS = ("auto", "opaque")
GPT_IMAGE_25_MODERATION = ("auto", "low")
GPT_IMAGE_25_MAX_IMAGES = 14
GPT_IMAGE_25_PROMPT_MAX_LENGTH = 32_000
GPT_IMAGE_25_ENDPOINT_TIMEOUT = (30, 900)


class GPTImage25Error(RuntimeError):
    """Input, transport, or response error from the GPT Image 2.5 node."""


def _parse_size(size: str) -> tuple[int, int]:
    parts = str(size or "").lower().split("x")
    if len(parts) != 2:
        raise GPTImage25Error("size must use WIDTHxHEIGHT, for example 1024x1024")
    try:
        width, height = (int(value) for value in parts)
    except ValueError as exc:
        raise GPTImage25Error(
            "size must use WIDTHxHEIGHT, for example 1024x1024"
        ) from exc
    return width, height


def validate_gpt_image_25_size(size: str) -> tuple[int, int]:
    width, height = _parse_size(size)
    if width % 16 or height % 16:
        raise GPTImage25Error("image width and height must both be multiples of 16")
    if width > 3840 or height > 3840:
        raise GPTImage25Error("image width and height must not exceed 3840")
    short_edge, long_edge = sorted((width, height))
    if short_edge <= 0 or long_edge / short_edge > 3:
        raise GPTImage25Error("image aspect ratio must be between 1:3 and 3:1")
    pixels = width * height
    if not 655_360 <= pixels <= 8_294_400:
        raise GPTImage25Error(
            "image size must contain between 655,360 and 8,294,400 pixels"
        )
    return width, height


def resolve_gpt_image_25_size(
    size: str,
    custom_width: int = 1024,
    custom_height: int = 1024,
) -> str:
    resolved = (
        f"{int(custom_width)}x{int(custom_height)}"
        if size == "custom"
        else str(size)
    )
    validate_gpt_image_25_size(resolved)
    return resolved


def validate_gpt_image_25_request(
    model: str,
    prompt: str,
    quality: str,
    size: str,
    custom_width: int,
    custom_height: int,
    n: int,
    background: str,
    moderation: str,
) -> str:
    if model not in GPT_IMAGE_25_MODELS:
        raise GPTImage25Error(f"unsupported GPT Image 2.5 model: {model}")
    normalized_prompt = str(prompt or "").strip()
    if not normalized_prompt:
        raise GPTImage25Error("prompt is required")
    if len(normalized_prompt) > GPT_IMAGE_25_PROMPT_MAX_LENGTH:
        raise GPTImage25Error("prompt must not exceed 32,000 characters")
    if quality not in GPT_IMAGE_25_QUALITY:
        raise GPTImage25Error(f"unsupported quality: {quality}")
    if background not in GPT_IMAGE_25_BACKGROUNDS:
        raise GPTImage25Error(f"unsupported background: {background}")
    if moderation not in GPT_IMAGE_25_MODERATION:
        raise GPTImage25Error(f"unsupported moderation: {moderation}")
    if not 1 <= int(n) <= 10:
        raise GPTImage25Error("n must be between 1 and 10")
    return resolve_gpt_image_25_size(size, custom_width, custom_height)


def build_gpt_image_25_generation_payload(
    *,
    model: str,
    prompt: str,
    quality: str,
    size: str,
    n: int,
    background: str,
    moderation: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": str(prompt).strip(),
        "quality": quality,
        "size": size,
        "n": int(n),
        "moderation": moderation,
    }
    if background != "auto":
        payload["background"] = background
    return payload


def build_gpt_image_25_edit_fields(
    *,
    model: str,
    prompt: str,
    quality: str,
    size: str,
    n: int,
    background: str,
    moderation: str,
) -> dict[str, str]:
    return {
        key: str(value)
        for key, value in build_gpt_image_25_generation_payload(
            model=model,
            prompt=prompt,
            quality=quality,
            size=size,
            n=n,
            background=background,
            moderation=moderation,
        ).items()
    }


def _iter_image_frames(value: Any) -> Iterable[torch.Tensor]:
    if value is None:
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_image_frames(item)
        return
    if not torch.is_tensor(value):
        raise GPTImage25Error(
            f"image inputs must be IMAGE tensors, got {type(value).__name__}"
        )
    if value.ndim == 3:
        yield value.unsqueeze(0)
        return
    if value.ndim != 4:
        raise GPTImage25Error("image tensors must have shape [B,H,W,C]")
    for index in range(int(value.shape[0])):
        yield value[index : index + 1]


def collect_gpt_image_25_frames(*images: Any) -> list[torch.Tensor]:
    frames: list[torch.Tensor] = []
    for image in images:
        frames.extend(_iter_image_frames(image))
        if len(frames) > GPT_IMAGE_25_MAX_IMAGES:
            raise GPTImage25Error(
                "Zhenzhen AI Workshop currently accepts at most 14 reference images"
            )
    return frames


def _frame_to_png(frame: torch.Tensor) -> tuple[bytes, tuple[int, int]]:
    tensor = frame.detach().cpu().float()
    if tensor.ndim == 4:
        if int(tensor.shape[0]) != 1:
            raise GPTImage25Error("each uploaded image must contain exactly one frame")
        tensor = tensor[0]
    if tensor.ndim != 3 or int(tensor.shape[-1]) not in (1, 3, 4):
        raise GPTImage25Error("IMAGE tensors must use one, three, or four channels")
    array = np.clip(tensor.numpy() * 255.0, 0, 255).astype(np.uint8)
    if array.shape[-1] == 1:
        array = np.repeat(array, 3, axis=-1)
    image = Image.fromarray(array)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), image.size


def _mask_to_png(mask: Any, expected_size: tuple[int, int]) -> bytes:
    if not torch.is_tensor(mask):
        raise GPTImage25Error("mask must be a MASK tensor")
    tensor = mask.detach().cpu().float()
    if tensor.ndim == 3:
        if int(tensor.shape[0]) != 1:
            raise GPTImage25Error("mask must contain exactly one frame")
        tensor = tensor[0]
    if tensor.ndim != 2:
        raise GPTImage25Error("mask must have shape [1,H,W] or [H,W]")
    height, width = (int(value) for value in tensor.shape)
    if (width, height) != expected_size:
        raise GPTImage25Error("mask and its input image must have the same dimensions")
    alpha = np.clip((1.0 - tensor.numpy()) * 255.0, 0, 255).astype(np.uint8)
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, 3] = alpha
    image = Image.fromarray(rgba, mode="RGBA")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def build_gpt_image_25_files(
    frames: list[torch.Tensor],
    mask: Any = None,
) -> list[tuple[str, tuple[str, bytes, str]]]:
    if mask is not None and len(frames) != 1:
        raise GPTImage25Error("mask requires exactly one reference image")
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    first_size: tuple[int, int] | None = None
    for index, frame in enumerate(frames, start=1):
        raw, image_size = _frame_to_png(frame)
        if first_size is None:
            first_size = image_size
        files.append(("image", (f"reference_{index}.png", raw, "image/png")))
    if mask is not None:
        files.append(
            (
                "mask",
                ("mask.png", _mask_to_png(mask, first_size), "image/png"),
            )
        )
    return files


def _response_error(response: Any) -> GPTImage25Error:
    message = "request rejected"
    try:
        body = response.json()
        error = body.get("error", {}) if isinstance(body, dict) else {}
        message = str(error.get("message") or body.get("message") or message)
    except Exception:
        text = str(getattr(response, "text", "") or "").strip()
        if text:
            message = text[:1000]
    return GPTImage25Error(
        f"GPT Image 2.5 request failed (HTTP {response.status_code}): {message}"
    )


def _post_gpt_image_25(
    *,
    api_key: str,
    payload: dict[str, Any],
    files: list[tuple[str, tuple[str, bytes, str]]],
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    if files:
        response = requests.post(
            f"{PRIMARY_BASE_URL}/v1/images/edits",
            headers=headers,
            data={key: str(value) for key, value in payload.items()},
            files=files,
            timeout=GPT_IMAGE_25_ENDPOINT_TIMEOUT,
        )
    else:
        response = requests.post(
            f"{PRIMARY_BASE_URL}/v1/images/generations",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
            timeout=GPT_IMAGE_25_ENDPOINT_TIMEOUT,
        )
    if int(response.status_code) >= 400:
        raise _response_error(response)
    try:
        result = response.json()
    except Exception as exc:
        raise GPTImage25Error("GPT Image 2.5 returned a non-JSON response") from exc
    if not isinstance(result, dict):
        raise GPTImage25Error("GPT Image 2.5 returned an invalid response object")
    return result


def _decode_result_item(item: Any) -> tuple[torch.Tensor, str]:
    if not isinstance(item, dict):
        raise GPTImage25Error("GPT Image 2.5 returned an invalid image item")
    encoded = str(item.get("b64_json") or "").strip()
    if encoded:
        if encoded.startswith("data:image"):
            encoded = encoded.split(",", 1)[-1]
        try:
            raw = base64.b64decode(encoded)
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                return pil2tensor(image.convert("RGB")), ""
        except Exception as exc:
            raise GPTImage25Error("could not decode the returned base64 image") from exc
    image_url = str(item.get("url") or "").strip()
    if image_url:
        image = download_image_with_retry(
            image_url,
            timeout=300,
            max_attempts=5,
        )
        return pil2tensor(image), image_url
    raise GPTImage25Error("GPT Image 2.5 result contains neither url nor b64_json")


def decode_gpt_image_25_result(
    result: dict[str, Any],
) -> tuple[torch.Tensor, list[str]]:
    items = result.get("data")
    if not isinstance(items, list) or not items:
        raise GPTImage25Error("GPT Image 2.5 response contains no image data")
    tensors: list[torch.Tensor] = []
    urls: list[str] = []
    for item in items:
        tensor, image_url = _decode_result_item(item)
        tensors.append(tensor)
        if image_url:
            urls.append(image_url)
    shapes = {tuple(tensor.shape[1:]) for tensor in tensors}
    if len(shapes) != 1:
        raise GPTImage25Error("returned images have different dimensions and cannot form a batch")
    return torch.cat(tensors, dim=0), urls


def _safe_response_json(result: dict[str, Any], mode: str) -> str:
    safe = copy.deepcopy(result)
    for item in safe.get("data", []) if isinstance(safe.get("data"), list) else []:
        if isinstance(item, dict) and item.get("b64_json"):
            item["b64_json"] = "[base64 image omitted]"
    safe["request_mode"] = mode
    return json.dumps(safe, ensure_ascii=False, indent=2)


class T8ZhenzhenGPTImage25Workshop:
    """Generate or edit images with six GPT Image 2.5 Workshop models."""

    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True

    @classmethod
    def INPUT_TYPES(cls):
        optional: dict[str, Any] = {
            f"image{index}": ("IMAGE",)
            for index in range(1, GPT_IMAGE_25_MAX_IMAGES + 1)
        }
        optional.update(
            {
                "mask": ("MASK",),
                "api_key": ("STRING", {"default": ""}),
                "model": (list(GPT_IMAGE_25_MODELS), {"default": GPT_IMAGE_25_MODELS[0]}),
                "quality": (list(GPT_IMAGE_25_QUALITY), {"default": "auto"}),
                "size": (list(GPT_IMAGE_25_SIZES), {"default": "1024x1024"}),
                "custom_width": (
                    "INT",
                    {"default": 1024, "min": 16, "max": 3840, "step": 16},
                ),
                "custom_height": (
                    "INT",
                    {"default": 1024, "min": 16, "max": 3840, "step": 16},
                ),
                "n": ("INT", {"default": 1, "min": 1, "max": 10}),
                "background": (
                    list(GPT_IMAGE_25_BACKGROUNDS),
                    {"default": "auto"},
                ),
                "moderation": (
                    list(GPT_IMAGE_25_MODERATION),
                    {"default": "auto"},
                ),
                "skip_error": ("BOOLEAN", {"default": False}),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "step": 1,
                        "control_after_generate": True,
                        "tooltip": (
                            "ComfyUI cache seed only; it is not sent to GPT Image 2.5. "
                            "Fixed reuses the cached result."
                        ),
                    },
                ),
            }
        )
        return {
            "required": {
                "prompt": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "dynamicPrompts": True,
                    },
                ),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_urls", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/OpenAI"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        prompt="",
        model=GPT_IMAGE_25_MODELS[0],
        quality="auto",
        size="1024x1024",
        custom_width=1024,
        custom_height=1024,
        n=1,
        background="auto",
        moderation="auto",
        **kwargs,
    ):
        try:
            validate_gpt_image_25_request(
                model,
                prompt,
                quality,
                size,
                custom_width,
                custom_height,
                n,
                background,
                moderation,
            )
            images = [kwargs.get(f"image{index}") for index in range(1, 15)]
            frames = collect_gpt_image_25_frames(*images)
            if kwargs.get("mask") is not None and len(frames) != 1:
                raise GPTImage25Error("mask requires exactly one reference image")
        except Exception as exc:
            return str(exc)
        return True

    def generate(
        self,
        prompt: str,
        image1=None,
        image2=None,
        image3=None,
        image4=None,
        image5=None,
        image6=None,
        image7=None,
        image8=None,
        image9=None,
        image10=None,
        image11=None,
        image12=None,
        image13=None,
        image14=None,
        mask=None,
        api_key: str = "",
        model: str = GPT_IMAGE_25_MODELS[0],
        quality: str = "auto",
        size: str = "1024x1024",
        custom_width: int = 1024,
        custom_height: int = 1024,
        n: int = 1,
        background: str = "auto",
        moderation: str = "auto",
        skip_error: bool = False,
        seed: int = 0,
    ):
        del seed
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            key = str(api_key or "").strip()
            if not key:
                raise GPTImage25Error(
                    "API key is empty. Enter it in the current workflow or connect "
                    "T8Zhenzhen API Settings with the zhenzhen channel selected."
                )
            resolved_size = validate_gpt_image_25_request(
                model,
                prompt,
                quality,
                size,
                custom_width,
                custom_height,
                n,
                background,
                moderation,
            )
            frames = collect_gpt_image_25_frames(
                image1,
                image2,
                image3,
                image4,
                image5,
                image6,
                image7,
                image8,
                image9,
                image10,
                image11,
                image12,
                image13,
                image14,
            )
            files = build_gpt_image_25_files(frames, mask)
            payload = build_gpt_image_25_generation_payload(
                model=model,
                prompt=prompt,
                quality=quality,
                size=resolved_size,
                n=n,
                background=background,
                moderation=moderation,
            )
            mode = "image_edit" if files else "text_to_image"
            update_progress(10)
            result = _post_gpt_image_25(
                api_key=key,
                payload=payload,
                files=files,
            )
            update_progress(60)
            images, urls = decode_gpt_image_25_result(result)
            update_progress(100)
            return (
                images,
                "\n".join(urls),
                _safe_response_json(result, mode),
            )
        except Exception as exc:
            if not skip_error:
                raise
            response = {
                "status": "error",
                "model": model,
                "message": f"{type(exc).__name__}: {exc}",
            }
            return (
                torch.ones((1, 512, 512, 3), dtype=torch.float32),
                "",
                json.dumps(response, ensure_ascii=False, indent=2),
            )


__all__ = [
    "GPTImage25Error",
    "GPT_IMAGE_25_MAX_IMAGES",
    "GPT_IMAGE_25_MODELS",
    "GPT_IMAGE_25_SIZES",
    "T8ZhenzhenGPTImage25Workshop",
    "build_gpt_image_25_edit_fields",
    "build_gpt_image_25_files",
    "build_gpt_image_25_generation_payload",
    "collect_gpt_image_25_frames",
    "decode_gpt_image_25_result",
    "resolve_gpt_image_25_size",
    "validate_gpt_image_25_request",
    "validate_gpt_image_25_size",
]
