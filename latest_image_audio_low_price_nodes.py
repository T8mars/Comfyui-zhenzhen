"""Latest Zhenzhen low-price image and audio generation nodes."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

import torch

try:
    from .seedance_low_price_nodes import (
        AUDIO_TYPE,
        COMFYUI_AVAILABLE,
        CONFIG_TYPE,
        SeedanceLowPriceError,
        VIDEO_TYPE,
        audio_to_wav_bytes,
        download_audio,
        download_image,
        download_suno_audio,
        download_suno_file,
        download_suno_video,
        extract_audio_url,
        extract_audio_urls,
        extract_image_url,
        extract_suno_results,
        image_to_png_bytes,
        make_error_audio,
        make_error_video,
        make_silent_audio,
        poll_audio_task,
        poll_image_task,
        poll_suno_task,
        resolve_config,
        submit_audio_task,
        submit_image_task,
        submit_suno_action,
        upload_media,
    )
except ImportError:
    from seedance_low_price_nodes import (
        AUDIO_TYPE,
        COMFYUI_AVAILABLE,
        CONFIG_TYPE,
        SeedanceLowPriceError,
        VIDEO_TYPE,
        audio_to_wav_bytes,
        download_audio,
        download_image,
        download_suno_audio,
        download_suno_file,
        download_suno_video,
        extract_audio_url,
        extract_audio_urls,
        extract_image_url,
        extract_suno_results,
        image_to_png_bytes,
        make_error_audio,
        make_error_video,
        make_silent_audio,
        poll_audio_task,
        poll_image_task,
        poll_suno_task,
        resolve_config,
        submit_audio_task,
        submit_image_task,
        submit_suno_action,
        upload_media,
    )

if COMFYUI_AVAILABLE:
    import comfy.utils


ZHENZHEN_IMAGE_GK_V2_MODEL = "zhenzhen-image-gk-v2"
ZHENZHEN_IMAGE_GK_V2_EDIT_MODEL = "zhenzhen-image-gk-v2-edit"
ZHENZHEN_IMAGE_GK_V2_SIZES = [
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "9:16",
    "16:9",
]
ZHENZHEN_IMAGE_GK_V2_EDIT_ASPECT_RATIOS = [
    "auto",
    "16:9",
    "19.5:9",
    "1:1",
    "1:2",
    "20:9",
    "2:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "9:16",
    "9:19.5",
    "9:20",
]
ZHENZHEN_IMAGE_GK_V2_EDIT_RESOLUTIONS = ["1k", "2k"]
ZHENZHEN_IMAGE_GK_V2_PROMPT_MAX_LENGTH = 20000
MAX_ZHENZHEN_IMAGE_GK_V2_EDIT_IMAGES = 3

WAN27_GLOBAL_T2I_MODEL = "wan-2.7-global-t2i"
WAN27_GLOBAL_I2I_MODEL = "wan-2.7-global-i2i"
WAN27_GLOBAL_I2I_PRO_MODEL = "wan-2.7-global-i2i-pro"
WAN27_GLOBAL_IMAGE_MODELS = [
    WAN27_GLOBAL_T2I_MODEL,
    WAN27_GLOBAL_I2I_MODEL,
    WAN27_GLOBAL_I2I_PRO_MODEL,
]
WAN27_GLOBAL_I2I_MODELS = [WAN27_GLOBAL_I2I_MODEL, WAN27_GLOBAL_I2I_PRO_MODEL]
WAN27_GLOBAL_T2I_PROMPT_MAX_LENGTH = 5000
WAN27_GLOBAL_I2I_PROMPT_MAX_LENGTH = 2048
MAX_WAN27_GLOBAL_IMAGES = 9

QWEN3_TTS_FLASH_MODEL = "qwen3-tts-flash"
QWEN3_TTS_INSTRUCT_FLASH_MODEL = "qwen3-tts-instruct-flash"
QWEN3_TTS_MODELS = [QWEN3_TTS_FLASH_MODEL, QWEN3_TTS_INSTRUCT_FLASH_MODEL]
QWEN3_TTS_LANGUAGE_TYPES = [
    "Chinese",
    "English",
    "Japanese",
    "Korean",
    "German",
    "French",
    "Russian",
    "Portuguese",
    "Spanish",
    "Italian",
]

MINIMAX_MUSIC_MODEL = "minimax-music-2.6"
MINIMAX_SPEECH_HD_MODEL = "minimax-speech-2.8-hd"
MINIMAX_SPEECH_TURBO_MODEL = "minimax-speech-2.8-turbo"
MINIMAX_VOICE_CLONE_MODEL = "minimax-voice-clone"
MINIMAX_AUDIO_MODELS = [
    MINIMAX_MUSIC_MODEL,
    MINIMAX_SPEECH_HD_MODEL,
    MINIMAX_SPEECH_TURBO_MODEL,
    MINIMAX_VOICE_CLONE_MODEL,
]
MINIMAX_SPEECH_MODELS = [MINIMAX_SPEECH_HD_MODEL, MINIMAX_SPEECH_TURBO_MODEL]
MINIMAX_AUDIO_FORMATS = ["mp3", "wav", "flac"]
MINIMAX_SAMPLE_RATES = ["16000", "24000", "32000", "44100"]
MINIMAX_BITRATES = ["32000", "64000", "128000", "256000"]
MINIMAX_LANGUAGE_BOOSTS = [
    "auto",
    "Chinese",
    "Chinese,Yue",
    "English",
    "Japanese",
    "Korean",
    "French",
    "German",
    "Spanish",
    "Portuguese",
    "Russian",
]

MUREKA_BGM_MODELS = ["mureka-v8-bgm", "mureka-v9-bgm"]

FLOWMUSIC_MODEL = "flowmusic"
FLOWMUSIC_VERSIONS = ["default", "lyria-3.5"]
FLOWMUSIC_FORMATS = ["mp3", "wav"]
FLOWMUSIC_VIDEO_PRESETS = ["simple", "modern", "player"]
FLOWMUSIC_ACTION_SPECS: Dict[str, Dict[str, Any]] = {
    "flowmusic-generation": {
        "action": "",
        "allowed_fields": (
            "version", "sound_prompt", "lyrics", "title", "bpm", "length", "seed",
        ),
        "required_fields": (),
        "result_family": "audio",
    },
    "flowmusic-lyrics": {
        "action": "lyrics",
        "allowed_fields": ("prompt",),
        "required_fields": ("prompt",),
        "result_family": "text",
    },
    "flowmusic-upload-audio": {
        "action": "upload-audio",
        "allowed_fields": ("audio_url",),
        "required_fields": ("audio_url",),
        "result_family": "audio",
    },
    "flowmusic-extend": {
        "action": "extend",
        "allowed_fields": (
            "version", "clip_id", "extend_from_s", "extend_s", "instruction", "title", "seed",
        ),
        "required_fields": ("clip_id", "extend_from_s", "extend_s", "instruction"),
        "result_family": "audio",
    },
    "flowmusic-replace": {
        "action": "replace",
        "allowed_fields": (
            "version", "clip_id", "start_s", "end_s", "instruction", "title", "seed",
        ),
        "required_fields": ("clip_id", "start_s", "end_s", "instruction"),
        "result_family": "audio",
    },
    "flowmusic-cover": {
        "action": "cover",
        "allowed_fields": (
            "version", "clip_id", "instruction", "strength", "title", "seed",
        ),
        "required_fields": ("clip_id", "instruction", "strength"),
        "result_family": "audio",
    },
    "flowmusic-stems": {
        "action": "stems",
        "allowed_fields": ("clip_id",),
        "required_fields": ("clip_id",),
        "result_family": "file",
    },
    "flowmusic-download-audio": {
        "action": "download-audio",
        "allowed_fields": ("clip_id", "format"),
        "required_fields": ("clip_id", "format"),
        "result_family": "audio",
    },
    "flowmusic-video-clip": {
        "action": "video-clip",
        "allowed_fields": ("clip_id", "preset"),
        "required_fields": ("clip_id", "preset"),
        "result_family": "video",
    },
}
FLOWMUSIC_OPERATIONS = list(FLOWMUSIC_ACTION_SPECS)


def _progress_bar():
    return comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None


def _update_progress(progress_bar, value: float) -> None:
    if progress_bar is not None:
        try:
            progress_bar.update_absolute(int(value), 100)
        except Exception:
            pass


def _image_error_result(model: str, error: Exception, task_id: str = ""):
    response = json.dumps(
        {
            "status": "error",
            "model": model,
            "message": f"{type(error).__name__}: {error}",
        },
        ensure_ascii=False,
        indent=2,
    )
    blank = torch.ones((1, 512, 512, 3), dtype=torch.float32)
    return blank, "", task_id, response


def _success_response(
    model: str,
    task_id: str,
    submit_response: Dict[str, Any],
    final_response: Dict[str, Any],
) -> str:
    return json.dumps(
        {
            "status": "SUCCESS",
            "model": model,
            "task_id": task_id,
            "submit": submit_response,
            "result": final_response,
        },
        ensure_ascii=False,
        indent=2,
    )


class Comfly_zhenzhen_image_gk_v2_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "size": (ZHENZHEN_IMAGE_GK_V2_SIZES, {"default": "1:1"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 12, "step": 1}),
            },
            "optional": {
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(cls, prompt=None, size=None, n=None, strict=False, **kwargs):
        prompt_text = str(prompt or "").strip()
        if strict and not prompt_text:
            return "Zhenzhen Image GK v2 requires a prompt"
        if len(prompt_text) > ZHENZHEN_IMAGE_GK_V2_PROMPT_MAX_LENGTH:
            return (
                "Zhenzhen Image GK v2 prompt cannot exceed "
                f"{ZHENZHEN_IMAGE_GK_V2_PROMPT_MAX_LENGTH} characters"
            )
        if size not in (None, *ZHENZHEN_IMAGE_GK_V2_SIZES):
            return f"Unsupported Zhenzhen Image GK v2 size: {size}"
        if n is not None and not 1 <= int(n) <= 12:
            return "Zhenzhen Image GK v2 n must be between 1 and 12"
        return True

    @staticmethod
    def _build_payload(prompt: str, size: str, n: int) -> Dict[str, Any]:
        return {
            "model": ZHENZHEN_IMAGE_GK_V2_MODEL,
            "prompt": str(prompt).strip(),
            "size": size,
            "n": int(n),
        }

    def generate(
        self,
        prompt: str,
        size: str,
        n: int,
        api_config: Any = None,
        skip_error: bool = False,
    ):
        task_id = ""
        try:
            validation = self.VALIDATE_INPUTS(
                prompt=prompt, size=size, n=n, strict=True
            )
            if validation is not True:
                raise SeedanceLowPriceError(validation)
            config = resolve_config(api_config)
            progress = _progress_bar()
            payload = self._build_payload(prompt, size, n)
            task_id, submitted = submit_image_task(payload, config)
            _update_progress(progress, 20)
            final = poll_image_task(
                task_id,
                config,
                on_progress=lambda value: _update_progress(
                    progress, 20 + value * 0.75
                ),
            )
            image_url = extract_image_url(final)
            image = download_image(image_url)
            _update_progress(progress, 100)
            return (
                image,
                image_url,
                task_id,
                _success_response(
                    ZHENZHEN_IMAGE_GK_V2_MODEL, task_id, submitted, final
                ),
            )
        except Exception as error:
            if not skip_error:
                raise
            return _image_error_result(
                ZHENZHEN_IMAGE_GK_V2_MODEL, error, task_id
            )


class Comfly_zhenzhen_image_gk_v2_edit_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {
            f"image{index}": ("IMAGE",)
            for index in range(1, MAX_ZHENZHEN_IMAGE_GK_V2_EDIT_IMAGES + 1)
        }
        optional["api_config"] = (CONFIG_TYPE,)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "aspect_ratio": (
                    ZHENZHEN_IMAGE_GK_V2_EDIT_ASPECT_RATIOS,
                    {"default": "auto"},
                ),
                "resolution": (
                    ZHENZHEN_IMAGE_GK_V2_EDIT_RESOLUTIONS,
                    {"default": "1k"},
                ),
                "n": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
                "nsfw_check": ("BOOLEAN", {"default": False}),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        prompt=None,
        aspect_ratio=None,
        resolution=None,
        n=None,
        strict=False,
        **kwargs,
    ):
        prompt_text = str(prompt or "").strip()
        if strict and not prompt_text:
            return "Zhenzhen Image GK v2 Edit requires an editing prompt"
        if len(prompt_text) > ZHENZHEN_IMAGE_GK_V2_PROMPT_MAX_LENGTH:
            return (
                "Zhenzhen Image GK v2 Edit prompt cannot exceed "
                f"{ZHENZHEN_IMAGE_GK_V2_PROMPT_MAX_LENGTH} characters"
            )
        if aspect_ratio not in (None, *ZHENZHEN_IMAGE_GK_V2_EDIT_ASPECT_RATIOS):
            return f"Unsupported Zhenzhen Image GK v2 Edit aspect_ratio: {aspect_ratio}"
        if resolution not in (None, *ZHENZHEN_IMAGE_GK_V2_EDIT_RESOLUTIONS):
            return f"Unsupported Zhenzhen Image GK v2 Edit resolution: {resolution}"
        if n is not None and not 1 <= int(n) <= 10:
            return "Zhenzhen Image GK v2 Edit n must be between 1 and 10"
        if strict and not any(
            kwargs.get(f"image{index}") is not None
            for index in range(1, MAX_ZHENZHEN_IMAGE_GK_V2_EDIT_IMAGES + 1)
        ):
            return "Zhenzhen Image GK v2 Edit requires 1-3 reference images"
        return True

    @staticmethod
    def _build_payload(
        prompt: str,
        image_urls: List[str],
        aspect_ratio: str,
        resolution: str,
        n: int,
        nsfw_check: bool,
    ) -> Dict[str, Any]:
        if not 1 <= len(image_urls) <= MAX_ZHENZHEN_IMAGE_GK_V2_EDIT_IMAGES:
            raise SeedanceLowPriceError(
                "Zhenzhen Image GK v2 Edit requires 1-3 reference images"
            )
        return {
            "model": ZHENZHEN_IMAGE_GK_V2_EDIT_MODEL,
            "prompt": str(prompt).strip(),
            "images": list(image_urls),
            "n": int(n),
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "nsfw_check": bool(nsfw_check),
        }

    def generate(
        self,
        prompt: str,
        aspect_ratio: str,
        resolution: str,
        n: int,
        nsfw_check: bool,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        try:
            validation = self.VALIDATE_INPUTS(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                n=n,
                strict=True,
                **kwargs,
            )
            if validation is not True:
                raise SeedanceLowPriceError(validation)
            config = resolve_config(api_config)
            progress = _progress_bar()
            images = [
                kwargs[f"image{index}"]
                for index in range(1, MAX_ZHENZHEN_IMAGE_GK_V2_EDIT_IMAGES + 1)
                if kwargs.get(f"image{index}") is not None
            ]
            image_urls = []
            for index, image in enumerate(images, start=1):
                image_urls.append(
                    upload_media(
                        image_to_png_bytes(image),
                        f"zhenzhen_image_gk_v2_edit_{index}.png",
                        "image/png",
                        config,
                    )
                )
                _update_progress(progress, index / len(images) * 15)
            payload = self._build_payload(
                prompt,
                image_urls,
                aspect_ratio,
                resolution,
                n,
                nsfw_check,
            )
            task_id, submitted = submit_image_task(payload, config)
            _update_progress(progress, 20)
            final = poll_image_task(
                task_id,
                config,
                on_progress=lambda value: _update_progress(
                    progress, 20 + value * 0.75
                ),
            )
            image_url = extract_image_url(final)
            image = download_image(image_url)
            _update_progress(progress, 100)
            return (
                image,
                image_url,
                task_id,
                _success_response(
                    ZHENZHEN_IMAGE_GK_V2_EDIT_MODEL,
                    task_id,
                    submitted,
                    final,
                ),
            )
        except Exception as error:
            if not skip_error:
                raise
            return _image_error_result(
                ZHENZHEN_IMAGE_GK_V2_EDIT_MODEL, error, task_id
            )


class Comfly_wan_2_7_global_image_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {
            f"image{index}": ("IMAGE",)
            for index in range(1, MAX_WAN27_GLOBAL_IMAGES + 1)
        }
        optional["api_config"] = (CONFIG_TYPE,)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        return {
            "required": {
                "model": (WAN27_GLOBAL_IMAGE_MODELS, {"default": WAN27_GLOBAL_T2I_MODEL}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "width": ("INT", {"default": 1024, "min": 512, "max": 4096, "step": 8}),
                "height": ("INT", {"default": 1024, "min": 512, "max": 4096, "step": 8}),
                "thinking_mode": ("BOOLEAN", {"default": True}),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt=None,
        width=None,
        height=None,
        strict=False,
        **kwargs,
    ):
        if model not in (None, *WAN27_GLOBAL_IMAGE_MODELS):
            return f"Unsupported Wan 2.7 Global image model: {model}"
        prompt_text = str(prompt or "").strip()
        if strict and not prompt_text:
            return "Wan 2.7 Global image requires a prompt"
        limit = (
            WAN27_GLOBAL_T2I_PROMPT_MAX_LENGTH
            if model in (None, WAN27_GLOBAL_T2I_MODEL)
            else WAN27_GLOBAL_I2I_PROMPT_MAX_LENGTH
        )
        if len(prompt_text) > limit:
            return f"Wan 2.7 Global prompt cannot exceed {limit} characters"
        if model in (None, WAN27_GLOBAL_T2I_MODEL):
            if width is not None and not 512 <= int(width) <= 4096:
                return "Wan 2.7 Global T2I width must be between 512 and 4096"
            if height is not None and not 512 <= int(height) <= 4096:
                return "Wan 2.7 Global T2I height must be between 512 and 4096"
        connected = sum(
            kwargs.get(f"image{index}") is not None
            for index in range(1, MAX_WAN27_GLOBAL_IMAGES + 1)
        )
        if (
            strict
            and model in WAN27_GLOBAL_I2I_MODELS
            and not 1 <= connected <= MAX_WAN27_GLOBAL_IMAGES
        ):
            return "Wan 2.7 Global I2I requires 1 to 9 images"
        return True

    @staticmethod
    def _build_payload(
        model: str,
        prompt: str,
        width: int,
        height: int,
        thinking_mode: bool,
        image_urls: List[str],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": str(prompt).strip(),
        }
        if model == WAN27_GLOBAL_T2I_MODEL:
            payload["metadata"] = {
                "width": int(width),
                "height": int(height),
                "thinking_mode": bool(thinking_mode),
            }
        else:
            if not 1 <= len(image_urls) <= MAX_WAN27_GLOBAL_IMAGES:
                raise SeedanceLowPriceError(
                    "Wan 2.7 Global I2I requires 1 to 9 images"
                )
            payload["images"] = list(image_urls)
        return payload

    def generate(
        self,
        model: str,
        prompt: str,
        width: int,
        height: int,
        thinking_mode: bool,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        try:
            validation = self.VALIDATE_INPUTS(
                model=model,
                prompt=prompt,
                width=width,
                height=height,
                strict=True,
                **kwargs,
            )
            if validation is not True:
                raise SeedanceLowPriceError(validation)
            config = resolve_config(api_config)
            progress = _progress_bar()
            references: List[Tuple[int, Any]] = []
            if model in WAN27_GLOBAL_I2I_MODELS:
                references = [
                    (index, kwargs.get(f"image{index}"))
                    for index in range(1, MAX_WAN27_GLOBAL_IMAGES + 1)
                    if kwargs.get(f"image{index}") is not None
                ]
            image_urls: List[str] = []
            for done, (slot, tensor) in enumerate(references, start=1):
                image_urls.append(
                    upload_media(
                        image_to_png_bytes(tensor),
                        f"wan_2_7_global_reference_{slot}.png",
                        "image/png",
                        config,
                    )
                )
                _update_progress(progress, done / len(references) * 15)
            payload = self._build_payload(
                model, prompt, width, height, thinking_mode, image_urls
            )
            task_id, submitted = submit_image_task(payload, config)
            _update_progress(progress, 20)
            final = poll_image_task(
                task_id,
                config,
                on_progress=lambda value: _update_progress(
                    progress, 20 + value * 0.75
                ),
            )
            image_url = extract_image_url(final)
            image = download_image(image_url)
            _update_progress(progress, 100)
            return (
                image,
                image_url,
                task_id,
                _success_response(model, task_id, submitted, final),
            )
        except Exception as error:
            if not skip_error:
                raise
            return _image_error_result(model, error, task_id)


class Comfly_qwen3_tts_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (QWEN3_TTS_MODELS, {"default": QWEN3_TTS_FLASH_MODEL}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "voice": ("STRING", {"default": "Cherry"}),
                "language_type": (QWEN3_TTS_LANGUAGE_TYPES, {"default": "Chinese"}),
                "instructions": ("STRING", {"multiline": True, "default": ""}),
                "optimize_instructions": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = (AUDIO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio", "audio_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls, model=None, prompt=None, voice=None, language_type=None, strict=False, **kwargs
    ):
        if model not in (None, *QWEN3_TTS_MODELS):
            return f"Unsupported Qwen3 TTS model: {model}"
        if strict and not str(prompt or "").strip():
            return "Qwen3 TTS requires text"
        if strict and not str(voice or "").strip():
            return "Qwen3 TTS requires a voice"
        if language_type not in (None, *QWEN3_TTS_LANGUAGE_TYPES):
            return f"Unsupported Qwen3 TTS language_type: {language_type}"
        return True

    @staticmethod
    def _build_payload(
        model: str,
        prompt: str,
        voice: str,
        language_type: str,
        instructions: str,
        optimize_instructions: bool,
    ) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "voice": str(voice).strip(),
            "language_type": language_type,
        }
        instruction_text = str(instructions or "").strip()
        if model == QWEN3_TTS_INSTRUCT_FLASH_MODEL and instruction_text:
            metadata["instructions"] = instruction_text
            metadata["optimize_instructions"] = bool(optimize_instructions)
        return {
            "model": model,
            "prompt": str(prompt).strip(),
            "metadata": metadata,
        }

    def generate(
        self,
        model: str,
        prompt: str,
        voice: str,
        language_type: str,
        instructions: str,
        optimize_instructions: bool,
        api_config: Any = None,
        skip_error: bool = False,
    ):
        task_id = ""
        try:
            validation = self.VALIDATE_INPUTS(
                model=model,
                prompt=prompt,
                voice=voice,
                language_type=language_type,
                strict=True,
            )
            if validation is not True:
                raise SeedanceLowPriceError(validation)
            config = resolve_config(api_config)
            progress = _progress_bar()
            payload = self._build_payload(
                model,
                prompt,
                voice,
                language_type,
                instructions,
                optimize_instructions,
            )
            task_id, submitted = submit_audio_task(payload, config)
            _update_progress(progress, 20)
            final = poll_audio_task(
                task_id,
                config,
                on_progress=lambda value: _update_progress(
                    progress, 20 + value * 0.75
                ),
            )
            audio_url = extract_audio_url(final)
            audio = download_audio(audio_url, "wav", 24000)
            _update_progress(progress, 100)
            return (
                audio,
                audio_url,
                task_id,
                _success_response(model, task_id, submitted, final),
            )
        except Exception as error:
            if not skip_error:
                raise
            response = json.dumps(
                {"status": "error", "model": model, "message": f"{type(error).__name__}: {error}"},
                ensure_ascii=False,
                indent=2,
            )
            return make_error_audio(24000), "", task_id, response


class Comfly_minimax_audio_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (MINIMAX_AUDIO_MODELS, {"default": MINIMAX_SPEECH_TURBO_MODEL}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "lyrics": ("STRING", {"multiline": True, "default": ""}),
                "is_instrumental": ("BOOLEAN", {"default": True}),
                "lyrics_optimizer": ("BOOLEAN", {"default": False}),
                "voice_id": ("STRING", {"default": "Wise_Woman"}),
                "speed": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.05}),
                "volume": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 10.0, "step": 0.1}),
                "pitch": ("INT", {"default": 0, "min": -12, "max": 12, "step": 1}),
                "language_boost": (MINIMAX_LANGUAGE_BOOSTS, {"default": "auto"}),
                "output_format": (MINIMAX_AUDIO_FORMATS, {"default": "mp3"}),
                "sample_rate": (MINIMAX_SAMPLE_RATES, {"default": "32000"}),
                "bitrate": (MINIMAX_BITRATES, {"default": "128000"}),
                "channel": (["1", "2"], {"default": "1"}),
                "custom_voice_id": ("STRING", {"default": "SeedanceVoice01"}),
                "clone_target_model": (MINIMAX_SPEECH_MODELS, {"default": MINIMAX_SPEECH_HD_MODEL}),
                "need_noise_reduction": ("BOOLEAN", {"default": False}),
                "need_volume_normalization": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "reference_audio": (AUDIO_TYPE,),
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = (AUDIO_TYPE, "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio", "audio_url", "result_text", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @staticmethod
    def _valid_custom_voice_id(value: Any) -> bool:
        text = str(value or "").strip()
        return bool(
            8 <= len(text) <= 256
            and text[0].isalpha()
            and text[-1] not in "-_"
            and all(character.isalnum() or character in "-_" for character in text)
        )

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt=None,
        lyrics=None,
        is_instrumental=None,
        lyrics_optimizer=None,
        voice_id=None,
        speed=None,
        volume=None,
        pitch=None,
        output_format=None,
        sample_rate=None,
        bitrate=None,
        channel=None,
        custom_voice_id=None,
        clone_target_model=None,
        reference_audio=None,
        strict=False,
        **kwargs,
    ):
        if model not in (None, *MINIMAX_AUDIO_MODELS):
            return f"Unsupported MiniMax audio model: {model}"
        if strict and not str(prompt or "").strip():
            return "MiniMax audio requires a prompt or speech text"
        if output_format not in (None, *MINIMAX_AUDIO_FORMATS):
            return f"Unsupported MiniMax output_format: {output_format}"
        if sample_rate is not None and str(sample_rate) not in MINIMAX_SAMPLE_RATES:
            return f"Unsupported MiniMax sample_rate: {sample_rate}"
        if bitrate is not None and str(bitrate) not in MINIMAX_BITRATES:
            return f"Unsupported MiniMax bitrate: {bitrate}"
        if channel is not None and str(channel) not in ("1", "2"):
            return "MiniMax channel must be 1 or 2"
        if speed is not None and not 0.5 <= float(speed) <= 2.0:
            return "MiniMax speed must be between 0.5 and 2.0"
        if volume is not None and not 0 < float(volume) <= 10.0:
            return "MiniMax volume must be greater than 0 and at most 10"
        if pitch is not None and not -12 <= int(pitch) <= 12:
            return "MiniMax pitch must be between -12 and 12"
        if strict and model == MINIMAX_MUSIC_MODEL:
            if (
                not bool(is_instrumental)
                and not str(lyrics or "").strip()
                and not bool(lyrics_optimizer)
            ):
                return "MiniMax Music requires lyrics, lyrics_optimizer, or instrumental mode"
        if strict and model in MINIMAX_SPEECH_MODELS and not str(voice_id or "").strip():
            return "MiniMax speech requires voice_id"
        if model == MINIMAX_VOICE_CLONE_MODEL:
            if strict and reference_audio is None:
                return "MiniMax Voice Clone requires reference_audio"
            if strict and not cls._valid_custom_voice_id(custom_voice_id):
                return (
                    "custom_voice_id must be 8-256 letters/digits/-/_, start "
                    "with a letter, and not end with -/_"
                )
            if clone_target_model not in (None, *MINIMAX_SPEECH_MODELS):
                return f"Unsupported clone target model: {clone_target_model}"
        return True

    @staticmethod
    def _build_payload(values: Dict[str, Any], audio_url: str = "") -> Dict[str, Any]:
        model = values["model"]
        metadata: Dict[str, Any]
        if model == MINIMAX_MUSIC_MODEL:
            instrumental = bool(values["is_instrumental"])
            metadata = {
                "is_instrumental": instrumental,
                "lyrics_optimizer": bool(values["lyrics_optimizer"]),
                "format": values["output_format"],
                "sample_rate": str(values["sample_rate"]),
                "bitrate": str(values["bitrate"]),
            }
            lyrics_text = str(values.get("lyrics") or "").strip()
            if not instrumental and lyrics_text:
                metadata["lyrics"] = lyrics_text
        elif model in MINIMAX_SPEECH_MODELS:
            metadata = {
                "voice_id": str(values["voice_id"]).strip(),
                "speed": float(values["speed"]),
                "vol": float(values["volume"]),
                "pitch": int(values["pitch"]),
                "language_boost": values["language_boost"],
                "format": values["output_format"],
                "sample_rate": str(values["sample_rate"]),
                "bitrate": str(values["bitrate"]),
                "channel": int(values["channel"]),
            }
        else:
            metadata = {
                "audio_url": audio_url,
                "custom_voice_id": str(values["custom_voice_id"]).strip(),
                "model": values["clone_target_model"],
                "need_noise_reduction": bool(values["need_noise_reduction"]),
                "need_volume_normalization": bool(values["need_volume_normalization"]),
            }
        return {
            "model": model,
            "prompt": str(values["prompt"]).strip(),
            "metadata": metadata,
        }

    @staticmethod
    def _result_text(final_response: Dict[str, Any], fallback: str = "") -> str:
        pending: List[Any] = [final_response]
        while pending:
            value = pending.pop(0)
            if isinstance(value, dict):
                for key in ("voice_id", "custom_voice_id", "result_text", "text"):
                    if value.get(key):
                        return str(value[key])
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        return fallback

    def generate(
        self,
        api_config: Any = None,
        reference_audio: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        model = str(kwargs.get("model") or MINIMAX_SPEECH_TURBO_MODEL)
        sample_rate = str(kwargs.get("sample_rate") or "32000")
        try:
            kwargs["reference_audio"] = reference_audio
            validation = self.VALIDATE_INPUTS(strict=True, **kwargs)
            if validation is not True:
                raise SeedanceLowPriceError(validation)
            config = resolve_config(api_config)
            progress = _progress_bar()
            reference_url = ""
            if model == MINIMAX_VOICE_CLONE_MODEL:
                reference_url = upload_media(
                    audio_to_wav_bytes(reference_audio),
                    "minimax_voice_clone_reference.wav",
                    "audio/wav",
                    config,
                )
            _update_progress(progress, 15)
            payload = self._build_payload(kwargs, reference_url)
            task_id, submitted = submit_audio_task(payload, config)
            _update_progress(progress, 20)
            final = poll_audio_task(
                task_id,
                config,
                on_progress=lambda value: _update_progress(
                    progress, 20 + value * 0.75
                ),
            )
            fallback_text = (
                str(kwargs.get("custom_voice_id") or "").strip()
                if model == MINIMAX_VOICE_CLONE_MODEL
                else ""
            )
            result_text = self._result_text(final, fallback_text)
            try:
                audio_url = extract_audio_url(final)
            except SeedanceLowPriceError:
                if model != MINIMAX_VOICE_CLONE_MODEL:
                    raise
                audio_url = ""
            if audio_url:
                audio = download_audio(
                    audio_url,
                    str(kwargs["output_format"]),
                    int(sample_rate),
                )
            else:
                audio = make_error_audio(int(sample_rate))
            _update_progress(progress, 100)
            return (
                audio,
                audio_url,
                result_text,
                task_id,
                _success_response(model, task_id, submitted, final),
            )
        except Exception as error:
            if not skip_error:
                raise
            response = json.dumps(
                {"status": "error", "model": model, "message": f"{type(error).__name__}: {error}"},
                ensure_ascii=False,
                indent=2,
            )
            return make_error_audio(int(sample_rate)), "", "", task_id, response


class Comfly_mureka_bgm_lowprice:
    COMFLY_CONCURRENT_DISABLED = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (MUREKA_BGM_MODELS, {"default": MUREKA_BGM_MODELS[0]}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "instrumental_id": ("STRING", {"default": ""}),
                "n": ("INT", {"default": 1, "min": 1, "max": 3, "step": 1}),
            },
            "optional": {
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = (AUDIO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audios", "audio_urls", "task_id", "response")
    OUTPUT_IS_LIST = (True, False, False, False)
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls, model=None, prompt=None, instrumental_id=None, n=None, strict=False, **kwargs
    ):
        if model not in (None, *MUREKA_BGM_MODELS):
            return f"Unsupported Mureka BGM model: {model}"
        if n is not None and not 1 <= int(n) <= 3:
            return "Mureka BGM n must be between 1 and 3"
        has_prompt = bool(str(prompt or "").strip())
        has_id = bool(str(instrumental_id or "").strip())
        if strict and has_prompt == has_id:
            return "Mureka BGM requires exactly one of prompt or instrumental_id"
        return True

    @staticmethod
    def _build_payload(
        model: str, prompt: str, instrumental_id: str, n: int
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "metadata": {"n": int(n), "stream": False},
        }
        prompt_text = str(prompt or "").strip()
        if prompt_text:
            payload["prompt"] = prompt_text
        else:
            payload["metadata"]["instrumental_id"] = str(instrumental_id).strip()
        return payload

    def generate(
        self,
        model: str,
        prompt: str,
        instrumental_id: str,
        n: int,
        api_config: Any = None,
        skip_error: bool = False,
    ):
        task_id = ""
        try:
            validation = self.VALIDATE_INPUTS(
                model=model,
                prompt=prompt,
                instrumental_id=instrumental_id,
                n=n,
                strict=True,
            )
            if validation is not True:
                raise SeedanceLowPriceError(validation)
            config = resolve_config(api_config)
            progress = _progress_bar()
            payload = self._build_payload(model, prompt, instrumental_id, n)
            task_id, submitted = submit_audio_task(payload, config)
            _update_progress(progress, 20)
            final = poll_audio_task(
                task_id,
                config,
                on_progress=lambda value: _update_progress(
                    progress, 20 + value * 0.75
                ),
            )
            audio_urls = extract_audio_urls(final)
            audios: List[Any] = []
            for index, audio_url in enumerate(audio_urls, start=1):
                audios.append(download_audio(audio_url, "mp3", 44100))
                _update_progress(progress, 95 + index / len(audio_urls) * 5)
            return (
                audios,
                json.dumps(audio_urls, ensure_ascii=False),
                task_id,
                _success_response(model, task_id, submitted, final),
            )
        except Exception as error:
            if not skip_error:
                raise
            response = json.dumps(
                {"status": "error", "model": model, "message": f"{type(error).__name__}: {error}"},
                ensure_ascii=False,
                indent=2,
            )
            return [make_error_audio(44100)], "[]", task_id, response


def _collect_flowmusic_clip_ids(value: Any) -> List[str]:
    clip_ids: List[str] = []
    seen = set()

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key == "clip_id" and isinstance(child, str) and child.strip():
                    normalized = child.strip()
                    if normalized not in seen:
                        seen.add(normalized)
                        clip_ids.append(normalized)
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return clip_ids


def _extract_flowmusic_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        simple = [
            item for item in value if isinstance(item, (str, int, float, bool))
        ]
        if simple and len(simple) == len(value):
            return json.dumps(simple, ensure_ascii=False)
        for item in value:
            text = _extract_flowmusic_text(item)
            if text:
                return text
        return ""
    if not isinstance(value, dict):
        return ""
    for key in (
        "text",
        "lyrics",
        "tags",
        "aligned_lyrics",
        "content",
        "message",
    ):
        if key in value:
            text = _extract_flowmusic_text(value.get(key))
            if text:
                return text
    for key, child in value.items():
        if key in {"id", "task_id", "clip_id", "status", "progress"}:
            continue
        text = _extract_flowmusic_text(child)
        if text:
            return text
    return ""


def extract_flowmusic_results(final_response: Dict[str, Any]) -> Dict[str, Any]:
    extracted = extract_suno_results(final_response)
    extracted["clip_ids"] = _collect_flowmusic_clip_ids(extracted["result"])
    extracted["text"] = _extract_flowmusic_text(extracted["result"])
    return extracted


class Comfly_flowmusic_lowprice:
    """All documented Flow Music actions through the domestic low-price API."""

    COMFLY_CONCURRENT_DISABLED = True
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = (
        AUDIO_TYPE,
        AUDIO_TYPE,
        VIDEO_TYPE,
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
    )
    RETURN_NAMES = (
        "audio1",
        "audio2",
        "video",
        "text",
        "clip_id",
        "primary_url",
        "result_urls",
        "primary_path",
        "result_paths",
        "task_id",
        "response",
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "operation": (
                    FLOWMUSIC_OPERATIONS,
                    {"default": "flowmusic-generation"},
                ),
                "version": (FLOWMUSIC_VERSIONS, {"default": "default"}),
                "sound_prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "音乐风格或声音描述。",
                    },
                ),
                "lyrics": (
                    "STRING",
                    {"multiline": True, "default": "", "tooltip": "音乐生成使用的歌词。"},
                ),
                "prompt": (
                    "STRING",
                    {"multiline": True, "default": "", "tooltip": "歌词生成提示词，最多 3000 字符。"},
                ),
                "title": ("STRING", {"default": ""}),
                "bpm": ("INT", {"default": 120, "min": 1, "step": 1}),
                "length": (
                    "INT",
                    {"default": 60, "min": 1, "max": 240, "step": 1},
                ),
                "clip_id": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "连接前一个 Flow Music 节点输出的 clip_id。",
                    },
                ),
                "extend_from_s": (
                    "FLOAT",
                    {"default": 0.0, "min": 0.0, "step": 0.1},
                ),
                "extend_s": (
                    "INT",
                    {"default": 30, "min": 1, "max": 164, "step": 1},
                ),
                "instruction": (
                    "STRING",
                    {"multiline": True, "default": ""},
                ),
                "start_s": (
                    "FLOAT",
                    {"default": 0.0, "min": 0.0, "step": 0.1},
                ),
                "end_s": (
                    "FLOAT",
                    {"default": 10.0, "min": 0.0, "step": 0.1},
                ),
                "strength": (
                    "FLOAT",
                    {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05},
                ),
                "format": (FLOWMUSIC_FORMATS, {"default": "mp3"}),
                "preset": (FLOWMUSIC_VIDEO_PRESETS, {"default": "modern"}),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "step": 1,
                        "control_after_generate": True,
                        "tooltip": "Flow Music 原生随机种子；fixed 可复用 ComfyUI 缓存。",
                    },
                ),
            },
            "optional": {
                "audio": (
                    AUDIO_TYPE,
                    {"tooltip": "flowmusic-upload-audio 使用的本地音频。"},
                ),
                "audio_url": (
                    "STRING",
                    {"default": "", "tooltip": "公网音频 URL，不能与本地音频同时使用。"},
                ),
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, operation=None, version=None, **kwargs):
        if operation not in FLOWMUSIC_ACTION_SPECS:
            return f"Unsupported Flow Music operation: {operation}"
        if version not in FLOWMUSIC_VERSIONS:
            return f"Unsupported Flow Music version: {version}"
        return True

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _update_progress(progress_bar: Any, value: float) -> None:
        _update_progress(progress_bar, value)

    def _resolve_audio_url(
        self,
        operation: str,
        audio: Any,
        audio_url: str,
        config: Dict[str, Any],
    ) -> str:
        if operation != "flowmusic-upload-audio":
            return ""
        url = self._text(audio_url)
        if audio is not None and url:
            raise SeedanceLowPriceError(
                "Flow Music audio and audio_url cannot both be used"
            )
        if audio is None and not url:
            raise SeedanceLowPriceError(
                "flowmusic-upload-audio requires local audio or audio_url"
            )
        if url:
            if not url.startswith(("http://", "https://")):
                raise SeedanceLowPriceError("audio_url must be an http(s) URL")
            return url
        return upload_media(
            audio_to_wav_bytes(audio),
            "flowmusic_upload.wav",
            "audio/wav",
            config,
        )

    def _build_payload(
        self,
        operation: str,
        uploaded_audio_url: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        if operation not in FLOWMUSIC_ACTION_SPECS:
            raise SeedanceLowPriceError(
                f"Unsupported Flow Music operation: {operation}"
            )
        spec = FLOWMUSIC_ACTION_SPECS[operation]
        allowed = set(spec["allowed_fields"])
        payload: Dict[str, Any] = {"model": FLOWMUSIC_MODEL}

        if "version" in allowed:
            version = self._text(kwargs.get("version")) or "default"
            if version not in FLOWMUSIC_VERSIONS:
                raise SeedanceLowPriceError(
                    f"Unsupported Flow Music version: {version}"
                )
            if version != "default":
                payload["version"] = version

        for field in (
            "sound_prompt",
            "lyrics",
            "prompt",
            "title",
            "clip_id",
            "instruction",
        ):
            if field in allowed:
                value = self._text(kwargs.get(field))
                if value:
                    payload[field] = value

        if operation == "flowmusic-generation":
            if not payload.get("sound_prompt") and not payload.get("lyrics"):
                raise SeedanceLowPriceError(
                    "Flow Music sound_prompt and lyrics cannot both be empty"
                )
            bpm = int(kwargs.get("bpm") or 0)
            length = int(kwargs.get("length") or 0)
            if bpm < 1:
                raise SeedanceLowPriceError("Flow Music bpm must be at least 1")
            if not 1 <= length <= 240:
                raise SeedanceLowPriceError(
                    "Flow Music length must be between 1 and 240"
                )
            payload.update(
                {"bpm": str(bpm), "length": length, "seed": int(kwargs.get("seed") or 0)}
            )

        if operation == "flowmusic-lyrics":
            prompt = payload.get("prompt", "")
            if not prompt:
                raise SeedanceLowPriceError("flowmusic-lyrics requires prompt")
            if len(prompt) > 3000:
                raise SeedanceLowPriceError(
                    "flowmusic-lyrics prompt must not exceed 3000 characters"
                )

        if operation == "flowmusic-upload-audio":
            if not uploaded_audio_url:
                raise SeedanceLowPriceError(
                    "flowmusic-upload-audio requires audio_url"
                )
            payload["audio_url"] = uploaded_audio_url

        if operation == "flowmusic-extend":
            extend_from_s = float(kwargs.get("extend_from_s") or 0.0)
            extend_s = int(kwargs.get("extend_s") or 0)
            if extend_from_s < 0:
                raise SeedanceLowPriceError(
                    "Flow Music extend_from_s must not be negative"
                )
            if not 1 <= extend_s <= 164:
                raise SeedanceLowPriceError(
                    "Flow Music extend_s must be between 1 and 164"
                )
            payload.update(
                {
                    "extend_from_s": extend_from_s,
                    "extend_s": extend_s,
                    "seed": int(kwargs.get("seed") or 0),
                }
            )

        if operation == "flowmusic-replace":
            start_s = float(kwargs.get("start_s") or 0.0)
            end_s = float(kwargs.get("end_s") or 0.0)
            if start_s < 0 or end_s <= start_s:
                raise SeedanceLowPriceError(
                    "Flow Music end_s must be greater than start_s"
                )
            payload.update(
                {
                    "start_s": start_s,
                    "end_s": end_s,
                    "seed": int(kwargs.get("seed") or 0),
                }
            )

        if operation == "flowmusic-cover":
            strength = float(kwargs.get("strength"))
            if not 0.0 <= strength <= 1.0:
                raise SeedanceLowPriceError(
                    "Flow Music strength must be between 0 and 1"
                )
            payload.update(
                {"strength": strength, "seed": int(kwargs.get("seed") or 0)}
            )

        if operation == "flowmusic-download-audio":
            output_format = self._text(kwargs.get("format"))
            if output_format not in FLOWMUSIC_FORMATS:
                raise SeedanceLowPriceError(
                    f"Unsupported Flow Music format: {output_format}"
                )
            payload["format"] = output_format

        if operation == "flowmusic-video-clip":
            preset = self._text(kwargs.get("preset"))
            if preset not in FLOWMUSIC_VIDEO_PRESETS:
                raise SeedanceLowPriceError(
                    f"Unsupported Flow Music preset: {preset}"
                )
            payload["preset"] = preset

        missing = [
            field
            for field in spec["required_fields"]
            if field not in payload or payload[field] in (None, "", [])
        ]
        if missing:
            raise SeedanceLowPriceError(
                f"{operation} requires: {', '.join(missing)}"
            )
        return {
            key: value
            for key, value in payload.items()
            if key == "model" or key in allowed
        }

    def _make_error_result(self, message: str) -> Dict[str, Any]:
        response = json.dumps({"error": message}, ensure_ascii=False, indent=2)
        silence = make_silent_audio()
        return {
            "ui": {"text": ["", "", "", "", response]},
            "result": (
                silence,
                silence,
                make_error_video(message),
                "",
                "",
                "",
                "[]",
                "",
                "[]",
                "",
                response,
            ),
        }

    def execute(
        self,
        operation: str,
        version: str,
        sound_prompt: str,
        lyrics: str,
        prompt: str,
        title: str,
        bpm: int,
        length: int,
        clip_id: str,
        extend_from_s: float,
        extend_s: int,
        instruction: str,
        start_s: float,
        end_s: float,
        strength: float,
        format: str,
        preset: str,
        seed: int,
        audio: Any = None,
        audio_url: str = "",
        api_config: Any = None,
        skip_error: bool = False,
    ):
        values = {
            "version": version,
            "sound_prompt": sound_prompt,
            "lyrics": lyrics,
            "prompt": prompt,
            "title": title,
            "bpm": bpm,
            "length": length,
            "clip_id": clip_id,
            "extend_from_s": extend_from_s,
            "extend_s": extend_s,
            "instruction": instruction,
            "start_s": start_s,
            "end_s": end_s,
            "strength": strength,
            "format": format,
            "preset": preset,
            "seed": seed,
        }
        try:
            return self._execute_inner(
                operation,
                audio,
                audio_url,
                api_config,
                values,
            )
        except Exception as error:
            if not skip_error:
                raise
            return self._make_error_result(
                f"Flow Music Low Price: {type(error).__name__}: {error}"
            )

    def _execute_inner(
        self,
        operation: str,
        audio: Any,
        audio_url: str,
        api_config: Any,
        values: Dict[str, Any],
    ):
        validation = self.VALIDATE_INPUTS(
            operation=operation,
            version=values.get("version"),
        )
        if validation is not True:
            raise SeedanceLowPriceError(validation)
        config = resolve_config(api_config)
        progress = _progress_bar()
        uploaded_audio_url = self._resolve_audio_url(
            operation, audio, audio_url, config
        )
        self._update_progress(progress, 15)
        payload = self._build_payload(operation, uploaded_audio_url, **values)
        spec = FLOWMUSIC_ACTION_SPECS[operation]
        task_id, submit_response = submit_suno_action(
            spec["action"], payload, config
        )
        if not task_id:
            raise SeedanceLowPriceError(
                f"{operation} returned no task id in its asynchronous response"
            )
        self._update_progress(progress, 20)
        final_response = poll_suno_task(
            task_id,
            config,
            on_progress=lambda value: self._update_progress(
                progress, 20 + value * 0.65
            ),
        )
        self._update_progress(progress, 85)

        extracted = extract_flowmusic_results(final_response)
        artifacts = extracted["artifacts"]
        result_paths: List[str] = []
        audio_objects: List[Dict[str, Any]] = []
        video: Any = None
        warnings: List[Dict[str, Any]] = []
        successful_downloads = 0
        artifact_count = max(1, len(artifacts))
        for index, artifact in enumerate(artifacts, start=1):
            url = artifact["url"]
            kind = artifact["kind"]
            if kind == "file" and spec["result_family"] in {"audio", "video"}:
                kind = spec["result_family"]
            path = ""
            try:
                if kind == "audio":
                    audio_object, path = download_suno_audio(url)
                    audio_objects.append(audio_object)
                elif kind == "video" and video is None:
                    video, path = download_suno_video(url)
                else:
                    path = download_suno_file(
                        url,
                        "flowmusic_stems" if operation == "flowmusic-stems" else "flowmusic_file",
                        "zip" if operation == "flowmusic-stems" else "bin",
                    )
                successful_downloads += 1
            except Exception as error:
                warnings.append(
                    {
                        "artifact_index": index,
                        "kind": kind,
                        "error": type(error).__name__,
                    }
                )
                print(
                    f"[Flow Music Low Price] Artifact {index}/{artifact_count} "
                    f"({kind}) download failed: {type(error).__name__}"
                )
            result_paths.append(path)
            self._update_progress(
                progress, 85 + min(10, index / artifact_count * 10)
            )

        if artifacts and successful_downloads == 0:
            raise SeedanceLowPriceError(
                "All Flow Music result artifacts failed to download"
            )

        all_urls = [artifact["url"] for artifact in artifacts]
        text = extracted["text"]
        if not text and spec["result_family"] == "text":
            text = json.dumps(extracted["result"], ensure_ascii=False, indent=2)
        clip_ids = extracted["clip_ids"]
        result_clip_id = clip_ids[0] if clip_ids else ""
        response_payload: Dict[str, Any] = final_response
        if warnings:
            response_payload = dict(final_response)
            response_payload["_zhenzhen_local"] = {
                "download_warnings": warnings
            }
        response = json.dumps(response_payload, ensure_ascii=False, indent=2)
        primary_url = all_urls[0] if all_urls else ""
        primary_path = result_paths[0] if result_paths else ""
        self._update_progress(progress, 100)
        return {
            "ui": {
                "text": [text, result_clip_id, primary_url, primary_path, response]
            },
            "result": (
                audio_objects[0] if audio_objects else None,
                audio_objects[1] if len(audio_objects) > 1 else None,
                video,
                text,
                result_clip_id,
                primary_url,
                json.dumps(all_urls, ensure_ascii=False),
                primary_path,
                json.dumps(result_paths, ensure_ascii=False),
                task_id,
                response,
            ),
        }


__all__ = [
    "Comfly_zhenzhen_image_gk_v2_lowprice",
    "Comfly_zhenzhen_image_gk_v2_edit_lowprice",
    "Comfly_wan_2_7_global_image_lowprice",
    "Comfly_qwen3_tts_lowprice",
    "Comfly_minimax_audio_lowprice",
    "Comfly_mureka_bgm_lowprice",
    "Comfly_flowmusic_lowprice",
]
