"""Motion Video Standard/Pro generation and revision for the low-price channel."""

from __future__ import annotations

import json
import time
from urllib.parse import urlparse

try:
    from . import seedance_low_price_nodes as api
    from .execution_seed import EXECUTION_SEED_SPEC
except ImportError:
    import seedance_low_price_nodes as api
    from execution_seed import EXECUTION_SEED_SPEC


MOTION_MODELS = ["zhenzhen/motion-video", "zhenzhen/motion-video-pro"]
MOTION_TEMPLATES = ["api_default", "hype-kinetic", "cyber-glitch", "blueprint-tech", "synthwave",
                    "swiss-minimal", "code-cinema", "data-story", "chalk-hand", "voxel-world", "cinematic-trailer"]


def string_list(value, field):
    if not isinstance(value, str):
        raise api.SeedanceLowPriceError(f"{field} requires one item per line or a JSON string array")
    text = value.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            items = json.loads(text)
        except ValueError:
            raise api.SeedanceLowPriceError(f"{field} contains invalid JSON") from None
    else:
        items = text.splitlines()
    if not isinstance(items, list) or any(not isinstance(item, str) or not item.strip() for item in items):
        raise api.SeedanceLowPriceError(f"{field} must contain non-empty strings")
    return [item.strip() for item in items]


def http_url(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        return (parsed.scheme in {"http", "https"} and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None and not any(char.isspace() for char in value))
    except ValueError:
        return False


def submit_motion_task(payload, config):
    # A lost task-creation response must not trigger another generation.
    try:
        response = api._get_session().post(f"{config['base_url']}/v1/video/generations",
            headers=api._headers(config["api_key"]), json=payload, timeout=config.get("timeout", 60))
    except api.requests.RequestException as error:
        raise api.SeedanceLowPriceError(
            f"Motion Video submission could not be confirmed ({type(error).__name__}); not retried. Check the website task list."
        ) from None
    try:
        data = api._response_json(response)
        if not 200 <= response.status_code < 300:
            message = api.extract_error_message(data, "request rejected")
            raise api.SeedanceLowPriceError(f"Motion Video submit rejected (HTTP {response.status_code}): {message}; not retried")
        task_id = (data.get("task_id") or data.get("id")) if isinstance(data, dict) else None
        if not task_id and isinstance(data, dict) and isinstance(data.get("data"), dict):
            task_id = data["data"].get("task_id") or data["data"].get("id")
        if not task_id:
            raise api.SeedanceLowPriceError("Motion Video submit response has no task ID; not retried. Check the website task list.")
        return str(task_id), data
    finally:
        response.close()


def poll_motion_task(task_id, config, on_progress=None, sleep=time.sleep, clock=time.monotonic):
    started, failures = clock(), 0
    while True:
        if clock() - started >= config.get("max_poll_time", 1800):
            raise api.SeedanceLowPriceError("Motion Video polling timed out; the upstream task may still be running")
        sleep(config.get("poll_interval", 4))
        response = None
        try:
            response = api._get_session().get(f"{config['base_url']}/v1/video/generations/{task_id}",
                headers=api._headers(config["api_key"], json_content=False), timeout=30)
            if response.status_code != 200:
                if 400 <= response.status_code < 500 and response.status_code not in (408, 429):
                    raise api.SeedanceLowPriceError(f"Motion Video polling rejected (HTTP {response.status_code})")
                raise api.requests.RequestException(f"HTTP {response.status_code}")
            data = api._response_json(response)
            record = data.get("data") if isinstance(data, dict) else None
            if not isinstance(record, dict) or "status" not in record:
                record = data
            if not isinstance(record, dict) or not isinstance(record.get("status"), str) or not record["status"].strip():
                raise api.requests.RequestException("Missing task status")
        except api.requests.RequestException:
            failures += 1
            if failures >= 6:
                raise api.SeedanceLowPriceError("Motion Video polling repeatedly failed; no new task was submitted") from None
            sleep(min(failures * 2, 10))
            continue
        finally:
            if response is not None:
                response.close()
        failures = 0
        status = record["status"].strip().upper()
        value = api._coerce_progress(record.get("progress"))
        if on_progress and value is not None:
            on_progress(value)
        if status in {"SUCCESS", "SUCCEEDED", "COMPLETED"}:
            return data
        if status in {"FAILURE", "FAILED", "CANCELED", "CANCELLED"}:
            reason = record.get("fail_reason") or api.extract_error_message(record, "upstream render failed")
            raise api.SeedanceLowPriceError(f"Motion Video task failed: {reason}")
        # Preview readiness and future intermediate states are not final renders.


class T8ZhenzhenMotionVideoLowPrice:
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    RETURN_TYPES = (api.VIDEO_TYPE,) + ("STRING",) * 9
    RETURN_NAMES = ("video", "video_url", "task_id", "response", "cover_url", "preview_url",
                    "html_preview_url", "subtitle_url", "storyboard", "fallback_scenes")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": (MOTION_MODELS, {"default": MOTION_MODELS[0]}),
            "operation": (["generate", "revise"], {"default": "generate"}),
            "prompt": ("STRING", {"default": "", "multiline": True}),
            "duration": ([15, 30, 45, 60], {"default": 15}),
            "ratio": (["16:9", "9:16", "1:1"], {"default": "16:9"}),
            "resolution": (["720p", "1080p"], {"default": "720p"}),
            "template_id": (MOTION_TEMPLATES, {"default": "api_default"}),
            "title": ("STRING", {"default": ""}),
            "subtitle": ("STRING", {"default": ""}),
            "keywords": ("STRING", {"default": "", "multiline": True, "tooltip": "One keyword per line or a JSON string array."}),
            "signature": ("STRING", {"default": ""}),
            "language": ("STRING", {"default": "zh-CN"}),
            "music": (["api_default", "auto"], {"default": "auto"}),
            "assets": ("STRING", {"default": "", "multiline": True,
                "tooltip": "Up to 4 persistent public HTTP(S) image URLs, one per line or a JSON array. No local files or temporary uploads; upstream image rendering may be incomplete."}),
            "revise_from": ("STRING", {"default": "", "tooltip": "Connect your completed Motion Video task_id."}),
            "revision_instruction": ("STRING", {"default": "", "multiline": True}),
        }, "optional": {
            "api_config": (api.CONFIG_TYPE,),
            "skip_error": ("BOOLEAN", {"default": False}),
            "seed": EXECUTION_SEED_SPEC,
        }}

    @classmethod
    def VALIDATE_INPUTS(cls, strict=False, **values):
        definitions = cls.INPUT_TYPES()["required"]
        for name in ("model", "operation", "duration", "ratio", "resolution", "template_id", "music"):
            value = values.get(name, definitions[name][1]["default"])
            if value is None and not strict:
                continue
            if value not in definitions[name][0] or (name == "duration" and type(value) is not int):
                return f"Unsupported Motion Video {name}"
        operation = values.get("operation", "generate")
        text_fields = ["prompt", "title", "subtitle", "signature", "language"]
        if operation == "revise":
            text_fields += ["revise_from", "revision_instruction"]
        for name in text_fields:
            if name in values and not isinstance(values[name], str) and (strict or values[name] is not None):
                return f"Motion Video {name} must be text"
        try:
            for name in ("keywords", "assets"):
                if not strict and values.get(name, "") is None:
                    continue
                items = string_list(values.get(name, ""), name)
                if name == "assets" and (len(items) > 4 or any(not http_url(item) for item in items)):
                    return "assets requires at most 4 persistent public HTTP(S) image URLs"
        except api.SeedanceLowPriceError as error:
            return str(error)
        if strict:
            if not values.get("prompt", "").strip():
                return "Motion Video prompt is required"
            if operation == "revise" and (not values.get("revise_from", "").strip() or not values.get("revision_instruction", "").strip()):
                return "Revision requires revise_from and revision_instruction"
        return True

    @classmethod
    def build_payload(cls, values):
        validation = cls.VALIDATE_INPUTS(strict=True, **values)
        if validation is not True:
            raise api.SeedanceLowPriceError(validation)
        defaults = {name: definition[1]["default"] for name, definition in cls.INPUT_TYPES()["required"].items()}
        options = {**defaults, **values}
        payload = {name: options[name] for name in ("model", "duration", "ratio", "resolution")}
        payload["prompt"] = options["prompt"].strip()
        motion = {}
        for name in ("template_id", "title", "subtitle", "signature", "language", "music"):
            value = options[name].strip()
            if value and not (name in ("template_id", "music") and value == "api_default"):
                motion[name] = value
        for name in ("keywords", "assets"):
            items = string_list(options[name], name)
            if items:
                motion[name] = items
        if options["operation"] == "revise":
            motion.update({name: options[name].strip() for name in ("revise_from", "revision_instruction")})
        if motion:
            payload["motion"] = motion
        return payload

    @classmethod
    def result_content(cls, result):
        current = result
        for _ in range(4):
            if not isinstance(current, dict):
                break
            content = current.get("content")
            if isinstance(content, dict) and http_url(content.get("video_url")):
                normalized = dict(content)
                for name in cls.RETURN_NAMES[4:]:
                    if name not in normalized and name in current:
                        normalized[name] = current[name]
                return normalized
            current = current.get("data")
        raise api.SeedanceLowPriceError("Motion Video completed without final content.video_url")

    def generate(self, api_config=None, skip_error=False, seed=0, **values):
        del seed
        try:
            payload = self.build_payload(values)
            config = api.resolve_config(api_config)
            bar = api.comfy.utils.ProgressBar(100) if api.COMFYUI_AVAILABLE else None

            def progress(value):
                if bar is not None:
                    bar.update_absolute(int(value), 100)

            progress(0)
            task_id, submitted = submit_motion_task(payload, config)
            progress(20)
            result = poll_motion_task(task_id, config, on_progress=lambda value: progress(20 + value * .75))
            progress(95)
            content = self.result_content(result)
            if content.get("fallback_scenes"):
                print("[Motion Video] WARNING: upstream used fallback scenes; inspect the fallback_scenes output.")
            video = api.download_video(content["video_url"])
            extras = []
            for name in self.RETURN_NAMES[4:]:
                value = content.get(name)
                extras.append("" if value is None else value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
            response = json.dumps({"status": "SUCCESS", "model": payload["model"], "task_id": task_id,
                                   "submit": submitted, "result": result}, ensure_ascii=False, indent=2)
            progress(100)
            return (video, content["video_url"], task_id, response, *extras)
        except Exception as error:
            if not skip_error:
                raise
            message = f"{type(error).__name__}: {error}"
            return (api.make_error_video(message), "", "", json.dumps({"status": "error", "message": message}), *("",) * 6)
