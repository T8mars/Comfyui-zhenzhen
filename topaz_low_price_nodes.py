"""Topaz video restoration for the Zhenzhen low-price channel."""

from __future__ import annotations

import json
from urllib.parse import urlparse

try:
    from . import seedance_low_price_nodes as api
except ImportError:
    import seedance_low_price_nodes as api


TOPAZ_MODEL = "Topaz-Upscale-LowPirce"
TOPAZ_RESOLUTIONS = ["720p", "1080p", "2K", "4K"]
TOPAZ_QUALITIES = ["Ultra", "Max", "High", "Medium", "Low"]


def submit_topaz_task(payload, config):
    # A timed-out creation request may already be running; never replay it.
    try:
        response = api._get_session().post(
            f"{config['base_url']}/v1/video/generations",
            headers=api._headers(config["api_key"]), json=payload,
            timeout=config.get("timeout", 60),
        )
    except api.requests.RequestException as exc:
        raise api.SeedanceLowPriceError(
            f"Topaz submission could not be confirmed ({type(exc).__name__}); "
            "the request was not resubmitted. Check the website task list before retrying."
        ) from None
    try:
        data = api._response_json(response)
        if not 200 <= response.status_code < 300:
            message = api.extract_error_message(data, "request rejected")
            raise api.SeedanceLowPriceError(
                f"Topaz submit rejected (HTTP {response.status_code}): {message}; not resubmitted"
            )
        task = data.get("data") if isinstance(data, dict) else None
        task_id = (data.get("id") or data.get("task_id")) if isinstance(data, dict) else None
        if not task_id and isinstance(task, dict):
            task_id = task.get("id") or task.get("task_id")
        if not task_id:
            raise api.SeedanceLowPriceError(
                "Topaz submit response had no id/task_id; not resubmitted. Check the website task list."
            )
        return str(task_id), data
    finally:
        response.close()


def extract_topaz_video_url(response):
    try:
        return api.extract_legacy_video_url(response)
    except api.SeedanceLowPriceError:
        pass
    containers = [response]
    visited = set()
    for container in containers:
        if not isinstance(container, dict) or id(container) in visited:
            continue
        visited.add(id(container))
        urls = container.get("video_urls")
        if isinstance(urls, list):
            for url in urls:
                if isinstance(url, str) and url.strip():
                    return url.strip()
        containers.extend(container.get(key) for key in ("data", "content", "metadata", "result"))
    raise api.SeedanceLowPriceError("Topaz completed but no result video URL was returned")


class T8ZhenzhenTopazVideoUpscaleLowPrice:
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    RETURN_TYPES = (api.VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_url": ("STRING", {"default": "",
                                          "tooltip": "Public MP4 URL; leave empty for input_video."}),
                "resolution": (TOPAZ_RESOLUTIONS, {"default": "1080p",
                                                   "tooltip": "Output pixel budget; preserves source aspect ratio."}),
                "model": (TOPAZ_QUALITIES, {"default": "Max",
                                            "tooltip": "Restoration model; submitted as metadata.quality."}),
            },
            "optional": {
                "input_video": (api.VIDEO_TYPE,),
                "api_config": (api.CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF,
                                 "step": 1, "control_after_generate": True,
                                 "tooltip": "ComfyUI cache seed only; not sent to Topaz."}),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, video_url=None, resolution=None, model=None, strict=False,
                        input_video=None, **kwargs):
        if resolution not in (None, *TOPAZ_RESOLUTIONS):
            return "Topaz resolution must be 720p, 1080p, 2K, or 4K"
        if model not in (None, *TOPAZ_QUALITIES):
            return "Topaz restoration model must be Ultra, Max, High, Medium, or Low"
        url = str(video_url or "").strip()
        if url:
            try:
                parsed = urlparse(url)
                valid = parsed.scheme in ("http", "https") and bool(parsed.hostname)
            except ValueError:
                valid = False
            if not valid:
                return "video_url must be a public HTTP(S) MP4 URL"
        if strict and bool(url) == (input_video is not None):
            return "Topaz requires exactly one source: input_video or video_url"
        return True

    @classmethod
    def build_payload(cls, video_url, resolution="1080p", model="Max"):
        validation = cls.VALIDATE_INPUTS(video_url, resolution, model, strict=True)
        if validation is not True:
            raise api.SeedanceLowPriceError(validation)
        return {"model": TOPAZ_MODEL, "metadata": {
            "video_url": [str(video_url).strip()], "resolution": resolution, "quality": model,
        }}

    def generate(self, video_url="", resolution="1080p", model="Max", input_video=None,
                 api_config=None, skip_error=False, seed=0):
        del seed
        bar = api.comfy.utils.ProgressBar(100) if api.COMFYUI_AVAILABLE else None

        def progress(value):
            if bar is not None:
                bar.update_absolute(value, 100)

        try:
            validation = self.VALIDATE_INPUTS(
                video_url, resolution, model, strict=True, input_video=input_video,
            )
            if validation is not True:
                raise api.SeedanceLowPriceError(validation)
            source_url = str(video_url or "").strip()
            video_bytes = None
            if not source_url:
                video_bytes, extension = api.video_to_upload_bytes(input_video)
                if extension.lower() != "mp4" or video_bytes[4:8] != b"ftyp":
                    raise api.SeedanceLowPriceError("Topaz requires one valid MP4 video")
                if len(video_bytes) > 50 * 1024 * 1024:
                    raise api.SeedanceLowPriceError("Topaz local video exceeds the 50 MB upload limit")
            config = api.resolve_config(api_config)
            if video_bytes is not None:
                source_url = api.upload_media(video_bytes, "topaz_input.mp4", "video/mp4", config)
            progress(20)
            task_id, submit = submit_topaz_task(self.build_payload(source_url, resolution, model), config)
            progress(25)
            result = api.poll_legacy_video_task(
                task_id, config, on_progress=lambda value: progress(25 + int(value * .7)),
            )
            result_url = extract_topaz_video_url(result)
            progress(95)
            video = api.download_video(result_url)
            progress(100)
            response = json.dumps({"status": "SUCCESS", "model": TOPAZ_MODEL, "task_id": task_id,
                                   "submit": submit, "result": result}, ensure_ascii=False, indent=2)
            return (video, result_url, task_id, response)
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            return (api.make_error_video(message), "", "",
                    json.dumps({"status": "error", "model": TOPAZ_MODEL, "message": message},
                               ensure_ascii=False))
