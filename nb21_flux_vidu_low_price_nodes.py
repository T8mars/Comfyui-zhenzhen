"""NB 2.1, FLUX 3 Image, and Vidu Q4 nodes for the low-price channel."""

from __future__ import annotations

import json
import os
import subprocess
from urllib.parse import urlparse

try:
    from . import seedance_low_price_nodes as api
except ImportError:
    import seedance_low_price_nodes as api


NB21_MODEL = "zhenzhen-image-nb-2.1"
NB21_RESOLUTIONS = ["1K", "2K", "4K"]
NB21_RATIOS = ["auto", "1:1", "16:9", "9:16", "21:9", "2:3", "3:2",
               "3:4", "4:3", "4:5", "5:4"]
FLUX_MODEL = "flux-3-image"
FLUX_RESOLUTIONS = ["768sq", "1k", "1.5k", "2k", "4k"]
FLUX_RATIOS = ["auto", "1:1", "16:9", "9:16", "21:9", "9:21", "1:2", "2:1",
               "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "5:7", "7:5"]
VIDU_MODELS = ["vidu-q4-preview-i2v", "vidu-q4-preview-r2v",
               "vidu-q4-preview-global-i2v", "vidu-q4-preview-global-r2v"]
VIDU_SECONDS = [str(i) for i in range(3, 17)]
VIDU_RESOLUTIONS = ["540p", "720p", "1080p", "2k", "4k"]
VIDU_RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4"]
VIDU_I2V_DEFAULT_PROMPT = "Animate the reference image with natural subtle motion."
SEED_INPUT = ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF,
                      "control_after_generate": True,
                      "tooltip": "ComfyUI cache seed only; not sent to the API."})


def _single_image(image, name):
    shape = getattr(image, "shape", ())
    if len(shape) != 4 or int(shape[0]) != 1:
        raise api.SeedanceLowPriceError(f"{name} requires exactly one IMAGE")


def _progress(bar, value):
    if bar is not None:
        bar.update_absolute(value, 100)


def _response(model, task_id, submit, result):
    return json.dumps({"status": "SUCCESS", "model": model, "task_id": task_id,
                       "submit": submit, "result": result}, ensure_ascii=False, indent=2)


def audio_to_mp3_bytes(audio):
    ffmpeg = api._find_suno_ffmpeg()
    if not ffmpeg:
        raise api.SeedanceLowPriceError("Vidu Q4 local audio requires FFmpeg")
    completed = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
         "-acodec", "libmp3lame", "-f", "mp3", "pipe:1"],
        input=api.audio_to_wav_bytes(audio), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False, timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    if completed.returncode != 0 or not completed.stdout:
        raise api.SeedanceLowPriceError("Vidu Q4 MP3 encoding failed")
    return completed.stdout


class _ImageNode:
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        required = {
            "prompt": ("STRING", {"multiline": True, "default": ""}),
            "resolution": (cls.RESOLUTIONS, {"default": cls.DEFAULT_RESOLUTION}),
            "aspect_ratio": (cls.RATIOS, {"default": "auto"}),
        }
        if cls.MODEL == FLUX_MODEL:
            required.update({
                "grounding": ("BOOLEAN", {"default": True}),
                "safety_tolerance": ("INT", {"default": 2, "min": 0, "max": 4}),
            })
        optional = {"api_config": (api.CONFIG_TYPE,)}
        optional.update({f"image{i}": ("IMAGE",) for i in range(1, cls.MAX_IMAGES + 1)})
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        optional["seed"] = SEED_INPUT
        return {"required": required, "optional": optional}

    @classmethod
    def VALIDATE_INPUTS(cls, prompt=None, resolution=None, aspect_ratio=None,
                        safety_tolerance=2, strict=False, **kwargs):
        if strict and not str(prompt or "").strip():
            return "prompt is required"
        if resolution not in (None, *cls.RESOLUTIONS):
            return "Unsupported resolution"
        if aspect_ratio not in (None, *cls.RATIOS):
            return "Unsupported aspect_ratio"
        if cls.MODEL == FLUX_MODEL and safety_tolerance is not None:
            if type(safety_tolerance) is not int or not 0 <= safety_tolerance <= 4:
                return "safety_tolerance must be an integer from 0 to 4"
        for i in range(1, cls.MAX_IMAGES + 1):
            if kwargs.get(f"image{i}") is not None:
                try:
                    _single_image(kwargs[f"image{i}"], f"image{i}")
                except api.SeedanceLowPriceError as exc:
                    return str(exc)
        return True

    def build_payload(self, prompt, resolution, aspect_ratio, images,
                      grounding=True, safety_tolerance=2):
        validation = self.VALIDATE_INPUTS(prompt, resolution, aspect_ratio,
                                          safety_tolerance, strict=True)
        if validation is not True:
            raise api.SeedanceLowPriceError(validation)
        if len(images) > self.MAX_IMAGES:
            raise api.SeedanceLowPriceError(f"At most {self.MAX_IMAGES} images are allowed")
        payload = {"model": self.MODEL, "prompt": str(prompt).strip(), "n": 1}
        if self.MODEL == NB21_MODEL:
            payload["size"] = aspect_ratio
            payload["metadata"] = {"resolution": resolution}
        else:
            payload.update(resolution=resolution, aspect_ratio=aspect_ratio, grounding=bool(grounding),
                           safety_tolerance=safety_tolerance)
        if images:
            payload["images"] = list(images)
        return payload

    def generate(self, prompt, resolution, aspect_ratio, api_config=None,
                 skip_error=False, seed=0, grounding=True, safety_tolerance=2, **kwargs):
        del seed
        task_id = ""
        bar = api.comfy.utils.ProgressBar(100) if api.COMFYUI_AVAILABLE else None
        try:
            validation = self.VALIDATE_INPUTS(
                prompt, resolution, aspect_ratio, safety_tolerance, strict=True, **kwargs,
            )
            if validation is not True:
                raise api.SeedanceLowPriceError(validation)
            config = api.resolve_config(api_config)
            references = [(i, kwargs[f"image{i}"]) for i in range(1, self.MAX_IMAGES + 1)
                          if kwargs.get(f"image{i}") is not None]
            urls = []
            for index, image in references:
                urls.append(api.upload_media(api.image_to_png_bytes(image),
                                             f"reference_{index}.png", "image/png", config))
                _progress(bar, int(len(urls) / len(references) * 20))
            payload = self.build_payload(prompt, resolution, aspect_ratio, urls,
                                         grounding, safety_tolerance)
            task_id, submit = api.submit_image_task(payload, config)
            _progress(bar, 25)
            result = api.poll_image_task(
                task_id, config,
                on_progress=lambda value: _progress(bar, 25 + int(value * .7)),
            )
            url = api.extract_image_url(result)
            image = api.download_image(url)
            _progress(bar, 100)
            return (image, url, task_id, _response(self.MODEL, task_id, submit, result))
        except Exception as exc:
            if not skip_error:
                raise
            return (api.torch.ones((1, 512, 512, 3)), "", "",
                    json.dumps({"status": "error", "model": self.MODEL,
                                "message": f"{type(exc).__name__}: {exc}"}))


class T8ZhenzhenNB21LowPrice(_ImageNode):
    MODEL = NB21_MODEL
    RESOLUTIONS = NB21_RESOLUTIONS
    RATIOS = NB21_RATIOS
    DEFAULT_RESOLUTION = "1K"
    MAX_IMAGES = 14


class T8ZhenzhenFlux3ImageLowPrice(_ImageNode):
    MODEL = FLUX_MODEL
    RESOLUTIONS = FLUX_RESOLUTIONS
    RATIOS = FLUX_RATIOS
    DEFAULT_RESOLUTION = "1k"
    MAX_IMAGES = 10


class T8ZhenzhenViduQ4PreviewLowPrice:
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    RETURN_TYPES = (api.VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        optional = {"api_config": (api.CONFIG_TYPE,)}
        optional.update({f"image{i}": ("IMAGE",) for i in range(1, 16)})
        optional.update({f"audio{i}": ("AUDIO",) for i in range(1, 4)})
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        optional["seed"] = SEED_INPUT
        return {"required": {
            "model": (VIDU_MODELS, {"default": VIDU_MODELS[0]}),
            "prompt": ("STRING", {"multiline": True, "default": "",
                                   "tooltip": "R2V requires a prompt; empty I2V uses natural subtle motion."}),
            "seconds": (VIDU_SECONDS, {"default": "5"}),
            "resolution": (VIDU_RESOLUTIONS, {"default": "720p"}),
            "ratio": (VIDU_RATIOS, {"default": "16:9"}),
            "generate_audio": ("BOOLEAN", {"default": True}),
            "is_rec": ("BOOLEAN", {"default": True}),
            "watermark": ("BOOLEAN", {"default": False}),
            **{f"audio_url{i}": ("STRING", {"default": "",
                                           "tooltip": "Public MP3 URL or local AUDIO, not both."})
               for i in range(1, 4)},
        }, "optional": optional}

    @classmethod
    def VALIDATE_INPUTS(cls, model=None, prompt=None, seconds=None, resolution=None,
                        ratio=None, strict=False, **kwargs):
        if model not in (None, *VIDU_MODELS):
            return "Unsupported Vidu Q4 model"
        if seconds is not None and str(seconds) not in VIDU_SECONDS:
            return "Vidu Q4 seconds must be 3-16"
        if resolution not in (None, *VIDU_RESOLUTIONS):
            return "Unsupported Vidu Q4 resolution"
        reference = str(model or "").endswith("-r2v")
        if reference:
            if ratio not in (None, *VIDU_RATIOS):
                return "Unsupported Vidu Q4 reference ratio"
            if strict and not str(prompt or "").strip():
                return "Vidu Q4 R2V prompt is required"
            for i in range(1, 4):
                url = str(kwargs.get(f"audio_url{i}") or "").strip()
                parsed = urlparse(url)
                if url and (parsed.scheme not in ("http", "https") or not parsed.netloc):
                    return "audio URL must use HTTP(S)"
                if strict and url and kwargs.get(f"audio{i}") is not None:
                    return f"audio{i} accepts one local AUDIO or one MP3 URL, not both"
        return True

    def collect_media(self, values, config, progress):
        validation = self.VALIDATE_INPUTS(**values, strict=True)
        if validation is not True:
            raise api.SeedanceLowPriceError(validation)
        reference = values["model"].endswith("-r2v")
        images = [(i, values[f"image{i}"]) for i in range(1, 16)
                  if values.get(f"image{i}") is not None]
        if not reference and (len(images) != 1 or values.get("image1") is None):
            raise api.SeedanceLowPriceError("Vidu Q4 I2V requires exactly image1")
        if reference and not images:
            raise api.SeedanceLowPriceError("Vidu Q4 R2V requires 1-15 images")
        for i, image in images:
            _single_image(image, f"image{i}")
        audios = []
        if reference:
            for i in range(1, 4):
                audio = values.get(f"audio{i}")
                url = str(values.get(f"audio_url{i}") or "").strip()
                if audio is not None:
                    waveform = audio.get("waveform") if isinstance(audio, dict) else None
                    shape = getattr(waveform, "shape", ())
                    if len(shape) not in (2, 3) or (len(shape) == 3 and int(shape[0]) != 1):
                        raise api.SeedanceLowPriceError(f"audio{i} requires exactly one AUDIO")
                if audio is not None or url:
                    audios.append((i, audio, url))
        # Encode all local audio before uploading anything, including FFmpeg preflight.
        encoded = {i: audio_to_mp3_bytes(audio) for i, audio, _ in audios if audio is not None}
        total = len(images) + len(audios)
        image_urls, audio_urls = [], []
        for i, image in images:
            image_urls.append(api.upload_media(api.image_to_png_bytes(image),
                                               f"vidu_q4_image_{i}.png", "image/png", config))
            progress(int(len(image_urls) / total * 20))
        for i, audio, url in audios:
            if audio is not None:
                url = api.upload_media(encoded[i], f"vidu_q4_audio_{i}.mp3", "audio/mpeg", config)
            audio_urls.append(url)
            progress(int((len(image_urls) + len(audio_urls)) / total * 20))
        return {"images": image_urls, "audio_urls": audio_urls}

    def build_payload(self, values, media):
        validation = self.VALIDATE_INPUTS(**values, strict=True)
        if validation is not True:
            raise api.SeedanceLowPriceError(validation)
        reference = values["model"].endswith("-r2v")
        images = media.get("images") or []
        if not (1 <= len(images) <= 15 if reference else len(images) == 1):
            raise api.SeedanceLowPriceError("Invalid Vidu Q4 image count")
        metadata = {"resolution": values["resolution"],
                    "generate_audio": bool(values.get("generate_audio", True)),
                    "is_rec": bool(values.get("is_rec", True)),
                    "watermark": bool(values.get("watermark", False))}
        if reference:
            metadata["ratio"] = values.get("ratio", "16:9")
            audio_urls = media.get("audio_urls") or []
            if len(audio_urls) > 3:
                raise api.SeedanceLowPriceError("Vidu Q4 accepts at most 3 MP3 references")
            if audio_urls:
                metadata["audio_urls"] = list(audio_urls)
        payload = {"model": values["model"], "seconds": str(values["seconds"]),
                   "images": list(images), "metadata": metadata}
        # The live gateway requires prompt even though Q4 I2V docs allow omission.
        payload["prompt"] = str(values.get("prompt") or "").strip() or VIDU_I2V_DEFAULT_PROMPT
        return payload

    def generate(self, model, prompt, seconds, resolution, ratio, generate_audio,
                 is_rec, watermark, audio_url1="", audio_url2="", audio_url3="",
                 api_config=None, skip_error=False, seed=0, **kwargs):
        del seed
        task_id = ""
        bar = api.comfy.utils.ProgressBar(100) if api.COMFYUI_AVAILABLE else None
        values = dict(model=model, prompt=prompt, seconds=seconds, resolution=resolution,
                      ratio=ratio, generate_audio=generate_audio, is_rec=is_rec,
                      watermark=watermark, audio_url1=audio_url1, audio_url2=audio_url2,
                      audio_url3=audio_url3, **kwargs)
        try:
            config = api.resolve_config(api_config)
            media = self.collect_media(values, config, lambda value: _progress(bar, value))
            task_id, submit = api.submit_legacy_video_task(self.build_payload(values, media), config)
            _progress(bar, 25)
            result = api.poll_legacy_video_task(
                task_id, config,
                on_progress=lambda value: _progress(bar, 25 + int(value * .7)),
            )
            url = api.extract_legacy_video_url(result)
            video = api.download_video(url)
            _progress(bar, 100)
            return (video, url, task_id, _response(model, task_id, submit, result))
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            return (api.make_error_video(message), "", "",
                    json.dumps({"status": "error", "model": model, "message": message}))
