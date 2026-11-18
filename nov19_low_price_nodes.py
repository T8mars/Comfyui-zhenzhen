"""Kling 4 Image, MAI Image 2.7 and Qwen Audio 3.1 for the Low Price channel."""

import json

from . import seedance_low_price_nodes as api
from . import nov19_image_contracts as images, qwen_audio31_contracts as speech
from .h3_turbo_low_price_nodes import get_config
from .execution_seed import EXECUTION_SEED_SPEC

KEYS = {"kling": "T8Zhenzhen_Kling_V4_Image_LowPrice",
        "mai": "T8Zhenzhen_MAI_Image_27_LowPrice",
        "audio": "T8Zhenzhen_Qwen_Audio_31_TTS_LowPrice"}


class _ImageNode:
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    ZHENZHEN_VALIDATE_CONCURRENT_AT_EXECUTION = True

    @classmethod
    def image_inputs(cls, count):
        return {"prompt": ("STRING", {"default": "", "multiline": True})}, {
            **{f"image{i}": ("IMAGE",) for i in range(1, count + 1)},
            "api_config": (api.CONFIG_TYPE,), "skip_error": ("BOOLEAN", {"default": False}),
            "seed": EXECUTION_SEED_SPEC,
        }

    @classmethod
    def VALIDATE_INPUTS(cls, strict=False, **values):
        try:
            checked = values if strict else {name: value for name, value in values.items() if value is not None}
            images.payload(cls.KIND, checked, strict=strict)
            return True
        except (api.SeedanceLowPriceError, ValueError) as error:
            return str(error)

    def execute(self, api_config=None, skip_error=False, **values):
        try:
            images.payload(self.KIND, values)
            encoded = images.encode_references(self.KIND, values)
            config = get_config(api_config)
            uploaded = [api.upload_media(data, f"reference_{index}.png", "image/png", config) for index, data in encoded]
            body = images.payload(self.KIND, values, images=uploaded)
            task, _ = api.submit_image_task(body, config, retry_server_errors=False)
            final = api.poll_image_task(task, config)
            urls = api.extract_image_urls(final)
            warnings = []
            if self.KIND == "kling":
                expected = body.get("sequential_image_generation_options", {}).get("max_images", body.get("n", 1))
                if len(urls) != expected:
                    warnings.append(f"Kling returned {len(urls)} images instead of {expected}; all returned images are included.")
            elif len(urls) != 1:
                raise api.SeedanceLowPriceError("MAI must return exactly one image")
            outputs = [api.download_image(url) for url in urls]
            media = (outputs, urls) if self.KIND == "kling" else (outputs[0], urls[0])
            return {"ui": {"text": [*warnings, *urls]}, "result": (*media, task, json.dumps(final, ensure_ascii=False))}
        except Exception as error:
            if not skip_error:
                raise
            image = api.torch.zeros(1, 64, 64, 3)
            media = ([image], [""]) if self.KIND == "kling" else (image, "")
            return {"ui": {"text": [str(error)]}, "result": (*media, "", json.dumps({"error": str(error)}, ensure_ascii=False))}


class T8ZhenzhenKlingV4Image(_ImageNode):
    KIND = "kling"
    RETURN_NAMES = ("images", "image_urls", "task_id", "response")
    OUTPUT_IS_LIST = (True, True, False, False)
    COMFLY_CONCURRENT_DISABLED = True

    @classmethod
    def INPUT_TYPES(cls):
        required, optional = cls.image_inputs(10)
        required.update(size=(images.KLING_SIZES, {"default": "auto"}),
                        resolution=(["2k", "4k"], {"default": "2k"}),
                        sequential_image_generation=(["disabled", "auto"], {"default": "disabled"}),
                        n=("INT", {"default": 1, "min": 1, "max": 9}),
                        max_images=("INT", {"default": 2, "min": 2, "max": 4}),
                        nsfw_check=("BOOLEAN", {"default": False}))
        return {"required": required, "optional": optional}


class T8ZhenzhenMAIImage27(_ImageNode):
    KIND = "mai"

    @classmethod
    def INPUT_TYPES(cls):
        required, optional = cls.image_inputs(5)
        required = {"model": (images.MAI_MODELS, {"default": images.MAI_MODELS[0]}), **required}
        maximum = images.MAI_MAX_PIXELS // 768
        required.update(resolution=(["1k", "2k"], {"default": "1k"}),
                        size=(images.MAI_SIZES, {"default": "1:1"}),
                        custom_ratio=("STRING", {"default": "16:9"}),
                        width=("INT", {"default": 1536, "min": 768, "max": maximum}),
                        height=("INT", {"default": 1024, "min": 768, "max": maximum}),
                        background=(["auto", "opaque"], {"default": "auto"}),
                        nsfw_check=("BOOLEAN", {"default": False}))
        return {"required": required, "optional": optional}


class T8ZhenzhenQwenAudio31:
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = (api.AUDIO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio", "audio_url", "task_id", "response")

    @classmethod
    def INPUT_TYPES(cls):
        spec, default = speech, "api_default"
        return {"required": {
            "model": (spec.MODELS, {"default": spec.FLASH}),
            "prompt": ("STRING", {"default": "", "multiline": True}),
            "voice": ([default, *spec.VOICES[spec.FLASH], *spec.VOICES[spec.PLUS]], {"default": default, "zhenzhen_voice_profiles": spec.VOICES}),
            "instruction": ("STRING", {"default": "", "multiline": True}),
            "language_hint": ([default, *spec.LANGUAGES[spec.PLUS]], {"default": default}),
            "rate": ("FLOAT", {"default": 1.0, "min": .5, "max": 2.0, "step": .05}),
            "pitch": ("FLOAT", {"default": 1.0, "min": .5, "max": 2.0, "step": .05}),
            "volume": ("INT", {"default": 50, "min": 0, "max": 100}),
            "output_format": ([default, *spec.SYSTEM_FORMATS], {"default": default}),
            "sample_rate": ([default, *spec.SYSTEM_RATES], {"default": default}),
            "channels": (["1", "2"], {"default": "2"}),
            "enable_ssml": ("BOOLEAN", {"default": False}),
            "enable_cbr": ("BOOLEAN", {"default": False}),
            "enable_aigc_tag": ("BOOLEAN", {"default": False}),
            "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647, "control_after_generate": True}),
        }, "optional": {
            **{f"audio{i}": (api.AUDIO_TYPE,) for i in range(1, 4)},
            "audio_urls": ("STRING", {"default": "", "multiline": True}),
            "api_config": (api.CONFIG_TYPE,), "skip_error": ("BOOLEAN", {"default": False}),
        }}

    @classmethod
    def VALIDATE_INPUTS(cls, strict=False, **values):
        try:
            checked = values if strict else {name: value for name, value in values.items() if value is not None}
            speech.payload(checked, strict=strict)
            return True
        except (api.SeedanceLowPriceError, ValueError) as error:
            return str(error)

    def execute(self, api_config=None, skip_error=False, **values):
        try:
            speech.payload(values)
            encoded = speech.encode_references(values)
            config = get_config(api_config)
            urls = [api.upload_media(data, f"voice_{index}.wav", "audio/wav", config) for index, data in encoded]
            body = speech.payload(values, uploaded=urls)
            task, _ = api.submit_audio_task(body, config, retry_server_errors=False)
            final = api.poll_audio_task(task, config)
            url = api.extract_audio_url(final)
            metadata = body["metadata"]
            format_ = "ogg_opus" if metadata["format"] == "opus" else metadata["format"]
            audio = api.download_audio(url, format_, int(metadata["sample_rate"]), pcm_channels=int(metadata.get("channels", "1")))
            return {"ui": {"text": [url]}, "result": (audio, url, task, json.dumps(final, ensure_ascii=False))}
        except Exception as error:
            if not skip_error:
                raise
            return {"ui": {"text": [str(error)]}, "result": (api.make_error_audio(), "", "", json.dumps({"error": str(error)}, ensure_ascii=False))}


CLASSES = {"kling": T8ZhenzhenKlingV4Image, "mai": T8ZhenzhenMAIImage27, "audio": T8ZhenzhenQwenAudio31}
