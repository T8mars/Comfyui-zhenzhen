"""Doubao Seed TTS 2.0 synthesis and the published 2.0 voice catalog."""

import json
import math
from pathlib import Path

from .seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError


MODEL = "doubao-seed-tts-2.0"
VIVI = "zh_female_vv_uranus_bigtts"
CATALOG = json.loads((Path(__file__).parent / "web" / "data" / "doubao_tts_voices.json").read_text(encoding="utf-8"))
VOICES = {row["id"]: row for row in CATALOG["voices"]}
LANGUAGES = ["api_default", "zh-cn", "en", "ja", "es-mx", "id", "pt-br", "pt", "ko", "de", "fr", "th", "vi", "ru", "fil", "ms", "ar"]
FORMATS = ["mp3", "wav", "pcm", "ogg_opus"]
SAMPLE_RATES = ["8000", "16000", "22050", "24000", "32000", "44100", "48000"]
VOICE_MODELS = ["api_default", "seed-tts-2.0-standard", "seed-tts-2.0-expressive"]
OPTIONAL_BOOLEAN = ["api_default", "enabled", "disabled"]
BOOLEANS = ["disable_default_bit_rate", "disable_markdown_filter", "enable_latex_tn", "disable_emoji_filter",
            "enable_subtitle", "tone_fidelity", "aigc_watermark", "aigc_metadata_enable"]
STRINGS = ["section_id", "aigc_metadata_content_producer", "aigc_metadata_produce_id",
           "aigc_metadata_content_propagator", "aigc_metadata_propagate_id"]
ADVANCED = ["voice_model", "explicit_dialect", "bit_rate", "silence_duration", "max_length_to_filter_parenthesis",
            "latex_parser", "ssml", *BOOLEANS, *STRINGS]


def validate(kwargs, strict=False):
    for name, maximum in (("prompt", 10000), ("context_texts", 500), ("ssml", 2000), *[(name, 128) for name in STRINGS]):
        value = kwargs.get(name)
        if value is not None and (not isinstance(value, str) or len(value) > maximum):
            raise SeedanceAPIError(f"{name} must be text of at most {maximum} characters")
    speaker = kwargs.get("speaker", VIVI)
    if not isinstance(speaker, str) or not speaker.strip():
        raise SeedanceAPIError("speaker must be a voice ID")
    if strict and (not isinstance(kwargs.get("prompt"), str) or not kwargs["prompt"].strip()):
        raise SeedanceAPIError("Synthesis text is required (1-10000 characters)")
    enums = {"output_format": FORMATS, "sample_rate": SAMPLE_RATES, "explicit_language": LANGUAGES,
             "voice_model": VOICE_MODELS, "explicit_dialect": ["api_default", "dongbei", "shaanxi", "sichuan"],
             "max_length_to_filter_parenthesis": ["api_default", "0", "100"], "latex_parser": ["api_default", "v2"]}
    defaults = {"output_format": "mp3", "sample_rate": "24000"}
    for name, values in enums.items():
        if kwargs.get(name, defaults.get(name, "api_default")) not in values:
            raise SeedanceAPIError("Unsupported Doubao TTS " + name)
    for name in BOOLEANS:
        if kwargs.get(name, "api_default") not in OPTIONAL_BOOLEAN:
            raise SeedanceAPIError(name + " must be api_default, enabled or disabled")
    for name, low, high in (("speech_rate", -50, 100), ("loudness_rate", -50, 100), ("pitch", -12, 12), ("silence_duration", 0, 30000)):
        value = kwargs.get(name, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise SeedanceAPIError(f"{name} must be between {low} and {high}")
    bit_rate = kwargs.get("bit_rate", 0)
    if type(bit_rate) is not int or bit_rate != 0 and not (64000 <= bit_rate <= 160000 or kwargs.get("disable_default_bit_rate") == "enabled" and bit_rate in (16000, 32000)):
        raise SeedanceAPIError("bit_rate requires 64000-160000; enabled low-rate mode also accepts 16000/32000")
    builtin = speaker in VOICES or "uranus" in speaker
    if builtin and kwargs.get("voice_model", "api_default") != "api_default":
        raise SeedanceAPIError("Library voices must not specify voice_model")
    if builtin and kwargs.get("ssml", ""):
        raise SeedanceAPIError("2.0 library voices do not support SSML; use voice instructions")
    if kwargs.get("explicit_dialect", "api_default") != "api_default":
        if speaker != VIVI or kwargs.get("explicit_language", "api_default") not in ("api_default", "zh-cn"):
            raise SeedanceAPIError("Dialect selection requires Vivi with automatic/Chinese synthesis language")
    if kwargs.get("latex_parser") == "v2" or kwargs.get("enable_latex_tn") == "enabled":
        if kwargs.get("disable_markdown_filter") != "enabled":
            raise SeedanceAPIError("LaTeX requires disable_markdown_filter=enabled (true enables filtering)")
    if kwargs.get("ssml", "") and kwargs.get("disable_markdown_filter") == "enabled":
        raise SeedanceAPIError("SSML cannot be combined with Markdown filtering")
    return True


def payload(kwargs):
    validate(kwargs, strict=True)
    metadata = {"speaker": kwargs.get("speaker", VIVI).strip(), "format": kwargs.get("output_format", "mp3"),
                "sample_rate": kwargs.get("sample_rate", "24000")}
    for name in ("speech_rate", "loudness_rate", "pitch", "silence_duration"):
        if kwargs.get(name, 0):
            metadata[name] = kwargs[name]
    voice_model = kwargs.get("voice_model", "api_default")
    if voice_model != "api_default":
        metadata["voice_model"] = voice_model
    elif kwargs.get("context_texts", ""):
        metadata["context_texts"] = kwargs["context_texts"]
    for name in ("explicit_language", "explicit_dialect", "latex_parser"):
        if kwargs.get(name, "api_default") != "api_default":
            metadata[name] = kwargs[name]
    if kwargs.get("bit_rate", 0):
        metadata["bit_rate"] = kwargs["bit_rate"]
    if kwargs.get("max_length_to_filter_parenthesis", "api_default") != "api_default":
        metadata["max_length_to_filter_parenthesis"] = int(kwargs["max_length_to_filter_parenthesis"])
    for name in BOOLEANS:
        if kwargs.get(name, "api_default") != "api_default":
            metadata[name] = kwargs[name] == "enabled"
    for name in STRINGS:
        if kwargs.get(name, ""):
            metadata[name] = kwargs[name]
    if kwargs.get("ssml", ""):
        metadata.update(ssml=kwargs["ssml"], disable_markdown_filter=False)
    return {"model": MODEL, "prompt": kwargs["prompt"], "metadata": metadata}
