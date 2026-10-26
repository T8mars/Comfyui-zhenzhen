"""Independent Kling 4 video, reusable element and reusable voice nodes."""

from __future__ import annotations

from io import BytesIO
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.parse import urlparse

try:
    from . import seedance_low_price_nodes as api
    from .execution_seed import EXECUTION_SEED_SPEC
except ImportError:
    import seedance_low_price_nodes as api
    from execution_seed import EXECUTION_SEED_SPEC


RATIOS = ["21:9", "16:9", "1:1", "9:16"]
RESOLUTIONS = ["720p", "1080p"]
WATERMARKS = ["api_default", "disabled", "enabled"]
TAGS = [f"o_{number}" for number in range(101, 109)]
Error = api.SeedanceLowPriceError


def string_list(value, name):
    if not isinstance(value, str):
        raise Error(f"Kling 4 {name} requires one item per line or a JSON string array")
    value = value.strip()
    if not value:
        return []
    try:
        result = json.loads(value) if value.startswith("[") else value.splitlines()
    except ValueError:
        raise Error(f"Kling 4 {name} contains invalid JSON") from None
    if not isinstance(result, list) or any(not isinstance(item, str) or not item.strip() for item in result):
        raise Error(f"Kling 4 {name} requires non-empty strings")
    return [item.strip() for item in result]


def http_url(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        return (parsed.scheme in {"http", "https"} and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None and not any(c.isspace() for c in value))
    except ValueError:
        return False


def prompt_valid(prompt, required=False):
    if not isinstance(prompt, str):
        raise Error("Kling 4 prompt must be text")
    if required and not prompt.strip():
        raise Error("Kling 4 prompt is required")
    english = sum(ord(char) < 128 for char in prompt)
    other = len(prompt) - english
    if english * 11000 + other * 26000 > 26000 * 11000:
        raise Error("Kling 4 prompt exceeds English/26000 + non-English/11000 <=1")


def reject_extra_slots(values, prefix, maximum):
    if any(name.startswith(prefix) and name[len(prefix):].isdigit() and not 1 <= int(name[len(prefix):]) <= maximum
           and value is not None for name, value in values.items()):
        raise Error(f"Kling 4 supports at most {maximum} {prefix} inputs")


def validate_video(kind, values, strict=False):
    prompt_valid(values.get("prompt", ""), required=strict and kind != "i2v")
    seconds = values.get("seconds", 3)
    if type(seconds) is not int or not 3 <= seconds <= 30:
        raise Error("Kling 4 duration must be an integer from 3 to 30 seconds")
    if values.get("resolution", "720p") not in RESOLUTIONS:
        raise Error("Kling 4 resolution must be 720p or 1080p")
    if kind != "i2v" and values.get("ratio", "16:9") not in RATIOS + (["adaptive"] if kind == "omni" else []):
        raise Error("Unsupported Kling 4 ratio")
    if values.get("watermark", "api_default") not in WATERMARKS:
        raise Error("Unsupported Kling 4 watermark control")
    reject_extra_slots(values, "image", 0 if kind == "t2v" else 2 if kind == "i2v" else 10)
    reject_extra_slots(values, "video", 5 if kind == "omni" else 0)
    if kind == "i2v" and strict and values.get("image1") is None:
        raise Error("Kling 4 I2V requires image1 as the first frame")
    if kind != "omni":
        return
    images = sum(values.get(f"image{i}") is not None for i in range(1, 11))
    videos = sum(values.get(f"video{i}") is not None for i in range(1, 6))
    urls = string_list(values.get("video_urls", ""), "video_urls")
    if any(not http_url(url) for url in urls):
        raise Error("Kling 4 video_urls must be public HTTP(S) links")
    videos += len(urls)
    image_ids = string_list(values.get("image_element_ids", ""), "image_element_ids")
    video_ids = string_list(values.get("video_element_ids", ""), "video_element_ids")
    voices = string_list(values.get("voice_ids", ""), "voice_ids")
    elements = image_ids + video_ids
    if len(elements) > 7 or len(video_ids) > 3 or len(voices) > 3:
        raise Error("Kling 4 Omni supports at most 7 elements, 3 video elements and 3 voices")
    if len(set(elements)) != len(elements):
        raise Error("Kling 4 element IDs must not be repeated across image/video lists")
    if videos > 5 or images + videos + len(elements) > 15 or videos + len(video_ids) > 5:
        raise Error("Kling 4 Omni: images/videos/elements <=15; videos/video elements <=5")


def video_payload(kind, values, media):
    validate_video(kind, values)
    prompt_valid(values.get("prompt", ""), required=kind != "i2v")
    images, videos = list(media.get("images", [])), list(media.get("videos", []))
    if kind == "i2v" and not 1 <= len(images) <= 2:
        raise Error("Kling 4 I2V requires one first frame and optional last frame")
    if kind == "omni" and (len(images) > 10 or len(videos) > 5):
        raise Error("Kling 4 Omni supports at most 10 images and 5 videos")
    metadata = {"resolution": values.get("resolution", "720p")}
    if kind != "i2v":
        metadata["ratio"] = values.get("ratio", "16:9")
    watermark = values.get("watermark", "api_default")
    if watermark != "api_default":
        metadata["watermark"] = watermark == "enabled"
    if kind == "omni":
        elements = string_list(values.get("image_element_ids", ""), "image_element_ids")
        video_elements = string_list(values.get("video_element_ids", ""), "video_element_ids")
        if len(images) + len(videos) + len(elements + video_elements) > 15 or len(videos) + len(video_elements) > 5:
            raise Error("Kling 4 Omni combined material limit exceeded")
        if videos:
            metadata["video_url"] = videos
        if elements or video_elements:
            metadata["elementIds"] = elements + video_elements
        voices = string_list(values.get("voice_ids", ""), "voice_ids")
        if voices:
            metadata["voiceIds"] = voices
    payload = {"model": f"kling-v4-{kind}", "seconds": str(values.get("seconds", 3)), "metadata": metadata}
    if values.get("prompt", "").strip():
        payload["prompt"] = values["prompt"].strip()
    if images and kind != "t2v":
        payload["images"] = images
    return payload


def encode_image(image, element=False):
    shape = getattr(image, "shape", ())
    if len(shape) != 4 or shape[0] != 1 or min(shape[1:3]) <= 0 or shape[-1] not in (3, 4):
        raise Error("Each Kling 4 IMAGE socket requires one non-empty RGB/RGBA image, not a batch")
    array = image.detach().cpu().numpy() if hasattr(image, "detach") else api.np.asarray(image)
    if not api.np.isfinite(array).all():
        raise Error("Kling 4 image contains NaN or infinity")
    if element and (min(shape[1:3]) < 300 or not .4 <= shape[2] / shape[1] <= 2.5):
        raise Error("Element images require shortest edge >=300px and ratio 0.4-2.5")
    data = api.image_to_png_bytes(image)
    if len(data) > (10 if element else 30) * 1024 * 1024:
        raise Error("Kling 4 image exceeds its documented size limit")
    return data


def probe_video(data, extension):
    try:
        import av
    except ImportError:
        av = None
    if av is not None:
        try:
            with av.open(BytesIO(data)) as container:
                stream = next(iter(container.streams.video), None)
                if stream is None or next(container.decode(video=0), None) is None:
                    raise Error("Kling 4 requires a decodable video stream")
                duration = (float(stream.duration * stream.time_base) if stream.duration is not None
                            else float(container.duration or 0) / av.time_base)
                return {"width": stream.width, "height": stream.height, "duration": duration}
        except Error:
            raise
        except Exception as error:
            raise Error(f"Kling 4 video could not be decoded ({type(error).__name__})") from None
    ffmpeg = api._find_suno_ffmpeg()
    executable = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe") if ffmpeg else None
    if executable is None or not executable.is_file():
        raise Error("Local Kling 4 video validation requires existing PyAV or ffprobe beside FFmpeg")
    with tempfile.TemporaryDirectory(prefix="zhenzhen-kling4-probe-") as folder:
        path = Path(folder) / ("input." + extension)
        path.write_bytes(data)
        result = subprocess.run([str(executable), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                                capture_output=True, timeout=60, check=True)
        info = json.loads(result.stdout)
        stream = next((item for item in info.get("streams", []) if item.get("codec_type") == "video"), None)
        if stream is None:
            raise Error("Kling 4 requires a decodable video stream")
        return {"width": stream["width"], "height": stream["height"],
                "duration": float(stream.get("duration") or info.get("format", {}).get("duration") or 0)}


def validate_local_video(data, extension, element=False):
    if element and extension not in {"mp4", "mov"}:
        raise Error("Kling 4 video elements require MP4 or MOV")
    if len(data) > 50 * 1024 * 1024:
        raise Error("Local upload is limited to 50 MB; use a public video URL for larger sources")
    info = probe_video(data, extension)
    if not api.np.isfinite(info["duration"]) or info["duration"] <= 0:
        raise Error("Could not determine Kling 4 reference video duration")
    if element and (not 3 <= info["duration"] <= 8 or (info["width"], info["height"]) not in {(1920, 1080), (1080, 1920)}):
        raise Error("Kling 4 video elements require 3-8 seconds at 1920x1080 or 1080x1920")
    return info


def validate_element(values, strict=False):
    name, prompt = values.get("element_name", ""), values.get("prompt", "")
    if not isinstance(name, str) or not isinstance(prompt, str):
        raise Error("Kling 4 element name and description must be text")
    if len(name.strip()) > 20 or len(prompt.strip()) > 100 or strict and (not name.strip() or not prompt.strip()):
        raise Error("Kling 4 element name requires 1-20 characters; description requires 1-100")
    mode = values.get("reference_type", "image_refer")
    if mode not in ("image_refer", "video_refer"):
        raise Error("Unsupported Kling 4 element reference type")
    if not isinstance(values.get("element_voice_id", ""), str):
        raise Error("Kling 4 element_voice_id must be text")
    if any(tag not in TAGS for tag in string_list(values.get("tag_list", ""), "tag_list")):
        raise Error("Kling 4 element tags must be o_101 through o_108")
    if mode == "image_refer":
        reject_extra_slots(values, "image", 4)
        if strict and (values.get("image1") is None or not any(values.get(f"image{i}") is not None for i in (2, 3, 4))):
            raise Error("Image elements require image1 (front) and 1-3 different reference images")
    else:
        url = values.get("video_url", "")
        if not isinstance(url, str) or url.strip() and not http_url(url.strip()):
            raise Error("Kling 4 element video_url must be a public HTTP(S) link")
        local = values.get("input_video") is not None
        if local and url.strip() or strict and not local and not url.strip():
            raise Error("Choose one element video source: input_video or video_url")


def element_payload(values, media):
    validate_element(values)
    if not values.get("element_name", "").strip() or not values.get("prompt", "").strip():
        raise Error("Kling 4 element name and description are required")
    mode = values.get("reference_type", "image_refer")
    metadata = {"elementName": values["element_name"].strip(), "referenceType": mode}
    payload = {"model": "kling-v4-custom-element", "prompt": values["prompt"].strip(), "metadata": metadata}
    if mode == "image_refer":
        images = list(media.get("images", []))
        if not 2 <= len(images) <= 4:
            raise Error("Kling 4 image elements require 2-4 ordered images")
        payload["images"] = images
    else:
        videos = list(media.get("videos", []))
        if len(videos) != 1:
            raise Error("Kling 4 video elements require exactly one video")
        metadata["video_url"] = videos
    if values.get("element_voice_id", "").strip():
        metadata["elementVoiceId"] = values["element_voice_id"].strip()
    tags = string_list(values.get("tag_list", ""), "tag_list")
    if tags:
        metadata["tagList"] = tags
    return payload


def validate_voice(values, strict=False):
    name = values.get("voice_name", "")
    if not isinstance(name, str) or strict and not name.strip():
        raise Error("Kling 4 voice_name is required")
    mode = values.get("source_mode", "audio")
    if mode not in ("audio", "video_id"):
        raise Error("Unsupported Kling 4 voice source mode")
    if mode == "video_id":
        value = values.get("video_id", "")
        if not isinstance(value, str) or strict and not value.strip():
            raise Error("Kling 4 video_id requires the provider videoId, not the generic task_id")
        return
    url = values.get("audio_url", "")
    if not isinstance(url, str) or url.strip() and not http_url(url.strip()):
        raise Error("Kling 4 audio_url must be a public HTTP(S) link")
    local = values.get("audio") is not None
    if local and url.strip() or strict and not local and not url.strip():
        raise Error("Choose one voice sample: local AUDIO or audio_url")


def named_results(final):
    current = final
    for _ in range(5):
        if not isinstance(current, dict):
            break
        text = current.get("result_text")
        if isinstance(text, str) and text.strip():
            try:
                parsed = json.loads(text)
            except ValueError:
                raise Error("Kling 4 auxiliary result_text contains invalid JSON") from None
            rows = parsed.get("results") if isinstance(parsed, dict) else None
            if not isinstance(rows, list):
                raise Error("Kling 4 auxiliary response has no results array")
            values = {}
            for row in rows:
                if isinstance(row, dict) and isinstance(row.get("name"), str):
                    for field in ("text", "value", "url"):
                        value = row.get(field)
                        if isinstance(value, str) and value.strip():
                            values[row["name"]] = value.strip()
                            break
            return values
        current = current.get("data")
    raise Error("Kling 4 auxiliary response has no result_text")


def submit_kling_task(payload, config):
    # A lost creation response must not replay generation or reusable-ID creation.
    try:
        response = api._get_session().post(f"{config['base_url']}/v1/video/generations",
            headers=api._headers(config["api_key"]), json=payload, timeout=config.get("timeout", 60))
    except api.requests.RequestException as error:
        raise Error(f"Kling 4 submission could not be confirmed ({type(error).__name__}); not retried. Check the website task list.") from None
    try:
        data = api._response_json(response)
        if not 200 <= response.status_code < 300:
            message = api.extract_error_message(data, "request rejected")
            raise Error(f"Kling 4 submit rejected (HTTP {response.status_code}): {message}; not retried")
        task = data.get("data") if isinstance(data, dict) else None
        task_id = (data.get("id") or data.get("task_id")) if isinstance(data, dict) else None
        if not task_id and isinstance(task, dict):
            task_id = task.get("id") or task.get("task_id")
        if not task_id:
            raise Error("Kling 4 submit response has no task ID; not retried. Check the website task list.")
        return str(task_id), data
    finally:
        response.close()


def poll_kling_task(task_id, config, on_progress=None, sleep=time.sleep, clock=time.monotonic):
    started, failures = clock(), 0
    while True:
        if clock() - started >= config.get("max_poll_time", 1800):
            raise Error("Kling 4 polling timed out; the upstream task may still be running")
        sleep(config.get("poll_interval", 4))
        response = None
        try:
            response = api._get_session().get(f"{config['base_url']}/v1/video/generations/{task_id}",
                headers=api._headers(config["api_key"], json_content=False), timeout=30)
            if response.status_code != 200:
                if 400 <= response.status_code < 500 and response.status_code not in (408, 429):
                    raise Error(f"Kling 4 polling rejected (HTTP {response.status_code})")
                raise api.requests.RequestException("Transient task query failure")
            data = api._response_json(response)
            record = data.get("data") if isinstance(data, dict) else None
            if not isinstance(record, dict) or "status" not in record:
                record = data
            if not isinstance(record, dict) or not isinstance(record.get("status"), str) or not record["status"].strip():
                raise api.requests.RequestException("Missing task status")
        except api.requests.RequestException:
            failures += 1
            if failures >= 6:
                raise Error("Kling 4 polling repeatedly failed; no new task was submitted") from None
            sleep(min(failures * 2, 10))
            continue
        finally:
            if response is not None:
                response.close()
        failures = 0
        status = record["status"].strip().upper()
        progress = api._coerce_progress(record.get("progress"))
        if on_progress and progress is not None:
            on_progress(progress)
        if status in {"SUCCESS", "SUCCEEDED", "COMPLETED"}:
            return data
        if status in {"FAILURE", "FAILED", "CANCELED", "CANCELLED"}:
            reason = record.get("fail_reason") or api.extract_error_message(record, "upstream task failed")
            raise Error(f"Kling 4 task failed: {reason}")


def upload_prepared(prepared, config, progress):
    images, videos = prepared.get("images", []), prepared.get("videos", [])
    count = len(images) + len(videos) + int("audio" in prepared)
    media, done = {"images": [], "videos": []}, 0
    for index, data in enumerate(images, 1):
        media["images"].append(api.upload_media(data, f"kling4_image_{index}.png", "image/png", config))
        done += 1
        progress(done / max(count, 1))
    for index, (data, extension) in enumerate(videos, 1):
        name = f"kling4_video_{index}.{extension}"
        media["videos"].append(api.upload_media(data, name, mimetypes.guess_type(name)[0] or "application/octet-stream", config))
        done += 1
        progress(done / max(count, 1))
    media["videos"].extend(prepared.get("video_urls", []))
    if "audio" in prepared:
        media["audio_url"] = api.upload_media(prepared["audio"], "kling4_voice.wav", "audio/wav", config)
    elif "audio_url" in prepared:
        media["audio_url"] = prepared["audio_url"]
    progress(1)
    return media


def config_inputs():
    return {"api_config": (api.CONFIG_TYPE,), "skip_error": ("BOOLEAN", {"default": False}), "seed": EXECUTION_SEED_SPEC}


class _Kling4Base:
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    RETURN_TYPES = (api.VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price/Kling 4"
    OUTPUT_NODE = True

    @classmethod
    def values_with_defaults(cls, values, preflight=False):
        defaults = {name: spec[1]["default"] for group in cls.INPUT_TYPES().values() for name, spec in group.items()
                    if len(spec) > 1 and "default" in spec[1]}
        return {**defaults, **{name: value for name, value in values.items() if not (preflight and value is None and name in defaults)}}

    @classmethod
    def VALIDATE_INPUTS(cls, strict=False, **values):
        try:
            cls.validate(cls.values_with_defaults(values, preflight=not strict), strict)
        except Error as error:
            return str(error)
        return True

    def success_result(self, final, task_id, response):
        url = api.extract_legacy_video_url(final)
        if not http_url(url):
            raise Error("Kling 4 completed without a public final video URL")
        return (api.download_video(url), url, task_id, response)

    def error_result(self, message, response):
        return (api.make_error_video(message), "", "", response)

    def generate(self, api_config=None, skip_error=False, seed=0, **values):
        del seed
        try:
            values = self.values_with_defaults(values)
            self.validate(values, True)
            prepared = self.prepare_media(values)
            config = api.resolve_config(api_config)
            bar = api.comfy.utils.ProgressBar(100) if api.COMFYUI_AVAILABLE else None

            def progress(value):
                if bar is not None:
                    bar.update_absolute(int(value), 100)

            progress(0)
            media = upload_prepared(prepared, config, lambda value: progress(value * 20))
            payload = self.build_payload(values, media)
            task_id, submitted = submit_kling_task(payload, config)
            progress(25)
            final = poll_kling_task(task_id, config, on_progress=lambda value: progress(25 + value * .65))
            progress(95)
            response = json.dumps({"status": "SUCCESS", "model": payload["model"], "task_id": task_id,
                                   "submit": submitted, "result": final}, ensure_ascii=False, indent=2)
            result = self.success_result(final, task_id, response)
            progress(100)
            return result
        except Exception as error:
            if not skip_error:
                raise
            message = f"{type(error).__name__}: {error}"
            return self.error_result(message, json.dumps({"status": "error", "message": message}, ensure_ascii=False))


class _Kling4Video(_Kling4Base):
    KIND = "t2v"

    @classmethod
    def INPUT_TYPES(cls):
        required = {"prompt": ("STRING", {"default": "", "multiline": True,
                    "tooltip": "English/26000 + non-English/11000 <=1."}),
                    "seconds": ("INT", {"default": 3, "min": 3, "max": 30}),
                    "resolution": (RESOLUTIONS, {"default": "720p"})}
        if cls.KIND != "i2v":
            required["ratio"] = (RATIOS + (["adaptive"] if cls.KIND == "omni" else []), {"default": "16:9"})
        required["watermark"] = (WATERMARKS, {"default": "api_default"})
        optional = {}
        if cls.KIND != "t2v":
            optional.update({f"image{i}": ("IMAGE",) for i in range(1, 3 if cls.KIND == "i2v" else 11)})
        if cls.KIND == "omni":
            optional.update({f"video{i}": (api.VIDEO_TYPE,) for i in range(1, 6)})
            for name, tooltip in (
                ("video_urls", "Public URLs after local videos. At most 5 videos, 30 seconds combined, 300 MB each. API validates remote media."),
                ("image_element_ids", "Image-element IDs, one per line or JSON array; precede video-element IDs."),
                ("video_element_ids", "At most 3 video-element IDs; videos plus video elements <=5."),
                ("voice_ids", "At most 3 reusable voice IDs, one per line or a JSON array."),
            ):
                required[name] = ("STRING", {"default": "", "multiline": True, "tooltip": tooltip})
        return {"required": required, "optional": {**optional, **config_inputs()}}

    @classmethod
    def validate(cls, values, strict):
        validate_video(cls.KIND, values, strict)

    def prepare_media(self, values):
        images = [encode_image(values[f"image{i}"]) for i in range(1, 3 if self.KIND == "i2v" else 11)
                  if values.get(f"image{i}") is not None] if self.KIND != "t2v" else []
        videos, duration = [], 0
        if self.KIND == "omni":
            for i in range(1, 6):
                if values.get(f"video{i}") is not None:
                    data, extension = api.video_to_upload_bytes(values[f"video{i}"])
                    duration += validate_local_video(data, extension)["duration"]
                    videos.append((data, extension))
            if duration > 30:
                raise Error("Kling 4 Omni reference videos must total at most 30 seconds")
        return {"images": images, "videos": videos, "video_urls":
                string_list(values.get("video_urls", ""), "video_urls") if self.KIND == "omni" else []}

    @classmethod
    def build_payload(cls, values, media):
        return video_payload(cls.KIND, values, media)


class T8ZhenzhenKling4T2V(_Kling4Video):
    KIND = "t2v"


class T8ZhenzhenKling4I2V(_Kling4Video):
    KIND = "i2v"


class T8ZhenzhenKling4Omni(_Kling4Video):
    KIND = "omni"


class T8ZhenzhenKling4CustomElement(_Kling4Base):
    RETURN_TYPES = ("STRING",) * 5
    RETURN_NAMES = ("element_id", "voice_id", "trial_url", "task_id", "response")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "element_name": ("STRING", {"default": "", "tooltip": "1-20 characters."}),
            "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "Element description, 1-100 characters."}),
            "reference_type": (["image_refer", "video_refer"], {"default": "image_refer"}),
            "video_url": ("STRING", {"default": "", "tooltip": "MP4/MOV, 3-8 seconds, 1080p, 16:9 or 9:16, at most 200 MB. API validates URL media."}),
            "element_voice_id": ("STRING", {"default": ""}),
            "tag_list": ("STRING", {"default": "", "tooltip": "One per line or JSON string array: o_101 through o_108."}),
        }, "optional": {**{f"image{i}": ("IMAGE",) for i in range(1, 5)}, "input_video": (api.VIDEO_TYPE,), **config_inputs()}}

    @classmethod
    def validate(cls, values, strict):
        validate_element(values, strict)

    def prepare_media(self, values):
        if values["reference_type"] == "image_refer":
            images = [encode_image(values[f"image{i}"], element=True) for i in range(1, 5) if values.get(f"image{i}") is not None]
            if len(set(images)) != len(images):
                raise Error("Element references must show different views; duplicate images were provided")
            return {"images": images}
        if values.get("input_video") is not None:
            data, extension = api.video_to_upload_bytes(values["input_video"])
            validate_local_video(data, extension, element=True)
            return {"videos": [(data, extension)]}
        return {"video_urls": [values["video_url"].strip()]}

    build_payload = staticmethod(element_payload)

    def success_result(self, final, task_id, response):
        values = named_results(final)
        if not values.get("element_id"):
            raise Error("Kling 4 custom element completed without element_id")
        return (values["element_id"], values.get("voice_id", ""), values.get("trial_url", ""), task_id, response)

    def error_result(self, message, response):
        return ("", "", "", "", response)


class T8ZhenzhenKling4CustomVoice(_Kling4Base):
    RETURN_TYPES = ("STRING", "AUDIO", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("voice_id", "trial_audio", "trial_url", "task_id", "response")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "voice_name": ("STRING", {"default": ""}),
            "source_mode": (["audio", "video_id"], {"default": "audio"}),
            "audio_url": ("STRING", {"default": "", "tooltip": "Public audio URL, at most 10 MB; leave empty for local AUDIO."}),
            "video_id": ("STRING", {"default": "", "tooltip": "Provider videoId, not the generic task_id."}),
        }, "optional": {"audio": ("AUDIO",), **config_inputs()}}

    @classmethod
    def validate(cls, values, strict):
        validate_voice(values, strict)

    def prepare_media(self, values):
        if values["source_mode"] == "video_id":
            return {}
        if values.get("audio") is None:
            return {"audio_url": values["audio_url"].strip()}
        audio = values["audio"]
        waveform = audio.get("waveform") if isinstance(audio, dict) else None
        shape = getattr(waveform, "shape", ())
        rate = audio.get("sample_rate") if isinstance(audio, dict) else None
        if len(shape) != 3 or shape[0] != 1 or min(shape[1:]) <= 0 or type(rate) is not int or rate <= 0:
            raise Error("Kling 4 requires one non-empty AUDIO sample with a positive sample rate")
        array = waveform.detach().cpu().numpy() if hasattr(waveform, "detach") else api.np.asarray(waveform)
        if not api.np.isfinite(array).all():
            raise Error("Kling 4 voice sample contains NaN or infinity")
        data = api.audio_to_wav_bytes(audio)
        if len(data) > 10 * 1024 * 1024:
            raise Error("Kling 4 voice sample must not exceed 10 MB")
        return {"audio": data}

    @staticmethod
    def build_payload(values, media):
        validate_voice(values)
        if not values.get("voice_name", "").strip():
            raise Error("Kling 4 voice_name is required")
        metadata = {"voiceName": values["voice_name"].strip()}
        if values.get("source_mode", "audio") == "video_id":
            if not values.get("video_id", "").strip():
                raise Error("Kling 4 provider videoId is required")
            metadata["videoId"] = values["video_id"].strip()
        else:
            if not media.get("audio_url"):
                raise Error("Kling 4 voice requires one audio source")
            metadata["audio_url"] = media["audio_url"]
        return {"model": "kling-v4-custom-voice", "metadata": metadata}

    def success_result(self, final, task_id, response):
        values = named_results(final)
        if not values.get("voice_id"):
            raise Error("Kling 4 custom voice completed without voice_id")
        url = values.get("trial_url", "")
        if url and not http_url(url):
            raise Error("Kling 4 trial_url is not a public HTTP(S) link")
        audio = api.download_audio(url, "mp3", 16000) if url else api.make_silent_audio()
        return (values["voice_id"], audio, url, task_id, response)

    def error_result(self, message, response):
        return ("", api.make_silent_audio(), "", "", response)
