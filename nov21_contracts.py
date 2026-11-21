"""Request contracts for Kling Long Image, Gemini TTS, HeyGen, and Miora."""

import re
from urllib.parse import urlsplit

import torch

from .seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError, audio_to_wav_bytes, image_to_png_bytes
from .preview_muse_flux_low_price_nodes import references


LONG_IMAGE = "kling-v4-long-image"
GEMINI_TTS = ["zhenzhen/gm-2.5-pro-tts", "zhenzhen/gm-2.5-flash-tts"]
GEMINI_VOICES = ("Zephyr Puck Charon Kore Fenrir Leda Orus Aoede Callirrhoe Autonoe Enceladus Iapetus Umbriel "
                 "Algieba Despina Erinome Algenib Rasalgethi Laomedeia Achernar Alnilam Schedar Gacrux "
                 "Pulcherrima Achird Zubenelgenubi Vindemiatrix Sadachbia Sadaltager Sulafat").split()
HEYGEN = ["heygen-avatar-6-turbo", "heygen-avatar-6"]
HEYGEN_RATIOS = ["16:9", "9:16", "1:1", "4:5", "5:4"]
MIORA_VIEWS = ["front", "left", "right", "back", "top", "bottom", "front-left", "front-right"]


def text(kwargs, name, maximum=None, default="", required=False):
    value = kwargs.get(name, default)
    if not isinstance(value, str) or maximum is not None and len(value) > maximum or required and not value.strip():
        limit = f" (maximum {maximum} characters)" if maximum is not None else ""
        raise SeedanceAPIError(f"{name} must be {'nonempty ' if required else ''}text{limit}")
    return value


def choice(kwargs, key, choices):
    value = kwargs.get(key, choices[0])
    if value not in choices:
        raise SeedanceAPIError(f"Unsupported {key}")
    return value


def boolean(kwargs, key):
    value = kwargs.get(key, False)
    if type(value) is not bool:
        raise SeedanceAPIError(f"{key} must be boolean")
    return value


def public_url(url, https=False):
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
        return bool(parsed.scheme in (("https",) if https else ("http", "https"))
                    and parsed.hostname and not parsed.username and not parsed.password)
    except ValueError:
        return False


def image_bytes(image, label, maximum=None):
    if (not isinstance(image, torch.Tensor) or image.ndim != 4 or image.shape[0] != 1
            or image.shape[-1] not in (3, 4) or min(image.shape[1:3]) < 1 or not torch.isfinite(image).all()):
        raise SeedanceAPIError(f"{label} requires one finite RGB/RGBA IMAGE")
    data = image_to_png_bytes(image)
    if maximum is not None and len(data) > maximum:
        raise SeedanceAPIError(f"{label} exceeds the encoded image size limit")
    return data


def audio_bytes(audio, maximum=None, max_seconds=None):
    wave = audio.get("waveform") if isinstance(audio, dict) else None
    rate = audio.get("sample_rate") if isinstance(audio, dict) else None
    if (not isinstance(wave, torch.Tensor) or wave.ndim != 3 or wave.shape[0] != 1
            or not 1 <= wave.shape[1] <= 2 or wave.shape[2] < 1 or type(rate) is not int
            or rate < 1 or not torch.isfinite(wave).all()):
        raise SeedanceAPIError("Reference requires one finite mono/stereo AUDIO")
    if max_seconds is not None and wave.shape[2] > max_seconds * rate:
        raise SeedanceAPIError("Set the video duration to cover the driving audio")
    data = audio_to_wav_bytes(audio)
    if maximum is not None and len(data) > maximum:
        raise SeedanceAPIError("Encoded reference WAV exceeds the audio size limit")
    return data


def long_image(kwargs, strict=False):
    mode = text(kwargs, "skill", default="ecommerce").lower()
    if mode not in ("ecommerce", "webpage"):
        raise SeedanceAPIError("skill must be ecommerce or webpage")
    prompt = text(kwargs, "prompt", required=strict).strip()
    if len(prompt) > 166000 or len(re.findall(r"[\u3400-\u9fff]", prompt)) > 71000:
        raise SeedanceAPIError("Kling Long Image prompt exceeds its character limit")
    products = [(f"image{index}", value) for index, value in references(kwargs, 3)]
    roles = [(role, kwargs[f"{role}_image"]) for role in ("style", "subject")
             if kwargs.get(f"{role}_image") is not None]
    if mode == "ecommerce" and roles or mode == "webpage" and products:
        raise SeedanceAPIError("Use product images for ecommerce, or style/subject images for webpage")
    if strict and mode == "ecommerce" and not products:
        raise SeedanceAPIError("Ecommerce requires at least one product image")
    used = products if mode == "ecommerce" else roles
    if strict and any(not 1 <= int(index) <= len(used)
                      for index in re.findall(r"@Image([0-9]{1,9})(?![0-9])", prompt, re.I)):
        raise SeedanceAPIError("An @Image reference does not match an input")
    body = {"model": LONG_IMAGE, "prompt": prompt, "skill": mode,
            "resolution": choice(kwargs, "resolution", ("1k", "2k")), "nsfw_check": boolean(kwargs, "nsfw_check")}
    if mode == "ecommerce":
        body["length"] = choice(kwargs, "length", ("medium", "short", "long"))
    return body, used


def long_image_bytes(image, name):
    data = image_bytes(image, name, 30_000_000)
    height, width = image.shape[1:3]
    if min(height, width) < 300 or 5 * min(height, width) < 2 * max(height, width):
        raise SeedanceAPIError(f"{name} requires width and height >=300 pixels and an aspect ratio from 2:5 to 5:2")
    return data


def gemini_tts(kwargs, strict=False):
    prompt = text(kwargs, "prompt", 5000, required=strict)
    instructions = text(kwargs, "instructions", 1000)
    chosen = text(kwargs, "voice", default="Kore").strip().casefold()
    voice = next((option for option in GEMINI_VOICES if option.casefold() == chosen), None)
    if not voice:
        raise SeedanceAPIError("Choose one of the documented Gemini TTS voices")
    metadata = {"voice": voice, "format": "wav"}
    if instructions.strip():
        metadata["instructions"] = instructions
    return {"model": choice(kwargs, "model", [GEMINI_TTS[1], GEMINI_TTS[0]]), "prompt": prompt, "metadata": metadata}


def heygen(kwargs, strict=False):
    metadata = {"avatar": text(kwargs, "avatar", default="Abigail Sofa Front", required=True).strip(),
                "ratio": choice(kwargs, "ratio", HEYGEN_RATIOS),
                "resolution": choice(kwargs, "resolution", ("1080p", "2k"))}
    audio = kwargs.get("audio")
    url = text(kwargs, "audio_url").strip()
    if url and not public_url(url, https=True):
        raise SeedanceAPIError("HeyGen requires a public HTTPS audio URL")
    if url and audio is not None:
        raise SeedanceAPIError("Connect local audio or supply a URL, not both")
    motion = text(kwargs, "motion_prompt", 1200).strip()
    if motion:
        metadata["motion_prompt"] = motion
    body = {"model": choice(kwargs, "model", HEYGEN), "metadata": metadata}
    if url:
        metadata["audio_urls"] = [url]
    elif audio is None:
        body["prompt"] = text(kwargs, "prompt", 5000 if strict else None, required=strict)
        metadata["voice"] = text(kwargs, "voice", default="Warm Pro Narrator", required=strict).strip()
    return body


def miora(kwargs, strict=False):
    views = references(kwargs, 8)
    if strict and [i for i, _ in views] != list(range(1, 1 + len(views))):
        raise SeedanceAPIError("Connect Miora views in order without leaving holes, starting with the front view")
    mode = choice(kwargs, "generate_type", ("normal", "geometry"))
    count = kwargs.get("face_count", 500000)
    if type(count) is not int or not 3000 <= count <= 1500000:
        raise SeedanceAPIError("face_count must be an integer between 3000 and 1500000")
    body = {"model": "miora-3d", "generate_type": mode, "face_count": count}
    if mode == "normal":
        body["enable_pbr"] = boolean(kwargs, "enable_pbr")
    if not views:
        body["prompt"] = text(kwargs, "prompt", required=strict).strip()
    return body, views


def miora_urls(final):
    data = final.get("data") if isinstance(final, dict) else None
    if not isinstance(data, dict):
        raise SeedanceAPIError("Miora returned no task data")
    nested = data.get("data")
    content = nested.get("content") if isinstance(nested, dict) else None
    content = content if isinstance(content, dict) else {}
    urls = content.get("file_urls")
    if urls is None or urls == []:
        urls = [content.get("file_url") or data.get("result_url")]
    if not isinstance(urls, list) or not urls or not all(public_url(url) for url in urls):
        raise SeedanceAPIError("Miora returned no valid 3D file URLs")
    return list(dict.fromkeys(urls))
