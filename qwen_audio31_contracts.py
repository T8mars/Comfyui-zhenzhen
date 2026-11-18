"""Qwen Audio 3.1 synthesis profiles and documented system voice IDs."""

import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit
from xml.etree import ElementTree

import torch

from .seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError, audio_to_wav_bytes


FLASH, NEXT, PLUS = MODELS = ["qwen-audio-3.1-tts-" + suffix for suffix in ("flash", "next", "plus")]
CATALOG = json.loads((Path(__file__).parent / "web" / "data" / "qwen_audio31_voices.json").read_text(encoding="utf-8"))
VOICES = {FLASH: [item["id"] for item in CATALOG["flash"]], PLUS: [item["id"] for item in CATALOG["plus"]]}
LANGUAGES = {FLASH: ["zh", "en"], PLUS: "zh en fr de ja ko ru pt th id vi es it ms fil ar".split()}
SYSTEM_FORMATS = ["mp3", "wav", "pcm", "opus"]
NEXT_FORMATS = ["wav", "mp3", "pcm"]
SYSTEM_RATES = ["8000", "12000", "16000", "22050", "24000", "44100", "48000"]
NEXT_RATES = ["8000", "16000", "24000", "44100", "48000"]


def reference_slots(kwargs):
    slots = []
    for key, value in kwargs.items():
        match = re.fullmatch(r"audio([0-9]+)", key)
        if value is None or not match:
            continue
        index = int(match[1])
        if not 1 <= index <= 3:
            raise SeedanceAPIError("Next accepts at most three audio references")
        slots.append((index, value))
    return sorted(slots)


def public_urls(value):
    if not isinstance(value, str):
        raise SeedanceAPIError("audio_urls must contain one public HTTP(S) URL per line")
    urls = [line.strip() for line in value.splitlines() if line.strip()]
    for url in urls:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise SeedanceAPIError("Audio references must be public HTTP(S) URLs without credentials")
    return urls


def _number(kwargs, key, default, minimum, maximum, integer=False):
    value = kwargs.get(key, default)
    if (type(value) not in ((int,) if integer else (int, float))
            or not minimum <= value <= maximum or not math.isfinite(value)):
        raise SeedanceAPIError(f"{key} must be between {minimum} and {maximum}")
    return value


def _boolean(kwargs, key):
    value = kwargs.get(key, False)
    if type(value) is not bool:
        raise SeedanceAPIError(f"{key} must be a boolean")
    return value


def payload(kwargs, uploaded=(), strict=True):
    model = kwargs.get("model", FLASH)
    if model not in MODELS:
        raise SeedanceAPIError("Unsupported Qwen Audio 3.1 model")
    next_model = model == NEXT
    maximum = 3000 if next_model else 20000
    prompt = kwargs.get("prompt", "")
    if not isinstance(prompt, str) or len(prompt) > maximum or (strict and not prompt.strip()):
        raise SeedanceAPIError(f"prompt must contain 1-{maximum} characters")
    fmt = kwargs.get("output_format", "api_default")
    fmt = ("wav" if next_model else "mp3") if fmt == "api_default" else fmt
    rate = kwargs.get("sample_rate", "api_default")
    rate = ("48000" if next_model else "22050") if rate == "api_default" else rate
    if fmt not in (NEXT_FORMATS if next_model else SYSTEM_FORMATS):
        raise SeedanceAPIError("Unsupported audio output format for this model")
    if rate not in (NEXT_RATES if next_model else SYSTEM_RATES) or fmt == "opus" and rate in ("22050", "44100"):
        raise SeedanceAPIError("Unsupported sample rate for this model and format")
    seed = _number(kwargs, "seed", -1, -1, 2147483647 if next_model else 65535, integer=True)
    metadata = {"format": fmt, "sample_rate": rate,
                "rate": _number(kwargs, "rate", 1.0, .5, 2),
                "volume": _number(kwargs, "volume", 50, 0, 100, integer=True),
                "enable_aigc_tag": _boolean(kwargs, "enable_aigc_tag")}
    slots = reference_slots(kwargs)
    urls = public_urls(kwargs.get("audio_urls", ""))
    if len(urls) + max(len(slots), len(uploaded)) > 3:
        raise SeedanceAPIError("Local and URL audio references combined must not exceed three")
    if next_model:
        channels = kwargs.get("channels", "2")
        if channels not in ("1", "2"):
            raise SeedanceAPIError("Next channels must be 1 or 2")
        metadata["channels"] = channels
        if fmt == "mp3":
            metadata["enable_cbr"] = _boolean(kwargs, "enable_cbr")
        if uploaded or urls:
            metadata["audio_urls"] = [*uploaded, *urls]
        if strict:
            for index in re.findall(r"@voice([0-9]{1,9})(?![0-9])", prompt, re.IGNORECASE):
                if not 1 <= int(index) <= len(urls) + max(len(slots), len(uploaded)):
                    raise SeedanceAPIError(f"@voice{index} does not have a matching reference")
    else:
        if slots or urls or uploaded:
            raise SeedanceAPIError("Only Next accepts reference audio")
        voice = kwargs.get("voice", "api_default")
        if voice == "api_default":
            voice = VOICES[model][0]
        if voice not in VOICES[model]:
            raise SeedanceAPIError("Selected voice is not in this model's system voice list")
        metadata.update(voice=voice, pitch=_number(kwargs, "pitch", 1.0, .5, 2),
                        enable_ssml=_boolean(kwargs, "enable_ssml"))
        language = kwargs.get("language_hint", "api_default")
        if language != "api_default":
            if language not in LANGUAGES[model]:
                raise SeedanceAPIError("Unsupported language hint for this model")
            metadata["language_hint"] = language
        instruction = kwargs.get("instruction", "")
        if not isinstance(instruction, str):
            raise SeedanceAPIError("instruction must be text")
        if instruction.strip():
            metadata["instruction"] = instruction
        if strict and metadata["enable_ssml"]:
            try:
                if "<!" in prompt or ElementTree.fromstring(prompt).tag != "speak":
                    raise ValueError("not a safe speak element")
            except (ValueError, ElementTree.ParseError):
                raise SeedanceAPIError("SSML mode requires valid <speak>...</speak> text") from None
    body = {"model": model, "prompt": prompt, "metadata": metadata}
    if seed >= 0:
        body["seed"] = seed
    return body


def encode_references(kwargs):
    encoded = []
    for index, audio in reference_slots(kwargs):
        waveform = audio.get("waveform") if isinstance(audio, dict) else None
        rate = audio.get("sample_rate") if isinstance(audio, dict) else None
        if (not isinstance(waveform, torch.Tensor) or waveform.ndim != 3 or waveform.shape[0] != 1
                or not 1 <= waveform.shape[1] <= 2 or waveform.shape[2] < 1
                or type(rate) is not int or rate < 1 or waveform.shape[2] > 30 * rate
                or not torch.isfinite(waveform).all()):
            raise SeedanceAPIError("Each audio reference requires finite mono/stereo AUDIO of at most 30 seconds")
        data = audio_to_wav_bytes(audio)
        if len(data) > 10_000_000:
            raise SeedanceAPIError("Reference WAV exceeds 10 MB; use a smaller audio file or supported public URL")
        encoded.append((index, data))
    return encoded
