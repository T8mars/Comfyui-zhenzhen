"""Contracts for the four fixed-768p H3 workflow IDs."""

import re

from .seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError, video_to_upload_bytes as video_to_bytes
from .h3_comfy_contracts import CHARSWAP_MAX_IMAGES, FRAMES, MIB, image_references, slots, video_urls
from .nov21_contracts import audio_bytes, choice, image_bytes, text


PROFILES = {
    "wf": ("minimax-h3-comfyui-max-10020-token", 6, 3, 0, 5),
    "jy": ("minimax-h3-comfyui-max-10021-token", 6, 3, 1, 5),
    "charswap": ("minimax-h3-comfyui-charswap-token", CHARSWAP_MAX_IMAGES, 0, 1, 5),
    "digital": ("minimax-h3-comfyui-digital-human-token", 1, 1, 0, 3),
}
RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9"]


def image_socket_count(kind):
    return 5 if kind == "charswap" else PROFILES[kind][1]


def plan(kind, kwargs, strict=False):
    model, n_images, n_audio, n_video, min_seconds = PROFILES[kind]
    prompt = text(kwargs, "prompt", required=strict).strip()
    inputs = {
        "images": image_references(kwargs, n_images, image_socket_count(kind)),
        "audio_urls": slots(kwargs, "audio", n_audio),
        "video_url": slots(kwargs, "video", n_video),
    }
    remote_video = video_urls(kwargs.get("video_urls", ""))
    clip_count = len(inputs["video_url"]) + len(remote_video)
    if clip_count > n_video:
        raise SeedanceAPIError(f"At most {n_video} MP4 references are accepted")
    if strict:
        if not inputs["images"]:
            raise SeedanceAPIError("Connect at least one reference image")
        if kind == "charswap" and clip_count != 1:
            raise SeedanceAPIError("Character replacement requires exactly one source MP4")
        if kind == "digital" and len(inputs["audio_urls"]) != 1:
            raise SeedanceAPIError("Digital human requires one driving audio track")
        for label, key in (("Picture", "images"), ("Audio", "audio_urls")):
            tags = re.findall(r"<" + label + r"\s+([0-9]{1,9})>", prompt, re.I)
            if any(not 1 <= int(index) <= len(inputs[key]) for index in tags):
                raise SeedanceAPIError(f"<{label} n> has no matching reference")
    metadata = {"ratio": choice(kwargs, "ratio", ("auto",) if kind == "charswap" else RATIOS)}
    body = {"model": model, "prompt": prompt, "metadata": metadata}
    if kind == "charswap" and choice(kwargs, "duration_mode", ("seconds", "frames")) == "frames":
        frames = kwargs.get("frames", 124)
        if type(frames) is not int or frames not in FRAMES:
            raise SeedanceAPIError("frames must be 22..362 in steps of 17")
        metadata["frames"] = frames
    else:
        seconds = kwargs.get("seconds", "5")
        if seconds not in [str(i) for i in range(min_seconds, 16)]:
            raise SeedanceAPIError(f"seconds must be an integer string from {min_seconds} to 15")
        body["seconds"] = seconds
    if strict and remote_video:
        metadata["video_url"] = remote_video
    return body, inputs


def encode(kind, body, inputs):
    encoded = []
    for index, image in inputs["images"]:
        encoded.append(("images", f"image{index}.png", "image/png", image_bytes(image, f"image{index}", 10 * MIB)))
    for index, audio in inputs["audio_urls"]:
        maximum = int(body["seconds"]) if kind == "digital" else None
        encoded.append(("audio_urls", f"audio{index}.wav", "audio/wav", audio_bytes(audio, 10 * MIB, maximum)))
    for index, video in inputs["video_url"]:
        data, extension = video_to_bytes(video)
        if extension.lower() != "mp4" or data[4:8] != b"ftyp" or len(data) > 50 * MIB:
            raise SeedanceAPIError("Reference video must be a valid MP4 of up to 50 MiB")
        encoded.append(("video_url", f"video{index}.mp4", "video/mp4", data))
    return encoded
