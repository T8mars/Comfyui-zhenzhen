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
        audio_to_wav_bytes,
        download_audio,
        download_image,
        extract_audio_url,
        extract_audio_urls,
        extract_image_url,
        image_to_png_bytes,
        make_error_audio,
        poll_audio_task,
        poll_image_task,
        resolve_config,
        submit_audio_task,
        submit_image_task,
        upload_media,
    )
except ImportError:
    from seedance_low_price_nodes import (
        AUDIO_TYPE,
        COMFYUI_AVAILABLE,
        CONFIG_TYPE,
        SeedanceLowPriceError,
        audio_to_wav_bytes,
        download_audio,
        download_image,
        extract_audio_url,
        extract_audio_urls,
        extract_image_url,
        image_to_png_bytes,
        make_error_audio,
        poll_audio_task,
        poll_image_task,
        resolve_config,
        submit_audio_task,
        submit_image_task,
        upload_media,
    )

if COMFYUI_AVAILABLE:
    import comfy.utils


ZHENZHEN_IMAGE_GK_V2_MODEL = "zhenzhen-image-gk-v2"
ZHENZHEN_IMAGE_GK_V2_SIZES = ["1:1", "16:9", "9:16", "3:2", "2:3"]
ZHENZHEN_IMAGE_GK_V2_PROMPT_MAX_LENGTH = 20000

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
                "n": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
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
        if n is not None and not 1 <= int(n) <= 10:
            return "Zhenzhen Image GK v2 n must be between 1 and 10"
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


__all__ = [
    "Comfly_zhenzhen_image_gk_v2_lowprice",
    "Comfly_wan_2_7_global_image_lowprice",
    "Comfly_qwen3_tts_lowprice",
    "Comfly_minimax_audio_lowprice",
    "Comfly_mureka_bgm_lowprice",
]
