"""Qwen Image Global 2.1 and Animate Motion Transfer low-price nodes."""

from __future__ import annotations

import json
import math
from typing import Any

try:
    from . import seedance_low_price_nodes as api
except ImportError:
    import seedance_low_price_nodes as api


QWEN_MODEL = "qwen-image-global-2.1"
ANIMATE_MODEL = "animate-motion-transfer"
QWEN_RESOLUTIONS = ["1k", "2k", "4k"]
QWEN_RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"]
ANIMATE_RESOLUTIONS = ["480p", "720p", "1080p"]
ANIMATE_RATIOS = ["adaptive", *QWEN_RATIOS, "custom"]
POSE_METHODS = ["vitpose", "sdpose", "wuwupose"]


def _progress_bar():
    return api.comfy.utils.ProgressBar(100) if api.COMFYUI_AVAILABLE else None


def _progress(bar, value):
    if bar is not None:
        try:
            bar.update_absolute(value, 100)
        except Exception:
            pass


def _single_image(value, label):
    shape = getattr(value, "shape", ())
    if len(shape) != 4 or int(shape[0]) != 1:
        raise api.SeedanceLowPriceError(f"{label} must contain exactly one IMAGE")


def _response(model, task_id, submit, result):
    return json.dumps(
        {"status": "completed", "model": model, "task_id": task_id,
         "submit": submit, "result": result},
        ensure_ascii=False,
        indent=2,
    )


class T8ZhenzhenQwenImageGlobal21LowPrice:
    @classmethod
    def INPUT_TYPES(cls):
        optional = {f"image{i}": ("IMAGE",) for i in range(1, 11)}
        optional["api_config"] = (api.CONFIG_TYPE,)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "resolution": (QWEN_RESOLUTIONS, {"default": "2k"}),
                "ratio": (QWEN_RATIOS, {"default": "3:4"}),
                "seed": ("INT", {"default": -1, "min": -1,
                                "max": 9007199254740991, "step": 1,
                                "control_after_generate": True,
                                "tooltip": "-1 uses a random API seed; 0 is a valid fixed seed."}),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(cls, prompt="", resolution="2k", ratio="3:4", seed=-1,
                        strict=False, **kwargs):
        if strict and not str(prompt or "").strip():
            return "Qwen Image Global 2.1 prompt is required"
        if ((resolution is not None and resolution not in QWEN_RESOLUTIONS)
                or (ratio is not None and ratio not in QWEN_RATIOS)):
            return "Unsupported Qwen Image Global 2.1 resolution or ratio"
        if seed is not None and not -1 <= int(seed) <= 9007199254740991:
            return "Qwen Image Global 2.1 seed must be -1 or 0..9007199254740991"
        for index in range(1, 11):
            image = kwargs.get(f"image{index}")
            if image is not None:
                try:
                    _single_image(image, f"image{index}")
                except api.SeedanceLowPriceError as exc:
                    return str(exc)
        return True

    @staticmethod
    def build_payload(prompt, resolution, ratio, seed, urls):
        metadata = {"ratio": ratio, "resolution": resolution}
        if int(seed) >= 0:
            metadata["seed"] = int(seed)
        payload = {"model": QWEN_MODEL, "prompt": str(prompt).strip(), "metadata": metadata}
        if urls:
            payload["images"] = urls
        return payload

    def generate(self, prompt, resolution, ratio, seed, api_config=None,
                 skip_error=False, **kwargs):
        task_id = ""
        bar = _progress_bar()
        try:
            validation = self.VALIDATE_INPUTS(
                prompt, resolution, ratio, seed, strict=True, **kwargs,
            )
            if validation is not True:
                raise api.SeedanceLowPriceError(validation)
            config = api.resolve_config(api_config)
            references = [(i, kwargs[f"image{i}"]) for i in range(1, 11)
                          if kwargs.get(f"image{i}") is not None]
            urls = []
            for index, image in references:
                urls.append(api.upload_media(
                    api.image_to_png_bytes(image), f"qwen21_reference_{index}.png",
                    "image/png", config,
                ))
                _progress(bar, int(len(urls) / len(references) * 15))
            payload = self.build_payload(prompt, resolution, ratio, seed, urls)
            task_id, submit = api.submit_image_task(payload, config)
            _progress(bar, 25)
            result = api.poll_image_task(
                task_id, config,
                on_progress=lambda value: _progress(bar, 25 + int(value * .7)),
            )
            result_url = api.extract_image_urls(result)[0]
            image = api.download_image(result_url)
            _progress(bar, 100)
            return (image, result_url, task_id, _response(QWEN_MODEL, task_id, submit, result))
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            return (api.torch.ones((1, 512, 512, 3), dtype=api.torch.float32), "", task_id,
                    json.dumps({"status": "error", "model": QWEN_MODEL,
                                "task_id": task_id, "message": message}, ensure_ascii=False))


class T8ZhenzhenAnimateMotionTransferLowPrice:
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_url": ("STRING", {"default": "", "tooltip": "Leave empty for input_image."}),
                "video_url": ("STRING", {"default": "", "tooltip": "Leave empty for input_video."}),
                "resolution": (ANIMATE_RESOLUTIONS, {"default": "720p"}),
                "ratio": (ANIMATE_RATIOS, {"default": "adaptive"}),
                "custom_ratio": ("STRING", {"default": "16:9"}),
                "frame_rate": ("INT", {"default": 30, "min": 1, "max": 999999}),
                "max_frames": ("INT", {"default": 0, "min": 0, "max": 999999,
                                      "tooltip": "0 uses the API default."}),
                "skip_frames": ("INT", {"default": 0, "min": 0, "max": 999999}),
                "pose_method": (POSE_METHODS, {"default": "vitpose"}),
                "normal_mode": ("BOOLEAN", {"default": True}),
                "neck_correction": ("BOOLEAN", {"default": False}),
                "pose_strength": ("FLOAT", {"default": 1.0, "step": .01}),
                "camera_motion": ("BOOLEAN", {"default": False}),
                "camera_strength": ("FLOAT", {"default": 1.0, "step": .01}),
                "mask_mode": ("BOOLEAN", {"default": False}),
                "expression_strength": ("FLOAT", {"default": .8, "step": .01}),
                "chest_motion_strength": ("FLOAT", {"default": .2, "step": .01}),
            },
            "optional": {
                "input_image": ("IMAGE",),
                "input_video": (api.VIDEO_TYPE,),
                "api_config": (api.CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF,
                                "control_after_generate": True,
                                "tooltip": "ComfyUI cache seed only; not sent to the API."}),
            },
        }

    RETURN_TYPES = (api.VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(cls, image_url="", video_url="", resolution="720p",
                        ratio="adaptive", custom_ratio="16:9", frame_rate=30,
                        max_frames=0, skip_frames=0, pose_method="vitpose",
                        input_image=None, input_video=None, strict=False, **kwargs):
        for name, value in (("image_url", image_url), ("video_url", video_url)):
            if value and not str(value).strip().startswith(("http://", "https://")):
                return f"{name} must be an http(s) URL"
        if ((resolution is not None and resolution not in ANIMATE_RESOLUTIONS)
                or (ratio is not None and ratio not in ANIMATE_RATIOS)):
            return "Unsupported Animate resolution or ratio"
        if ratio == "custom":
            parts = str(custom_ratio).split(":")
            if len(parts) != 2 or any(not part.isdigit() or not 1 <= int(part) <= 999999
                                       for part in parts):
                return "custom_ratio must be width:height (1..999999)"
        if ((frame_rate is not None and not 1 <= int(frame_rate) <= 999999)
                or (max_frames is not None and not 0 <= int(max_frames) <= 999999)):
            return "frame_rate or max_frames is out of range"
        if skip_frames is not None and not 0 <= int(skip_frames) <= 999999:
            return "skip_frames is out of range"
        if resolution == "1080p" and max_frames and int(max_frames) > int(frame_rate) * 10:
            return "1080p max_frames cannot exceed frame_rate x 10"
        if pose_method is not None and pose_method not in POSE_METHODS:
            return "Unsupported Animate pose_method"
        for name in ("pose_strength", "camera_strength", "expression_strength",
                     "chest_motion_strength"):
            if name in kwargs and not math.isfinite(float(kwargs[name])):
                return f"{name} must be finite"
        if strict:
            if bool(str(image_url or "").strip()) == (input_image is not None):
                return "Provide exactly one character image: image_url or input_image"
            if bool(str(video_url or "").strip()) == (input_video is not None):
                return "Provide exactly one motion video: video_url or input_video"
            if input_image is not None:
                try:
                    _single_image(input_image, "input_image")
                except api.SeedanceLowPriceError as exc:
                    return str(exc)
        return True

    @staticmethod
    def build_payload(image_url, video_url, resolution, ratio, custom_ratio,
                      frame_rate, pose_method, **kwargs):
        metadata = {
            "video_url": [video_url], "resolution": resolution,
            "ratio": custom_ratio.strip() if ratio == "custom" else ratio,
            "frame_rate": int(frame_rate), "pose_method": pose_method,
        }
        defaults = {
            "max_frames": 0, "skip_frames": 0, "normal_mode": True,
            "neck_correction": False, "pose_strength": 1.0,
            "camera_motion": False, "camera_strength": 1.0,
            "mask_mode": False, "expression_strength": .8,
            "chest_motion_strength": .2,
        }
        for name, default in defaults.items():
            value = kwargs.get(name, default)
            if value != default:
                metadata[name] = value
        return {"model": ANIMATE_MODEL, "images": [image_url], "metadata": metadata}

    def generate(self, image_url, video_url, resolution, ratio, custom_ratio,
                 frame_rate, max_frames, skip_frames, pose_method, normal_mode,
                 neck_correction, pose_strength, camera_motion, camera_strength,
                 mask_mode, expression_strength, chest_motion_strength,
                 input_image=None, input_video=None, api_config=None,
                 skip_error=False, seed=0):
        del seed
        task_id = ""
        bar = _progress_bar()
        options = dict(max_frames=max_frames, skip_frames=skip_frames,
                       normal_mode=normal_mode, neck_correction=neck_correction,
                       pose_strength=pose_strength, camera_motion=camera_motion,
                       camera_strength=camera_strength, mask_mode=mask_mode,
                       expression_strength=expression_strength,
                       chest_motion_strength=chest_motion_strength)
        try:
            validation = self.VALIDATE_INPUTS(
                image_url, video_url, resolution, ratio, custom_ratio,
                frame_rate, max_frames, skip_frames, pose_method,
                input_image=input_image, input_video=input_video, strict=True,
                pose_strength=pose_strength, camera_strength=camera_strength,
                expression_strength=expression_strength,
                chest_motion_strength=chest_motion_strength,
            )
            if validation is not True:
                raise api.SeedanceLowPriceError(validation)
            config = api.resolve_config(api_config)
            image_url = str(image_url).strip()
            video_url = str(video_url).strip()
            if not image_url:
                image_url = api.upload_media(
                    api.image_to_png_bytes(input_image), "animate_character.png", "image/png", config,
                )
            _progress(bar, 10)
            if not video_url:
                data, extension = api.video_to_upload_bytes(input_video)
                mime = {"mp4": "video/mp4", "mov": "video/quicktime",
                        "avi": "video/x-msvideo", "mkv": "video/x-matroska"}[extension]
                video_url = api.upload_media(data, f"animate_motion.{extension}", mime, config)
            _progress(bar, 20)
            payload = self.build_payload(
                image_url, video_url, resolution, ratio, custom_ratio,
                frame_rate, pose_method, **options,
            )
            task_id, submit = api.submit_legacy_video_task(payload, config)
            _progress(bar, 30)
            result = api.poll_legacy_video_task(
                task_id, config,
                on_progress=lambda value: _progress(bar, 30 + int(value * .6)),
            )
            result_url = api.extract_legacy_video_url(result)
            video = api.download_video(result_url)
            _progress(bar, 100)
            return (video, result_url, task_id, _response(ANIMATE_MODEL, task_id, submit, result))
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            return (api.make_error_video(message), "", task_id,
                    json.dumps({"status": "error", "model": ANIMATE_MODEL,
                                "task_id": task_id, "message": message}, ensure_ascii=False))
