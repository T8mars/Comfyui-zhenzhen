"""ByteDance Seed-TTS 3.0 on the Low Price channel."""

from collections import Counter
import json
from math import isfinite
from pathlib import Path

from . import seedance_low_price_nodes as api
from .nov21_contracts import text
from .nov21_low_price_nodes import OPTIONS, PROMPT, _LowPriceNode, combo, result

KEY = "T8Zhenzhen_Seed_TTS_30_LowPrice"
MODEL = "bytedance-seed/seed-tts-3-0"
DEFAULT = "sarah"
CATALOG = json.loads((Path(__file__).parent / "web/data/seed_tts_30_voices.json").read_text(encoding="utf-8"))
_counts = Counter(CATALOG.values())
_aliases = {short: full for full, short in CATALOG.items() if _counts[short] == 1}
VOICE_OPTIONS = sorted(short if short in _aliases else full for full, short in CATALOG.items())


class T8ZhenzhenSeedTTS30(_LowPriceNode):
    RETURN_TYPES = (api.AUDIO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio", "audio_url", "task_id", "response")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": PROMPT, "voice": combo(VOICE_OPTIONS, DEFAULT), "instructions": PROMPT,
            "speed": ("FLOAT", {"default": 1.0, "min": .5, "max": 2.0, "step": .05})}, "optional": OPTIONS.copy()}

    @staticmethod
    def plan(values, strict=False):
        prompt = text(values, "prompt", 5000, required=strict)
        instructions = text(values, "instructions", 1000)
        raw_voice = text(values, "voice", default=DEFAULT).strip().casefold() or DEFAULT
        voice = _aliases.get(raw_voice, raw_voice)
        if voice not in CATALOG:
            raise api.SeedanceLowPriceError("Choose a Seed-TTS 3.0 voice by short name or full catalog ID")
        speed = values.get("speed", 1.0)
        if type(speed) not in (int, float) or not isfinite(speed) or not .5 <= speed <= 2:
            raise api.SeedanceLowPriceError("Seed-TTS 3.0 speed must be between 0.5 and 2.0")
        metadata = {"voice": voice, "speed": speed, "format": "wav"}
        if instructions.strip():
            metadata["instructions"] = instructions
        return {"model": MODEL, "prompt": prompt, "metadata": metadata}

    def prepare(self, values):
        return self.plan(values, strict=True)

    def run(self, body, config, progress):
        task, _ = api.submit_audio_task(body, config, retry_server_errors=False)
        progress(20)
        final = api.poll_audio_task(task, config, on_progress=lambda value: progress(20 + value * .75))
        url = api.extract_audio_url(final)
        audio = api.download_audio(url, "wav", 24000)
        progress(100)
        return result((audio, url), task, final, [url])

    def error_result(self, message):
        return result((api.make_error_audio(), ""), "", {"error": message}, [message])
