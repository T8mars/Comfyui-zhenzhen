"""Seedance 2.5 Flash parameter and pre-upload material limits."""

import re

import torch

try:
    from .seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError, audio_to_wav_bytes, image_to_png_bytes, video_to_upload_bytes as video_to_bytes
    from .kling_v4_low_price_nodes import probe_video
except ImportError:
    from seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError, audio_to_wav_bytes, image_to_png_bytes, video_to_upload_bytes as video_to_bytes
    from kling_v4_low_price_nodes import probe_video


MODELS = [f"seedance-2.5-{region}flash-{mode}" for region in ("", "global-") for mode in ("t2v", "i2v", "multi")]
LIMITS = {"image": 10, "video": 5, "audio": 5}


def validate(kwargs, strict=False):
    model = kwargs["model"]
    if kwargs.get("resolution", "480p") not in ("480p", "720p"):
        raise SeedanceAPIError("Seedance Flash supports only 480p and 720p")
    if kwargs.get("draft", False):
        raise SeedanceAPIError("Seedance Flash does not support draft mode")
    if model.endswith("-i2v") and kwargs.get("ratio", "adaptive") != "adaptive":
        raise SeedanceAPIError("Seedance Flash I2V requires ratio=adaptive")
    counts = {family: 0 for family in LIMITS}
    for name, value in kwargs.items():
        match = re.fullmatch(r"(image|video|audio)(\d+)", name)
        if not match or value is None:
            continue
        family, index = match[1], int(match[2])
        limit = LIMITS[family] if model.endswith("-multi") else 2 if family == "image" and model.endswith("-i2v") else 0
        if not 1 <= index <= limit:
            raise SeedanceAPIError(f"Seedance Flash {model.rsplit('-', 1)[-1]} accepts at most {limit} {family} inputs")
        counts[family] += 1
    if strict:
        if model.endswith("-i2v") and kwargs.get("image1") is None:
            raise SeedanceAPIError("Flash I2V requires image1 as the first frame")
        if model.endswith("-multi") and not any(counts.values()):
            raise SeedanceAPIError("Flash Multi requires at least one reference material")
        task_type = kwargs.get("omni_reference_task_type", "auto")
        if model.endswith("-multi") and task_type in ("edit", "extend"):
            if not counts["video"] or kwargs.get("ratio", "adaptive") != "adaptive":
                raise SeedanceAPIError("Flash video edit/extend requires a video and adaptive ratio")
            if task_type == "edit" and str(kwargs.get("seconds", "4")) != "-1":
                raise SeedanceAPIError("Flash video edit requires automatic duration (-1)")
    return True


def encode_media(kwargs):
    validate(kwargs, strict=True)
    encoded, duration = [], 0.0
    for family in LIMITS:
        for index in range(1, LIMITS[family] + 1):
            value = kwargs.get(f"{family}{index}")
            if value is None:
                continue
            if family == "image":
                if not isinstance(value, torch.Tensor) or value.ndim != 4 or value.shape[0] != 1 or value.shape[-1] not in (3, 4) or not torch.isfinite(value).all():
                    raise SeedanceAPIError("Each Flash image input requires one finite RGB/RGBA IMAGE")
                data, extension, mime = image_to_png_bytes(value), "png", "image/png"
            elif family == "video":
                data, extension = video_to_bytes(value)
                info = probe_video(data, extension)
                seconds = info["duration"]
                if not 2 <= seconds <= 30:
                    raise SeedanceAPIError("Each Flash reference video must be 2-30 seconds")
                duration += seconds
                mime = {"mp4": "video/mp4", "avi": "video/x-msvideo", "mov": "video/quicktime", "mkv": "video/x-matroska"}.get(extension)
                if mime is None:
                    raise SeedanceAPIError("Unsupported Flash reference video container")
            else:
                wave = value.get("waveform") if isinstance(value, dict) else None
                rate = value.get("sample_rate") if isinstance(value, dict) else None
                if not isinstance(wave, torch.Tensor) or wave.ndim != 3 or wave.shape[0] != 1 or not 1 <= wave.shape[1] <= 2 or not torch.isfinite(wave).all() or type(rate) is not int or rate <= 0:
                    raise SeedanceAPIError("Invalid Flash reference AUDIO")
                if not 2 <= wave.shape[-1] / rate <= 30:
                    raise SeedanceAPIError("Each Flash reference audio must be 2-30 seconds")
                duration += wave.shape[-1] / rate
                data, extension, mime = audio_to_wav_bytes(value), "wav", "audio/wav"
            encoded.append((family, index, data, extension, mime))
    if duration > 30.000001:
        raise SeedanceAPIError("Flash reference video/audio duration must total at most 30 seconds")
    return encoded
