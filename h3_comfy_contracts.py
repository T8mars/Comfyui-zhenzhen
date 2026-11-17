"""Individual contracts for the four documented H3 ComfyUI video workflows."""

import io
import re
from urllib.parse import urlsplit

import numpy as np
from PIL import Image
import torch

from .seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError, audio_to_wav_bytes, video_to_upload_bytes as video_to_bytes
from .preview_muse_flux_low_price_nodes import references


MIB = 1024 * 1024
PROFILES = {
    "charswap": {"model": "minimax-h3-comfyui-charswap", "images": 9, "audios": 0, "videos": 1,
                 "resolutions": ["480p", "768p", "1088p", "auto"], "default": "768p", "min_seconds": 5,
                 "image_mb": 10, "total_mb": 50, "seed": True},
    "wuxi": {"model": "minimax-h3-comfyui-wuxi", "images": 9, "audios": 3, "videos": 3,
             "resolutions": ["480p", "704p", "768p", "928p", "1088p", "1440p", "2160p"], "default": "480p", "min_seconds": 5,
             "image_mb": 10, "total_mb": 50, "seed": True},
    "wf": {"model": "minimax-h3-comfyui-max-10020", "images": 6, "audios": 3, "videos": 0,
           "resolutions": ["480p", "608p", "672p", "768p"], "default": "480p", "min_seconds": 3,
           "image_mb": 20, "total_mb": 80, "seed": False},
    "selflift": {"model": "minimax-h3-comfyui-max-10021", "images": 9, "audios": 3, "videos": 0,
                 "resolutions": ["480p", "608p", "672p", "768p"], "default": "480p", "min_seconds": 3,
                 "image_mb": 20, "total_mb": 80, "seed": False},
}
FRAMES = list(range(22, 363, 17))


def ratios(kind, resolution):
    if kind in ("wf", "selflift"):
        return ["16:9", "9:16"]
    if kind == "charswap":
        result = ["auto"]
        if resolution != "auto":
            result += ["16:9", "9:16"]
        if resolution == "768p":
            result += ["1:1", "4:3", "3:4", "21:9"]
        return result
    return ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"]


def slots(kwargs, family, maximum):
    result = []
    for name, value in kwargs.items():
        match = re.fullmatch(family + r"(\d+)", name)
        if match and value is not None:
            index = int(match[1])
            if not 1 <= index <= maximum:
                raise SeedanceAPIError(f"At most {maximum} {family} references are supported")
            result.append((index, value))
    return sorted(result)


def video_urls(value):
    if not isinstance(value, str):
        raise SeedanceAPIError("video_urls must contain one public HTTP(S) URL per line")
    urls = [line.strip() for line in value.splitlines() if line.strip()]
    for url in urls:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise SeedanceAPIError("Video references require public HTTP(S) URLs")
    return urls


def validate(kind, kwargs, strict=False):
    spec = PROFILES[kind]
    prompt = kwargs.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        raise SeedanceAPIError("prompt must be text")
    if strict and not (prompt or "").strip():
        raise SeedanceAPIError("A non-empty prompt is required")
    resolution = kwargs.get("resolution", spec["default"])
    if resolution not in spec["resolutions"]:
        raise SeedanceAPIError("Unsupported H3 resolution")
    if kwargs.get("ratio", ratios(kind, resolution)[0]) not in ratios(kind, resolution):
        raise SeedanceAPIError("Unsupported H3 aspect ratio for this resolution")
    duration_mode = kwargs.get("duration_mode", "seconds") if kind == "charswap" else "seconds"
    if duration_mode not in ("seconds", "frames"):
        raise SeedanceAPIError("duration_mode must be seconds or frames")
    if duration_mode == "frames":
        frame_count = kwargs.get("frames", 124)
        if type(frame_count) is not int or frame_count not in FRAMES:
            raise SeedanceAPIError("frames must be 22..362 in steps of 17")
    elif kwargs.get("seconds", "5") not in [str(i) for i in range(spec["min_seconds"], 16)]:
        raise SeedanceAPIError(f"seconds must be an integer string from {spec['min_seconds']} to 15")
    if spec["seed"]:
        seed = kwargs.get("seed", -1)
        if type(seed) is not int or not -1 <= seed <= 2147483647:
            raise SeedanceAPIError("seed must be -1 (omit) or 0..2147483647")
    images = references(kwargs, spec["images"])
    audios = slots(kwargs, "audio", spec["audios"])
    videos = slots(kwargs, "video", spec["videos"])
    urls = video_urls(kwargs.get("video_urls", ""))
    if len(videos) + len(urls) > spec["videos"]:
        raise SeedanceAPIError(f"At most {spec['videos']} video references are supported")
    if strict:
        if kind == "charswap" and (not images or len(videos) + len(urls) != 1):
            raise SeedanceAPIError("Character replacement requires 1-9 images and exactly one source video")
        if kind == "wuxi" and (videos or urls) and not images:
            raise SeedanceAPIError("Wuxi video references require at least one image")
        if kind == "selflift" and audios and not images:
            raise SeedanceAPIError("SelfLift audio references require at least one image")
        for family, count in (("Picture", len(images)), ("Audio", len(audios))):
            for index in re.findall(r"<" + family + r"\s+(\d+)>", prompt):
                if family == "Audio" and kind in ("charswap", "wuxi"):
                    raise SeedanceAPIError("Describe audio in words; this workflow does not support <Audio n> tags")
                if not 1 <= int(index) <= count:
                    raise SeedanceAPIError(f"<{family} {index}> exceeds the supplied reference count")
    return True


def encode_media(kind, kwargs):
    validate(kind, kwargs, strict=True)
    spec, encoded = PROFILES[kind], []
    for index, image in references(kwargs, spec["images"]):
        if not isinstance(image, torch.Tensor) or image.ndim != 4 or image.shape[0] != 1 or image.shape[-1] not in (3, 4) or min(image.shape[1:3]) < 1:
            raise SeedanceAPIError("Each image reference requires one RGB/RGBA IMAGE")
        if not torch.isfinite(image).all():
            raise SeedanceAPIError("Image contains non-finite pixels")
        buffer = io.BytesIO()
        Image.fromarray(np.clip(image.detach().cpu().numpy()[0] * 255, 0, 255).astype(np.uint8)).save(buffer, format="PNG")
        data = buffer.getvalue()
        if len(data) > spec["image_mb"] * MIB:
            raise SeedanceAPIError("Reference image exceeds this workflow's per-file limit")
        encoded.append((f"image{index}", data, "image/png"))
    if sum(len(data) for _, data, _ in encoded) > spec["total_mb"] * MIB:
        raise SeedanceAPIError("Reference images exceed this workflow's combined size limit")
    for index, audio in slots(kwargs, "audio", spec["audios"]):
        waveform = audio.get("waveform") if isinstance(audio, dict) else None
        rate = audio.get("sample_rate") if isinstance(audio, dict) else None
        if not isinstance(waveform, torch.Tensor) or waveform.ndim != 3 or waveform.shape[0] != 1 or not 1 <= waveform.shape[1] <= 2 or waveform.shape[2] < 1:
            raise SeedanceAPIError("Each audio reference requires one mono/stereo AUDIO")
        if type(rate) is not int or rate < 1 or not torch.isfinite(waveform).all():
            raise SeedanceAPIError("Invalid reference audio sample rate or samples")
        encoded.append((f"audio{index}", audio_to_wav_bytes(audio), "audio/wav"))
    if sum(len(data) for _, data, mime in encoded if mime == "audio/wav") > 10 * MIB:
        raise SeedanceAPIError("Audio references must total at most 10 MiB")
    for index, video in slots(kwargs, "video", spec["videos"]):
        data, extension = video_to_bytes(video)
        if extension.lower() != "mp4" or data[4:8] != b"ftyp":
            raise SeedanceAPIError("H3 video references must be MP4 files")
        encoded.append((f"video{index}", data, "video/mp4"))
    if sum(len(data) for _, data, mime in encoded if mime == "video/mp4") > 50 * MIB:
        raise SeedanceAPIError("Video references must total at most 50 MiB")
    return encoded


def payload(kind, kwargs, images, audios, videos):
    validate(kind, kwargs, strict=True)
    spec = PROFILES[kind]
    if len(images) > spec["images"] or len(audios) > spec["audios"] or len(videos) > spec["videos"]:
        raise SeedanceAPIError("Uploaded reference count exceeds this workflow's contract")
    metadata = {"resolution": kwargs.get("resolution", spec["default"]),
                "ratio": kwargs.get("ratio", ratios(kind, kwargs.get("resolution", spec["default"]))[0])}
    body = {"model": spec["model"], "prompt": kwargs["prompt"].strip(), "metadata": metadata}
    if kind == "charswap" and kwargs.get("duration_mode", "seconds") == "frames":
        metadata["frames"] = kwargs.get("frames", 124)
    else:
        body["seconds"] = kwargs.get("seconds", "5")
    if spec["seed"] and kwargs.get("seed", -1) >= 0:
        metadata["seed"] = kwargs["seed"]
    if images:
        body["images"] = list(images)
    if audios:
        metadata["audio_urls"] = list(audios)
    if videos:
        metadata["video_url"] = list(videos)
    return body
