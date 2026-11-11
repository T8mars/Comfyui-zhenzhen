"""Seedream 5.5 requests and alpha-preserving local artifacts."""

import io
import numpy as np
from PIL import Image
import torch

try:
    from .seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError
    from .image_artifacts import output_target, download_file
    from .preview_muse_flux_low_price_nodes import references
except ImportError:
    from seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError
    from image_artifacts import output_target, download_file
    from preview_muse_flux_low_price_nodes import references

IMAGE_MODELS = ["seedream-v5.5-t2i", "seedream-v5.5-i2i", "dola-seedream-5.5-t2i", "dola-seedream-5.5-i2i"]
LAYER_MODELS = ["seedream-v5.5-layer-decomposition", "dola-seedream-5.5-layer-decomposition"]
RESOLUTIONS = ["1k", "1.5k", "2k", "custom"]
LAYER_RESOLUTIONS = ["auto", "1k", "1.5k", "2k"]
SOURCE_BYTES = 30 * 1024 * 1024


def encode_references(kwargs):
    encoded = []
    for index, tensor in references(kwargs, 10):
        shape = getattr(tensor, "shape", ())
        if len(shape) != 4 or shape[0] != 1 or shape[-1] not in (3, 4) or min(shape[1:3]) < 1:
            raise SeedanceAPIError("Each source input requires one RGB/RGBA IMAGE, not a batch")
        array = tensor.detach().cpu().numpy()[0]
        if not np.isfinite(array).all():
            raise SeedanceAPIError("Source image contains non-finite pixels")
        array = np.clip(array * 255, 0, 255).astype(np.uint8)
        buffer = io.BytesIO()
        Image.fromarray(array).save(buffer, format="PNG")
        data = buffer.getvalue()
        if len(data) > SOURCE_BYTES:
            raise SeedanceAPIError("Each encoded source image must not exceed 30 MiB")
        encoded.append((index, data))
    return encoded


def validate(kwargs, layer=False, strict=False):
    models = LAYER_MODELS if layer else IMAGE_MODELS
    model = kwargs.get("model", models[0])
    if model not in models:
        raise SeedanceAPIError("Unsupported Seedream 5.5 model")
    prompt = kwargs.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        raise SeedanceAPIError("prompt must be text")
    text = (prompt or "").strip()
    if len(text) > (2000 if layer else 5000) or (strict and not layer and len(text) < 5):
        raise SeedanceAPIError("Decomposition prompt must be 0-2000 characters" if layer else "Generation/editing prompt must be 5-5000 characters")
    resolution = kwargs.get("resolution", "auto" if layer else "1k")
    if resolution not in (LAYER_RESOLUTIONS if layer else RESOLUTIONS):
        raise SeedanceAPIError("Unsupported Seedream 5.5 resolution")
    format_ = kwargs.get("output_format", "png")
    if format_ not in ("png", "jpeg"):
        raise SeedanceAPIError("output_format must be png or jpeg")
    if not layer:
        background = kwargs.get("background", "auto")
        if background not in ("auto", "transparent", "opaque"):
            raise SeedanceAPIError("Unsupported background mode")
        if background == "transparent" and format_ != "png":
            raise SeedanceAPIError("Transparent backgrounds require PNG | 透明背景必须选择PNG")
        if resolution == "custom":
            dimensions = [kwargs.get(field, 1024) for field in ("width", "height")]
            for value in dimensions:
                if value is None and not strict:
                    continue
                if isinstance(value, bool) or not isinstance(value, int) or not 240 <= value <= 11520:
                    raise SeedanceAPIError("Custom width/height must be integers from 240 to 11520")
            if None not in dimensions:
                width, height = dimensions
                if not 921600 <= width * height <= 8294400 or not 1/16 <= width / height <= 16:
                    raise SeedanceAPIError("Custom canvas requires 921600-8294400 pixels and an aspect ratio from 1:16 to 16:1")
    else:
        maximum = kwargs.get("max_images", 30)
        if isinstance(maximum, bool) or not isinstance(maximum, int) or not 2 <= maximum <= 100:
            raise SeedanceAPIError("max_images must be an integer from 2 to 100, including the base image")
        if not isinstance(kwargs.get("text_recognition", False), bool):
            raise SeedanceAPIError("text_recognition must be boolean")
    if not isinstance(kwargs.get("watermark", False), bool):
        raise SeedanceAPIError("watermark must be boolean")
    identifier = kwargs.get("safety_identifier", "")
    if identifier is not None or strict:
        if not isinstance(identifier, str) or len(identifier) > 64:
            raise SeedanceAPIError("safety_identifier must be text up to 64 characters")
    if layer:
        if strict and kwargs.get("image") is None:
            raise SeedanceAPIError("Decomposition requires exactly one source image")
        if references(kwargs, 10):
            raise SeedanceAPIError("Use the single image input for decomposition")
    else:
        images = references(kwargs, 10)
        if model.endswith("-t2i") and images:
            raise SeedanceAPIError("T2I does not accept image references; select the matching I2I model")
        if strict and model.endswith("-i2i") and not images:
            raise SeedanceAPIError("I2I requires 1-10 reference images")
    return True


def payload(kwargs, urls, layer=False):
    validate(kwargs, layer=layer, strict=True)
    models = LAYER_MODELS if layer else IMAGE_MODELS
    model = kwargs.get("model", models[0])
    if (layer and len(urls) != 1) or (not layer and model.endswith("-i2i") and not 1 <= len(urls) <= 10):
        raise SeedanceAPIError("Invalid Seedream 5.5 source count")
    if not layer and model.endswith("-t2i") and urls:
        raise SeedanceAPIError("T2I cannot submit images")
    metadata = {"output_format": kwargs.get("output_format", "png"), "watermark": kwargs.get("watermark", False)}
    resolution = kwargs.get("resolution", "auto" if layer else "1k")
    if resolution == "custom":
        metadata.update(width=kwargs.get("width", 1024), height=kwargs.get("height", 1024))
    else:
        metadata["resolution"] = resolution
    if layer:
        metadata.update(max_images=kwargs.get("max_images", 30), text_recognition=kwargs.get("text_recognition", False))
    else:
        metadata["background"] = kwargs.get("background", "auto")
    identifier = kwargs.get("safety_identifier", "")
    if identifier:
        metadata["safety_identifier"] = identifier
    result = {"model": model, "metadata": metadata}
    prompt = (kwargs.get("prompt") or "").strip()
    if prompt:
        result["prompt"] = prompt
    if urls:
        result["images"] = list(urls)
    return result


def layer_metadata(final, urls):
    data = final.get("data") if isinstance(final, dict) else None
    upstream = data.get("data") if isinstance(data, dict) else None
    content = upstream.get("content") if isinstance(upstream, dict) else None
    layers = content.get("layers") if isinstance(content, dict) else None
    if layers is None:
        return []
    if not isinstance(layers, list) or len(layers) != len(urls) or any(
            not isinstance(layer, dict) or layer.get("url") != url for layer, url in zip(layers, urls)):
        raise SeedanceAPIError("Layer metadata must align with the returned image URL order")
    return layers


def download_original(url, prefix="zhenzhen/seedream55"):
    def inspect(path):
        with Image.open(path) as source:
            extension = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}.get(source.format)
            if extension is None or getattr(source, "n_frames", 1) != 1:
                raise SeedanceAPIError("Seedream 5.5 returned an unsupported static image format")
            if source.width * source.height > 64 * 1024 * 1024:
                raise SeedanceAPIError("Image exceeds the local decoded-pixel safety limit")
            has_alpha = "A" in source.getbands() or "transparency" in source.info
            array = np.array(source.convert("RGBA" if has_alpha else "RGB"), dtype=np.float32) / 255.0
        image = torch.from_numpy(array).unsqueeze(0)
        mask = 1 - image[..., 3] if has_alpha else image.new_zeros(image.shape[:3])
        return image, extension, mask

    path, entry, decoded = download_file(url, prefix, inspect=inspect)
    return decoded[0], decoded[2], path, entry
