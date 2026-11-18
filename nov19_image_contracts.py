"""Request contracts for Kling 4 Image and MAI Image 2.7."""

import re

import torch

from .seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError, image_to_png_bytes
from .preview_muse_flux_low_price_nodes import references


KLING_MODEL = "kling-v4-image"
KLING_SIZES = ["auto", "16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9"]
MAI_MODELS = ["mai-image-2-7", "mai-image-2-7-flash"]
MAI_SIZES = ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9", "4:1", "1:4",
             "custom_ratio", "custom_pixels"]
MAI_MAX_PIXELS = 4194304


def _prompt(value, kind, strict):
    if value is None and not strict:
        return ""
    if not isinstance(value, str):
        raise SeedanceAPIError("prompt must be text")
    value = value.strip()
    if strict and not value:
        raise SeedanceAPIError("A non-empty prompt is required")
    if kind == "kling":
        extended = sum(not char.isascii() for char in value)
        if (len(value) - extended) * 21000 + extended * 50000 > 50000 * 21000:
            raise SeedanceAPIError("Kling prompt exceeds its mixed-language length limit")
    elif len(value) > 20000:
        raise SeedanceAPIError("MAI prompt must contain at most 20000 characters")
    return value


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise SeedanceAPIError(f"{name} must be an integer between {low} and {high}")
    return value


def _resolution(value, choices):
    if not isinstance(value, str) or value.lower() not in choices:
        raise SeedanceAPIError("Unsupported image resolution")
    return value.lower()


def _mai_size(kwargs):
    size = kwargs.get("size", "1:1")
    if size == "custom_pixels":
        limit = MAI_MAX_PIXELS // 768
        w = _integer(kwargs.get("width", 1536), "width", 768, limit)
        h = _integer(kwargs.get("height", 1024), "height", 768, limit)
        if w * h > MAI_MAX_PIXELS:
            raise SeedanceAPIError("MAI width times height must not exceed 4194304 pixels")
        return {"width": w // 32 * 32, "height": h // 32 * 32}
    ratio = kwargs.get("custom_ratio", "16:9") if size == "custom_ratio" else size
    if not isinstance(ratio, str) or not re.fullmatch(r"[0-9]{1,9}:[0-9]{1,9}", ratio.strip()):
        raise SeedanceAPIError("MAI size requires a positive integer width:height ratio")
    w, h = map(int, ratio.split(":"))
    if min(w, h) < 1 or max(w, h) > min(w, h) * 4:
        raise SeedanceAPIError("MAI aspect ratio must be between 1:4 and 4:1")
    return {"size": f"{w}:{h}", "resolution": _resolution(kwargs.get("resolution", "1k"), ("1k", "2k"))}


def payload(kind, kwargs, images=(), strict=True):
    kling = kind == "kling"
    local_refs = references(kwargs, 10 if kling else 5)
    if len(images) > (10 if kling else 5):
        raise SeedanceAPIError("Too many reference images")
    body = {"prompt": _prompt(kwargs.get("prompt"), kind, strict)}
    nsfw = kwargs.get("nsfw_check", False)
    if type(nsfw) is not bool:
        raise SeedanceAPIError("nsfw_check must be a boolean")
    body["nsfw_check"] = nsfw
    if kling:
        size = kwargs.get("size", "auto")
        if size not in KLING_SIZES:
            raise SeedanceAPIError("Unsupported Kling image aspect ratio")
        mode = kwargs.get("sequential_image_generation", "disabled")
        if mode not in ("disabled", "auto"):
            raise SeedanceAPIError("Unsupported Kling image generation mode")
        body.update(model=KLING_MODEL, size=size,
                    resolution=_resolution(kwargs.get("resolution", "2k"), ("2k", "4k")),
                    sequential_image_generation=mode)
        if mode == "auto":
            body["sequential_image_generation_options"] = {
                "max_images": _integer(kwargs.get("max_images", 2), "max_images", 2, 4)
            }
        else:
            body["n"] = _integer(kwargs.get("n", 1), "n", 1, 9)
        if strict:
            for index in re.findall(r"@Image([0-9]{1,9})(?![0-9])", body["prompt"], re.IGNORECASE):
                if not 1 <= int(index) <= max(len(images), len(local_refs)):
                    raise SeedanceAPIError(f"@Image{index} does not have a matching reference")
    else:
        model = kwargs.get("model", MAI_MODELS[0])
        if model not in MAI_MODELS:
            raise SeedanceAPIError("Unsupported MAI 2.7 model")
        background = kwargs.get("background", "auto")
        if background not in ("auto", "opaque"):
            raise SeedanceAPIError("MAI background must be auto or opaque")
        body.update(model=model, n=1, background=background)
        if strict and not (images or local_refs):
            body.update(_mai_size(kwargs))
    if images:
        body["images"] = list(images)
    return body


def encode_references(kind, kwargs):
    kling = kind == "kling"
    encoded = []
    for index, image in references(kwargs, 10 if kling else 5):
        if (not isinstance(image, torch.Tensor) or image.ndim != 4 or image.shape[0] != 1
                or image.shape[-1] not in (3, 4) or min(image.shape[1:3]) < 1
                or not torch.isfinite(image).all()):
            raise SeedanceAPIError("Each reference requires one finite RGB/RGBA IMAGE")
        height, width = image.shape[1:3]
        if kling and (min(width, height) < 300 or 2 * max(width, height) > 5 * min(width, height)):
            raise SeedanceAPIError("Kling reference sides must be at least 300 px, with ratio 2:5 to 5:2")
        data = image_to_png_bytes(image)
        if kling and len(data) > 30_000_000:
            raise SeedanceAPIError("Kling reference PNG exceeds 30 MB")
        encoded.append((index, data))
    return encoded
