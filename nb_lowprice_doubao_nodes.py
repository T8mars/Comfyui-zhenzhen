"""Independent NB Lowprice and Doubao voice training/synthesis nodes."""

from __future__ import annotations

import json
import os
from urllib.parse import urlparse

try:
    from . import seedance_low_price_nodes as api
    from .execution_seed import EXECUTION_SEED_SPEC
except ImportError:
    import seedance_low_price_nodes as api
    from execution_seed import EXECUTION_SEED_SPEC


NB_MODELS = ["zhenzhen-image-nb-pro-lowprice", "zhenzhen-image-nb-2.1-lowprice"]
NB_RESOLUTIONS = ["1k", "2k", "4k"]
NB_STANDARD_SIZES = ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
NB_SIZES = [*NB_STANDARD_SIZES, "1:4", "4:1", "1:8", "8:1"]
VOICE_MODELS = ["doubao-voice-clone", "doubao-seed-icl-2.0"]
CLONE_LANGUAGES = ["api_default", *[str(i) for i in range(18)], "19", "20", "21"]
VOICE_VARIANTS = ["api_default", "seed-tts-2.0-standard", "seed-tts-2.0-expressive"]
AUDIO_FORMATS = ["mp3", "wav", "pcm", "ogg_opus"]
SAMPLE_RATES = ["8000", "16000", "22050", "24000", "32000", "44100", "48000"]
ICL_LANGUAGES = ["api_default", "zh-cn", "en", "ja", "es-mx", "id", "pt-br", "pt", "ko", "de", "fr", "th", "vi", "ru", "fil", "ms", "ar"]
OPTIONAL_BOOLEAN = ["api_default", "enabled", "disabled"]
CLONE_BOOLEANS = ["enable_audio_denoise", "disable_volume_normalization"]
ICL_BOOLEANS = ["enable_subtitle", "disable_markdown_filter", "disable_emoji_filter", "enable_latex_tn",
                "aigc_watermark", "disable_default_bit_rate", "tone_fidelity", "aigc_metadata_enable"]
ICL_STRINGS = ["section_id", "aigc_metadata_content_producer", "aigc_metadata_produce_id",
               "aigc_metadata_content_propagator", "aigc_metadata_propagate_id"]


def progress_bar():
    return api.comfy.utils.ProgressBar(100) if api.COMFYUI_AVAILABLE else None


def update(bar, value):
    if bar is not None:
        bar.update_absolute(int(value), 100)


def response_json(model, task_id, submitted, result):
    return json.dumps({"status": "SUCCESS", "model": model, "task_id": task_id,
                       "submit": submitted, "result": result}, ensure_ascii=False, indent=2)


class T8ZhenzhenNBLowPrice:
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": (NB_MODELS, {"default": NB_MODELS[0]}),
            "prompt": ("STRING", {"multiline": True, "default": "", "tooltip": "1-5000 characters."}),
            "resolution": (NB_RESOLUTIONS, {"default": "1k"}),
            "size": (NB_SIZES, {"default": "1:1"}),
        }, "optional": {
            **{f"image{i}": ("IMAGE", {"tooltip": f"Reference {i}/14; exactly one image per slot."}) for i in range(1, 15)},
            "api_config": (api.CONFIG_TYPE,),
            "skip_error": ("BOOLEAN", {"default": False}),
            "seed": EXECUTION_SEED_SPEC,
        }}

    @classmethod
    def VALIDATE_INPUTS(cls, model=None, prompt=None, resolution=None, size=None, strict=False, **values):
        if model not in (None, *NB_MODELS):
            return "Unsupported NB Lowprice model"
        if strict and not 1 <= len(str(prompt or "").strip()) <= 5000:
            return "NB Lowprice prompt must contain 1-5000 characters"
        if resolution not in (None, *NB_RESOLUTIONS):
            return "NB Lowprice resolution must be 1k, 2k or 4k"
        sizes = NB_STANDARD_SIZES if model == NB_MODELS[0] else NB_SIZES
        if size not in (None, *sizes):
            return "This NB model does not support the selected size"
        if strict:
            if any(value is not None and name.startswith("image") and name[5:].isdecimal() and int(name[5:]) > 14
                   for name, value in values.items()):
                return "NB Lowprice accepts at most 14 reference images"
            for i in range(1, 15):
                image = values.get(f"image{i}")
                if image is not None:
                    shape = getattr(image, "shape", ())
                    if len(shape) != 4 or int(shape[0]) != 1 or shape[-1] not in (3, 4):
                        return "Each NB reference slot requires exactly one IMAGE"
        return True

    @classmethod
    def build_payload(cls, values, images):
        validation = cls.VALIDATE_INPUTS(**values, strict=True)
        if validation is not True:
            raise api.SeedanceLowPriceError(validation)
        if len(images) > 14:
            raise api.SeedanceLowPriceError("NB Lowprice accepts at most 14 reference images")
        payload = {"model": values["model"], "prompt": str(values["prompt"]).strip(), "n": 1,
                   "size": values["size"], "metadata": {"resolution": values["resolution"]}}
        if images:
            payload["images"] = list(images)
        return payload

    def generate(self, model=NB_MODELS[0], prompt="", resolution="1k", size="1:1",
                 api_config=None, skip_error=False, seed=0, **references):
        del seed
        values = dict(model=model, prompt=prompt, resolution=resolution, size=size, **references)
        try:
            validation = self.VALIDATE_INPUTS(**values, strict=True)
            if validation is not True:
                raise api.SeedanceLowPriceError(validation)
            config = api.resolve_config(api_config)
            bar = progress_bar()
            images = [(i, references[f"image{i}"]) for i in range(1, 15) if references.get(f"image{i}") is not None]
            urls = []
            for i, image in images:
                urls.append(api.upload_media(api.image_to_png_bytes(image), f"nb_lowprice_reference_{i}.png", "image/png", config))
                update(bar, len(urls) / len(images) * 20)
            task_id, submitted = api.submit_image_task(self.build_payload(values, urls), config)
            update(bar, 25)
            result = api.poll_image_task(task_id, config, on_progress=lambda value: update(bar, 25 + value * .7))
            url = api.extract_image_url(result)
            update(bar, 95)
            image = api.download_image(url)
            update(bar, 100)
            return image, url, task_id, response_json(model, task_id, submitted, result)
        except Exception as error:
            if not skip_error:
                raise
            return api.torch.ones((1, 512, 512, 3)), "", "", json.dumps({"status": "error", "message": str(error)})


def download_voice_audio(url, output_format, sample_rate):
    path = api.download_suno_file(url, "doubao_voice", output_format or "wav")
    try:
        with open(path, "rb") as handle:
            data = handle.read()
        if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
            output_format = "wav"
        if output_format == "pcm":
            if not data or len(data) % 2:
                raise api.SeedanceLowPriceError("Invalid PCM audio result")
            samples = api.np.frombuffer(data, dtype="<i2").astype(api.np.float32) / 32768.0
            audio = {"waveform": api.torch.from_numpy(samples.copy()).reshape(1, 1, -1), "sample_rate": int(sample_rate)}
        else:
            audio = api.audio_bytes_to_comfy(data, output_format, int(sample_rate))
        waveform = audio["waveform"]
        if waveform.ndim != 3 or waveform.shape[-1] < 1 or not api.torch.isfinite(waveform).all():
            raise api.SeedanceLowPriceError("Invalid decoded voice audio")
        return audio, path
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise


class T8ZhenzhenDoubaoVoiceCloneICL:
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    RETURN_TYPES = ("AUDIO", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio", "audio_url", "audio_path", "speaker", "task_id", "response")
    OUTPUT_IS_LIST = (True, True, True, False, False, False)
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": (VOICE_MODELS, {"default": VOICE_MODELS[0]}),
            "prompt": ("STRING", {"multiline": True, "default": "", "tooltip": "Clone preview: 4-300; synthesis: 1-10000 characters."}),
            "speaker": ("STRING", {"default": "", "tooltip": "Connect the training speaker output; same account required."}),
            "audio_url": ("STRING", {"default": "", "tooltip": "Public voice sample URL, <=10 MB; OR local AUDIO. PCM requires 24 kHz mono."}),
            "custom_speaker_id": ("STRING", {"default": "", "tooltip": "Optional 8-256 characters, English initial. Blank lets the API assign an ID."}),
            "language": (CLONE_LANGUAGES, {"default": "api_default", "tooltip": "Match the sample language: 0 Chinese, 1 English; api_default omits this code."}),
            "reference_text": ("STRING", {"multiline": True, "default": "", "tooltip": "Matching recording transcript, at most 2000 characters."}),
            **{name: (OPTIONAL_BOOLEAN, {"default": "api_default"}) for name in CLONE_BOOLEANS},
            "voice_model": (VOICE_VARIANTS, {"default": "seed-tts-2.0-standard"}),
            "output_format": (AUDIO_FORMATS, {"default": "mp3"}),
            "sample_rate": (SAMPLE_RATES, {"default": "24000"}),
            **{name: ("FLOAT", {"default": 0.0, "min": low, "max": high, "step": 1})
               for name, low, high in [("speech_rate", -50, 100), ("loudness_rate", -50, 100), ("pitch", -12, 12)]},
            "explicit_language": (ICL_LANGUAGES, {"default": "api_default"}),
            "context_texts": ("STRING", {"multiline": True, "default": "", "tooltip": "At most 500 characters; only with voice_model=api_default."}),
            "advanced_mode": ("BOOLEAN", {"default": False}),
            "training_speaker_id": ("STRING", {"default": "", "tooltip": "Provider training ID, separate from custom_speaker_id."}),
            "bit_rate": ("INT", {"default": 0, "min": 0, "max": 160000, "step": 1000, "tooltip": "0 omits; explicit range 16000-160000."}),
            "max_length_to_filter_parenthesis": (["api_default", "0", "100"], {"default": "api_default"}),
            "silence_duration": ("INT", {"default": 0, "min": 0, "max": 30000, "step": 100}),
            **{name: (OPTIONAL_BOOLEAN, {"default": "api_default"}) for name in ICL_BOOLEANS},
            "latex_parser": (["api_default", "v2"], {"default": "api_default"}),
            **{name: ("STRING", {"default": ""}) for name in ICL_STRINGS},
        }, "optional": {
            "reference_audio": ("AUDIO", {"tooltip": "Exactly one recording; encoded WAV <=10 MB."}),
            "api_config": (api.CONFIG_TYPE,),
            "skip_error": ("BOOLEAN", {"default": False}),
            "seed": EXECUTION_SEED_SPEC,
        }}

    @classmethod
    def VALIDATE_INPUTS(cls, model=None, prompt=None, strict=False, **values):
        if model not in (None, *VOICE_MODELS):
            return "Unsupported Doubao voice model"
        if not strict:
            return True
        clone = model == VOICE_MODELS[0]
        low, high = (4, 300) if clone else (1, 10000)
        if not low <= len(str(prompt or "").strip()) <= high:
            return f"Doubao prompt must contain {low}-{high} characters"
        if clone:
            audio, url = values.get("reference_audio"), str(values.get("audio_url") or "").strip()
            if (audio is not None) == bool(url):
                return "Provide exactly one reference_audio OR audio_url"
            if url and (urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc):
                return "audio_url must be a public HTTP(S) URL"
            if audio is not None:
                waveform = audio.get("waveform") if isinstance(audio, dict) else None
                rate = audio.get("sample_rate") if isinstance(audio, dict) else None
                if (not isinstance(waveform, api.torch.Tensor) or waveform.ndim != 3 or waveform.shape[0] != 1
                        or min(waveform.shape[1:]) < 1 or not api.torch.isfinite(waveform).all()
                        or type(rate) is not int or rate <= 0):
                    return "reference_audio requires one valid AUDIO waveform"
            custom_id = str(values.get("custom_speaker_id") or "").strip()
            if custom_id and (not 8 <= len(custom_id) <= 256 or custom_id[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"):
                return "custom_speaker_id requires 8-256 characters and an English initial"
            if len(str(values.get("reference_text") or "").strip()) > 2000:
                return "reference_text exceeds 2000 characters"
            if values.get("language", "api_default") not in CLONE_LANGUAGES:
                return "Unsupported training language code"
            booleans = CLONE_BOOLEANS
        else:
            if not str(values.get("speaker") or "").strip():
                return "speaker is required; connect the training speaker output"
            defaults = {"voice_model": "seed-tts-2.0-standard", "output_format": "mp3", "sample_rate": "24000"}
            enums = {"voice_model": VOICE_VARIANTS, "output_format": AUDIO_FORMATS, "sample_rate": SAMPLE_RATES,
                     "explicit_language": ICL_LANGUAGES, "max_length_to_filter_parenthesis": ["api_default", "0", "100"],
                     "latex_parser": ["api_default", "v2"]}
            for name, choices in enums.items():
                if str(values.get(name, defaults.get(name, "api_default"))) not in choices:
                    return f"Unsupported Doubao {name}"
            for name, lower, upper in [("speech_rate", -50, 100), ("loudness_rate", -50, 100), ("pitch", -12, 12), ("silence_duration", 0, 30000)]:
                value = values.get(name, 0)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not lower <= value <= upper:
                    return f"{name} must be between {lower} and {upper}"
            bit_rate = values.get("bit_rate", 0)
            if type(bit_rate) is not int or (bit_rate != 0 and not 16000 <= bit_rate <= 160000):
                return "bit_rate must be 0 (omit) or 16000-160000"
            if values.get("voice_model", "seed-tts-2.0-standard") == "api_default" and len(str(values.get("context_texts") or "").strip()) > 500:
                return "context_texts exceeds 500 characters"
            for name in ICL_STRINGS:
                if len(str(values.get(name) or "").strip()) > 128:
                    return f"{name} exceeds 128 characters"
            if values.get("latex_parser") == "v2" and values.get("disable_markdown_filter") == "enabled":
                return "latex_parser v2 requires Markdown filtering"
            booleans = ICL_BOOLEANS
        for name in booleans:
            if values.get(name, "api_default") not in OPTIONAL_BOOLEAN:
                return f"{name} must be api_default, enabled or disabled"
        return True

    @classmethod
    def build_payload(cls, values, uploaded_audio_url=""):
        validation = cls.VALIDATE_INPUTS(**values, strict=True)
        if validation is not True:
            raise api.SeedanceLowPriceError(validation)
        if values["model"] == VOICE_MODELS[0]:
            metadata = {"audio_url": uploaded_audio_url or str(values.get("audio_url") or "").strip()}
            if not metadata["audio_url"]:
                raise api.SeedanceLowPriceError("Voice sample has not been uploaded")
            for name in ("custom_speaker_id", "reference_text"):
                if str(values.get(name) or "").strip():
                    metadata[name] = str(values[name]).strip()
            if str(values.get("training_speaker_id") or "").strip():
                metadata["speaker_id"] = str(values["training_speaker_id"]).strip()
            if values.get("language", "api_default") != "api_default":
                metadata["language"] = str(values["language"])
            booleans = CLONE_BOOLEANS
        else:
            metadata = {"speaker": str(values["speaker"]).strip(), "format": values.get("output_format", "mp3"),
                        "sample_rate": str(values.get("sample_rate", "24000")),
                        **{name: values.get(name, 0) for name in ("speech_rate", "loudness_rate", "pitch", "silence_duration")}}
            variant = values.get("voice_model", "seed-tts-2.0-standard")
            if variant != "api_default":
                metadata["voice_model"] = variant
            elif str(values.get("context_texts") or "").strip():
                metadata["context_texts"] = str(values["context_texts"]).strip()
            if values.get("explicit_language", "api_default") != "api_default":
                metadata["explicit_language"] = values["explicit_language"]
            if values.get("bit_rate", 0):
                metadata["bit_rate"] = values["bit_rate"]
            if values.get("max_length_to_filter_parenthesis", "api_default") != "api_default":
                metadata["max_length_to_filter_parenthesis"] = int(values["max_length_to_filter_parenthesis"])
            for name in ICL_STRINGS:
                if str(values.get(name) or "").strip():
                    metadata[name] = str(values[name]).strip()
            booleans = ICL_BOOLEANS
        for name in booleans:
            if values.get(name, "api_default") != "api_default":
                metadata[name] = values[name] == "enabled"
        if values["model"] == VOICE_MODELS[1] and values.get("latex_parser") == "v2":
            metadata.update(latex_parser="v2", disable_markdown_filter=False)
        return {"model": values["model"], "prompt": str(values["prompt"]).strip(), "metadata": metadata}

    def generate(self, model=VOICE_MODELS[0], prompt="", api_config=None, skip_error=False, seed=0, **values):
        del seed
        values = dict(values, model=model, prompt=prompt)
        paths = []
        try:
            validation = self.VALIDATE_INPUTS(**values, strict=True)
            if validation is not True:
                raise api.SeedanceLowPriceError(validation)
            clone = model == VOICE_MODELS[0]
            sample = None
            if clone and values.get("reference_audio") is not None:
                sample = api.audio_to_wav_bytes(values["reference_audio"])
                if len(sample) > 10 * 1024 * 1024:
                    raise api.SeedanceLowPriceError("Encoded voice sample exceeds 10 MB")
            config = api.resolve_config(api_config)
            bar = progress_bar()
            uploaded = api.upload_media(sample, "doubao_voice_reference.wav", "audio/wav", config) if sample is not None else ""
            update(bar, 15)
            task_id, submitted = api.submit_audio_task(self.build_payload(values, uploaded), config)
            update(bar, 20)
            result = api.poll_audio_task(task_id, config, on_progress=lambda value: update(bar, 20 + value * .7))
            record = result.get("data", {})
            speaker = str(record.get("result_text") or "").strip() if clone else str(values["speaker"]).strip()
            if not speaker:
                raise api.SeedanceLowPriceError("Voice training completed without a speaker ID")
            urls = api.extract_audio_urls(result)
            audios = []
            for index, url in enumerate(urls):
                audio, path = download_voice_audio(url, "" if clone else values.get("output_format", "mp3"),
                                                   24000 if clone else int(values.get("sample_rate", "24000")))
                audios.append(audio)
                paths.append(path)
                update(bar, 90 + 10 * (index + 1) / len(urls))
            return audios, urls, paths, speaker, task_id, response_json(model, task_id, submitted, result)
        except Exception as error:
            for path in paths:
                try:
                    os.remove(path)
                except OSError:
                    pass
            if not skip_error:
                raise
            return [api.make_error_audio(24000)], [""], [""], "", "", json.dumps({"status": "error", "message": str(error)})
