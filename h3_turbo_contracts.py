"""MiniMax H3 ComfyUI/Image and Qwen 2.1 Turbo request contracts."""

import io

import numpy as np
from PIL import Image
import torch

try:
    from .seedance_low_price_nodes import SeedanceLowPriceError as Error, audio_to_wav_bytes
    from .preview_muse_flux_low_price_nodes import references
except ImportError:
    from seedance_low_price_nodes import SeedanceLowPriceError as Error, audio_to_wav_bytes
    from preview_muse_flux_low_price_nodes import references


RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"]
PROFILES = {
    "video": {"model": "minimax-h3-comfyui-max", "images": 9,
              "resolutions": ["480p", "608p", "768p", "896p", "1088p", "1280p", "1440p"],
              "default": "480p", "ratios": ["16:9", "9:16"]},
    "minimax_image": {"model": "minimax-h3-image", "images": 16,
                      "resolutions": ["1k", "2k", "4k"], "default": "2k", "ratios": RATIOS + ["1:3", "3:1"]},
    "qwen": {"model": "qwen-image-2.1-turbo", "images": 4,
             "resolutions": ["1k", "2k", "720p"], "default": "1k", "ratios": RATIOS},
}
MIB = 1024 * 1024


def validate(kind, values, strict=False):
    spec = PROFILES[kind]
    prompt = values.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        raise Error("prompt must be text")
    if strict and not (prompt or "").strip():
        raise Error("A non-empty prompt is required")
    if kind == "qwen" and isinstance(prompt, str) and len(prompt.encode("utf-8")) > 8192:
        raise Error("Qwen Turbo prompt must not exceed 8192 UTF-8 bytes")
    images = references(values, spec["images"])
    for name, allowed, default in (("resolution", spec["resolutions"], spec["default"]),
                                    ("ratio", spec["ratios"], spec["ratios"][0])):
        value = values.get(name, default)
        if (value is not None or strict) and value not in allowed:
            raise Error("Unsupported " + name)
    if kind == "qwen" and strict and values.get("resolution") == "720p" and not images:
        raise Error("720p requires a reference image")
    for name, value in values.items():
        if name.startswith("audio") and name[5:].isdigit() and value is not None:
            if kind != "video" or not 1 <= int(name[5:]) <= 3:
                raise Error("Only the video model accepts up to three audio references")
    if kind == "video":
        seconds = values.get("seconds", "5")
        if (seconds is not None or strict) and seconds not in [str(i) for i in range(3, 16)]:
            raise Error("seconds must be an integer string from 3 to 15")
    else:
        seed = values.get("seed", -1)
        if (seed is not None or strict) and (type(seed) is not int or not -1 <= seed <= 2147483647):
            raise Error("seed must be -1 (omit) or 0..2147483647")
        format_ = values.get("output_format", "jpeg")
        if kind == "minimax_image" and (format_ is not None or strict) and format_ not in ("jpeg", "png", "webp"):
            raise Error("output_format must be jpeg, png or webp")
    return True


def encode_media(kind, values):
    validate(kind, values, strict=True)
    encoded = []
    for index, image in references(values, PROFILES[kind]["images"]):
        shape = getattr(image, "shape", ())
        if len(shape) != 4 or shape[0] != 1 or shape[-1] not in (3, 4) or min(shape[1:3]) < 1:
            raise Error("Each image reference requires one RGB/RGBA IMAGE, not a batch")
        pixels = image.detach().cpu().numpy()[0]
        if not np.isfinite(pixels).all():
            raise Error("Image contains non-finite pixels")
        buffer = io.BytesIO()
        Image.fromarray(np.clip(pixels * 255, 0, 255).astype(np.uint8)).save(buffer, format="PNG")
        data = buffer.getvalue()
        if kind == "video" and len(data) > 10 * MIB:
            raise Error("Each video reference image must not exceed 10 MiB")
        encoded.append((f"image{index}", data, "image/png"))
    if kind == "video":
        if sum(len(data) for _, data, _ in encoded) > 50 * MIB:
            raise Error("Video reference images must total at most 50 MiB")
        audio_bytes = 0
        for index in range(1, 4):
            audio = values.get(f"audio{index}")
            if audio is None:
                continue
            waveform = audio.get("waveform") if isinstance(audio, dict) else None
            rate = audio.get("sample_rate") if isinstance(audio, dict) else None
            if not isinstance(waveform, torch.Tensor) or waveform.ndim != 3 or waveform.shape[0] != 1 or not 1 <= waveform.shape[1] <= 2 or waveform.shape[2] < 1:
                raise Error("Each audio reference requires one mono/stereo AUDIO")
            if type(rate) is not int or rate < 1 or not torch.isfinite(waveform).all():
                raise Error("Invalid audio sample rate or waveform")
            data = audio_to_wav_bytes(audio)
            audio_bytes += len(data)
            if audio_bytes > 10 * MIB:
                raise Error("Audio references must total at most 10 MiB")
            encoded.append((f"audio{index}", data, "audio/wav"))
    return encoded


def payload(kind, values, image_urls, audio_urls=()):
    validate(kind, values, strict=True)
    spec = PROFILES[kind]
    if len(image_urls) > spec["images"] or len(audio_urls) > (3 if kind == "video" else 0):
        raise Error("Reference URL count exceeds this model's limit")
    metadata = {"resolution": values.get("resolution", spec["default"]),
                "ratio": values.get("ratio", spec["ratios"][0])}
    body = {"model": spec["model"], "prompt": values["prompt"].strip(), "metadata": metadata}
    if image_urls:
        body["images"] = list(image_urls)
    if kind == "video":
        body["seconds"] = values.get("seconds", "5")
        if audio_urls:
            metadata["audio_urls"] = list(audio_urls)
    else:
        if values.get("seed", -1) >= 0:
            metadata["seed"] = values["seed"]
        if kind == "minimax_image":
            metadata["output_format"] = values.get("output_format", "jpeg")
    return body
