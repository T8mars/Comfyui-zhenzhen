"""Doubao Seed TTS 2.0 with the published voice library."""

import json

from . import seedance_low_price_nodes as api, doubao_tts_contracts as contracts
from .h3_turbo_low_price_nodes import get_config
from .execution_seed import EXECUTION_SEED_SPEC


KEY = "T8Zhenzhen_Doubao_Seed_TTS_20_LowPrice"


class T8ZhenzhenDoubaoSeedTTS20:
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = (api.AUDIO_TYPE, "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio", "audio_url", "speaker", "task_id", "response")
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "prompt": ("STRING", {"default": "", "multiline": True}),
            "speaker": ("STRING", {"default": contracts.VIVI}),
            "context_texts": ("STRING", {"default": "", "multiline": True}),
            "explicit_language": (contracts.LANGUAGES, {"default": "api_default"}),
            "speech_rate": ("FLOAT", {"default": 0, "min": -50, "max": 100, "step": 1}),
            "loudness_rate": ("FLOAT", {"default": 0, "min": -50, "max": 100, "step": 1}),
            "pitch": ("FLOAT", {"default": 0, "min": -12, "max": 12, "step": 1}),
            "output_format": (contracts.FORMATS, {"default": "mp3"}),
            "sample_rate": (contracts.SAMPLE_RATES, {"default": "24000"}),
            "advanced_mode": ("BOOLEAN", {"default": False}),
            "voice_model": (contracts.VOICE_MODELS, {"default": "api_default"}),
            "explicit_dialect": (["api_default", "dongbei", "shaanxi", "sichuan"], {"default": "api_default"}),
            "bit_rate": ("INT", {"default": 0, "min": 0, "max": 160000, "step": 1000}),
            "silence_duration": ("INT", {"default": 0, "min": 0, "max": 30000}),
            "max_length_to_filter_parenthesis": (["api_default", "0", "100"], {"default": "api_default"}),
            "latex_parser": (["api_default", "v2"], {"default": "api_default"}),
            "ssml": ("STRING", {"default": "", "multiline": True}),
            **{name: (contracts.OPTIONAL_BOOLEAN, {"default": "api_default"}) for name in contracts.BOOLEANS},
            **{name: ("STRING", {"default": ""}) for name in contracts.STRINGS},
        }, "optional": {"api_config": (api.CONFIG_TYPE,), "skip_error": ("BOOLEAN", {"default": False}), "seed": EXECUTION_SEED_SPEC}}

    @classmethod
    def VALIDATE_INPUTS(cls, strict=False, **values):
        try:
            checked = values if strict else {name: value for name, value in values.items() if value is not None}
            return contracts.validate(checked, strict)
        except api.SeedanceLowPriceError as error:
            return str(error)

    def execute(self, api_config=None, skip_error=False, **values):
        try:
            body = contracts.payload(values)
            config = get_config(api_config)
            task, _ = api.submit_audio_task(body, config)
            final = api.poll_audio_task(task, config)
            url = api.extract_audio_url(final)
            audio = api.download_audio(url, values.get("output_format", "mp3"), int(values.get("sample_rate", "24000")))
            return {"ui": {"text": [url]}, "result": (audio, url, body["metadata"]["speaker"], task, json.dumps(final, ensure_ascii=False))}
        except Exception as error:
            if not skip_error:
                raise
            return {"ui": {"text": [str(error)]}, "result": (api.make_error_audio(), "", "", "", json.dumps({"error": str(error)}, ensure_ascii=False))}
