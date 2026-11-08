"""Static GPT Image 2.6 models on the Zhenzhen AI Workshop channel."""

import base64
import io
import json
import time

import numpy as np
from PIL import Image
import torch

try:
    from . import gpt_image_25_nodes as legacy
    from .execution_seed import EXECUTION_SEED_SPEC
    from .media_download import download_image_with_alpha_retry
except ImportError:
    import gpt_image_25_nodes as legacy
    from execution_seed import EXECUTION_SEED_SPEC
    from media_download import download_image_with_alpha_retry


MODELS = tuple(f"gpt-image-2.6-{variant}{suffix}" for variant in ("flare", "sunburst") for suffix in ("", "-2k", "-4k"))
QUALITIES = ("auto", "low", "medium", "high", "xhigh", "max")
SIZES = ("auto", "1024x1024", "1536x1024", "1024x1536", "2048x2048", "2048x1152", "1152x2048", "2880x2880", "3840x2160", "2160x3840", "custom")
MAX_IMAGES = 16
MAX_FILE_BYTES = 50 * 1024 * 1024
requests = legacy.requests


class GPTImage26Error(RuntimeError):
    pass


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def resolved_size(values, strict=False):
    size = values.get("size", "1024x1024")
    if size == "auto":
        return size
    if size == "custom":
        width, height = values.get("custom_width"), values.get("custom_height")
        if not strict and (width is None or height is None):
            for value in (width, height):
                if value is not None and (not integer(value, 16, 3840) or value % 16):
                    raise GPTImage26Error("Custom dimensions must be multiples of 16, at most 3840")
            return None
        if not integer(width, 16, 3840) or not integer(height, 16, 3840):
            raise GPTImage26Error("Custom dimensions must be integers from 16 to 3840")
        size = f"{width}x{height}"
    if not isinstance(size, str):
        raise GPTImage26Error("size must be auto or WIDTHxHEIGHT")
    try:
        legacy.validate_gpt_image_25_size(size)
    except legacy.GPTImage25Error as error:
        raise GPTImage26Error(str(error)) from None
    return size


def collect_frames(values):
    frames = []
    for name, value in values.items():
        if name.startswith("image") and name[5:].isdigit() and value is not None and not 1 <= int(name[5:]) <= MAX_IMAGES:
            raise GPTImage26Error(f"At most {MAX_IMAGES} reference images are supported")
    for index in range(1, MAX_IMAGES + 1):
        frames.extend(legacy._iter_image_frames(values.get(f"image{index}")))
        if len(frames) > MAX_IMAGES:
            raise GPTImage26Error(f"At most {MAX_IMAGES} reference images are supported, including batches")
    return frames


def validate(values, strict=False):
    prompt = values.get("prompt")
    if prompt is not None or strict:
        if not isinstance(prompt, str) or not prompt.strip():
            raise GPTImage26Error("A non-empty prompt is required")
        if len(prompt.strip()) > 32000:
            raise GPTImage26Error("prompt must not exceed 32000 characters")
    if values.get("model", MODELS[0]) not in MODELS:
        raise GPTImage26Error("Unsupported GPT Image 2.6 Workshop model")
    for field, choices, default in (("quality", QUALITIES, "auto"), ("background", ("auto", "opaque", "transparent"), "auto"),
        ("moderation", ("auto", "low"), "auto"), ("output_format", ("png", "jpeg", "webp"), "png"),
        ("complexity", ("api_default", "low", "medium", "high"), "api_default")):
        if values.get(field, default) not in choices:
            raise GPTImage26Error(f"Unsupported {field}")
    if values.get("background") == "transparent" and values.get("output_format", "png") == "jpeg":
        raise GPTImage26Error("Transparent output requires PNG or WebP")
    for field, low, high, default in (("n", 1, 10, 1), ("output_compression", -1, 100, -1),
        ("poll_interval", 2, 60, 5), ("max_poll_time", 60, 7200, 3600)):
        if not integer(values.get(field, default), low, high):
            raise GPTImage26Error(f"{field} must be an integer from {low} to {high}")
    if type(values.get("async_mode", True)) is not bool:
        raise GPTImage26Error("async_mode must be a boolean")
    resolved_size(values, strict)
    has_mask, has_markup = values.get("mask") is not None, values.get("markup") is not None
    if has_mask and has_markup:
        raise GPTImage26Error("mask and markup are mutually exclusive")
    if strict:
        frames = collect_frames(values)
        if (has_mask or has_markup) and not frames:
            raise GPTImage26Error("mask/markup requires a first reference image")
        if frames and values.get("output_format", "png") in ("jpeg", "webp") and values.get("output_compression", -1) >= 0:
            raise GPTImage26Error("Workshop image edits currently require output_compression=-1 (API default)")


def payload(values):
    validate(values, strict=True)
    result = {"model": values.get("model", MODELS[0]), "prompt": values["prompt"].strip(),
        "quality": values.get("quality", "auto"), "size": resolved_size(values, True), "n": values.get("n", 1),
        "background": values.get("background", "auto"), "moderation": values.get("moderation", "auto"),
        "output_format": values.get("output_format", "png")}
    if values.get("complexity", "api_default") != "api_default":
        result["complexity"] = values["complexity"]
    if result["output_format"] in ("jpeg", "webp") and values.get("output_compression", -1) >= 0:
        result["output_compression"] = values["output_compression"]
    return result


def prepare_files(values):
    frames = collect_frames(values)
    files, first_size = [], None
    for index, frame in enumerate(frames, 1):
        if not torch.isfinite(frame).all():
            raise GPTImage26Error("Reference images must not contain NaN or infinity")
        raw, size = legacy._frame_to_png(frame)
        if len(raw) > MAX_FILE_BYTES:
            raise GPTImage26Error("Reference image exceeds 50 MiB")
        if first_size is None:
            first_size = size
        files.append(("image[]" if len(frames) > 1 else "image", (f"reference_{index}.png", raw, "image/png")))
    if values.get("mask") is not None:
        if not torch.isfinite(values["mask"]).all():
            raise GPTImage26Error("Mask contains NaN or infinity")
        raw = legacy._mask_to_png(values["mask"], first_size)
        if len(raw) > MAX_FILE_BYTES:
            raise GPTImage26Error("Mask exceeds 50 MiB")
        files.append(("mask", ("mask.png", raw, "image/png")))
    if values.get("markup") is not None:
        markup = values["markup"]
        if not torch.is_tensor(markup) or markup.ndim != 4 or markup.shape[0] != 1 or markup.shape[-1] != 4:
            raise GPTImage26Error("markup must be one RGBA IMAGE with transparent pixels")
        if not torch.isfinite(markup).all() or not (markup[..., 3] < 1).any():
            raise GPTImage26Error("markup must contain finite values and transparent pixels")
        if (markup.shape[2], markup.shape[1]) != first_size or markup.shape[1] * markup.shape[2] > 16777216:
            raise GPTImage26Error("markup must match the first image and contain at most 16777216 pixels")
        raw, _ = legacy._frame_to_png(markup)
        if len(raw) > MAX_FILE_BYTES:
            raise GPTImage26Error("markup exceeds 50 MiB")
        files.append(("markup", ("markup.png", raw, "image/png")))
    return files


def response_json(response):
    try:
        body = response.json()
    except ValueError:
        raise GPTImage26Error(f"GPT Image 2.6 returned non-JSON data (HTTP {response.status_code})") from None
    if not 200 <= response.status_code < 300:
        error = body.get("error") if isinstance(body, dict) else None
        reason = error.get("message") if isinstance(error, dict) else body.get("message") if isinstance(body, dict) else "request rejected"
        raise GPTImage26Error(f"GPT Image 2.6 request rejected (HTTP {response.status_code}): {reason}")
    if not isinstance(body, dict):
        raise GPTImage26Error("GPT Image 2.6 returned an invalid response object")
    return body


def submit(key, data, files, async_mode=True):
    endpoint = "edits" if files else "generations"
    url = f"{legacy.PRIMARY_BASE_URL}/v1/images/{endpoint}" + ("?async=true" if async_mode else "")
    # URL responses and async=true are Workshop transport extensions, not OpenAI parameters.
    request = {**data, "response_format": "url"}
    headers = {"Authorization": f"Bearer {key}"}
    try:
        if files:
            response = requests.post(url, headers=headers, data={name: str(value) for name, value in request.items()},
                files=files, timeout=legacy.GPT_IMAGE_25_ENDPOINT_TIMEOUT)
        else:
            response = requests.post(url, headers={**headers, "Content-Type": "application/json"}, json=request,
                timeout=legacy.GPT_IMAGE_25_ENDPOINT_TIMEOUT)
    except requests.RequestException as error:
        raise GPTImage26Error(f"Submission could not be confirmed ({type(error).__name__}); not retried. Check the website task list.") from None
    try:
        try:
            result = response_json(response)
        except GPTImage26Error:
            # The gateway can append a size suffix twice before rejecting routing.
            model = data["model"]
            suffix = next((value for value in ("-2k", "-4k") if model.endswith(value)), "")
            if files or response.status_code != 503 or not suffix:
                raise
            body = response.json()
            if not isinstance(body, dict):
                raise
            error = body.get("error", {})
            message = str(error.get("message", "")) if isinstance(error, dict) else ""
            has_task = any(body.get(name) for name in ("id", "task_id", "taskId")) or legacy._extract_task_id(body.get("data", {}))
            rejected_route = model + suffix in message and ("\u65e0\u53ef\u7528\u6e20\u9053" in message or "no available channel" in message.lower())
            if not rejected_route or has_task or legacy._find_image_result(body) is not None:
                raise
            response.close()
            canonical = model[:-len(suffix)]
            result = submit(key, {**data, "model": canonical}, files, async_mode)
            result["_zhenzhen_wire_model"] = canonical
        return result
    finally:
        response.close()


def poll(key, identifier, interval, maximum, progress=None, sleep=time.sleep, clock=time.monotonic):
    start, failures = clock(), 0
    while clock() - start < maximum:
        sleep(interval)
        response = None
        try:
            response = requests.get(f"{legacy.PRIMARY_BASE_URL}/v1/images/tasks/{identifier}",
                headers={"Authorization": f"Bearer {key}"}, timeout=legacy.GPT_IMAGE_25_POLL_REQUEST_TIMEOUT)
            if response.status_code in (408, 429) or response.status_code >= 500:
                raise requests.RequestException("Transient task query failure")
            body = response_json(response)
            record = body.get("data") if isinstance(body.get("data"), dict) else body
            status = str(record.get("status", "")).strip().upper()
            completed = legacy._find_image_result(body)
            if not status and completed is None:
                raise requests.RequestException("Task query has no status or image data")
        except (requests.RequestException, GPTImage26Error):
            if response is not None and 400 <= response.status_code < 500 and response.status_code not in (408, 429):
                raise
            failures += 1
            if failures >= 8:
                raise GPTImage26Error("Task queries repeatedly failed; no new generation was submitted") from None
            continue
        finally:
            if response is not None:
                response.close()
        failures = 0
        if progress:
            try:
                progress(min(94, 20 + float(str(record.get("progress", "0")).rstrip("%")) * .74))
            except (ValueError, TypeError):
                pass
        if completed is not None and status in ("", "SUCCESS", "COMPLETED", "SUCCEEDED"):
            return completed
        if status in ("FAILURE", "FAILED", "ERROR", "CANCELLED", "CANCELED"):
            raise GPTImage26Error(f"GPT Image 2.6 task {status}: {record.get('fail_reason') or record.get('message') or 'generation failed'}")
    raise GPTImage26Error("Task polling timed out; the original task may still be running")


def decode_result(result):
    items = result.get("data")
    if not isinstance(items, list) or not items:
        raise GPTImage26Error("GPT Image 2.6 response contains no images")
    images, masks, urls = [], [], []
    for item in items:
        if not isinstance(item, dict):
            raise GPTImage26Error("Invalid image result item")
        encoded, url = item.get("b64_json"), item.get("url")
        if encoded:
            if not isinstance(encoded, str):
                raise GPTImage26Error("Invalid base64 image data")
            raw = base64.b64decode(encoded.split(",", 1)[-1] if encoded.startswith("data:image") else encoded, validate=True)
            with Image.open(io.BytesIO(raw)) as source:
                source.load()
                decoded = source.convert("RGBA")
        elif isinstance(url, str) and url.strip():
            decoded = download_image_with_alpha_retry(url, timeout=300, max_attempts=5)
            urls.append(url)
        else:
            raise GPTImage26Error("Result contains neither base64 nor an image URL")
        array = np.asarray(decoded.convert("RGBA"), dtype=np.float32).copy() / 255
        images.append(torch.from_numpy(array[..., :3]).unsqueeze(0))
        masks.append(torch.from_numpy(1 - array[..., 3]).unsqueeze(0))
    if len({tuple(value.shape[1:]) for value in images}) != 1:
        raise GPTImage26Error("Result dimensions differ and cannot form one IMAGE batch")
    return torch.cat(images), urls, torch.cat(masks)


class T8ZhenzhenGPTImage26Workshop:
    CATEGORY = "zhenzhen/OpenAI"
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "MASK")
    RETURN_NAMES = ("image", "image_urls", "response", "mask")
    FUNCTION = "generate"
    OUTPUT_NODE = True
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    ZHENZHEN_VALIDATE_CONCURRENT_AT_EXECUTION = True

    @classmethod
    def INPUT_TYPES(cls):
        optional = {f"image{i}": ("IMAGE",) for i in range(1, MAX_IMAGES + 1)}
        optional.update(mask=("MASK",), markup=("IMAGE",), api_key=("STRING", {"default": ""}),
            model=(list(MODELS), {"default": MODELS[0]}), quality=(list(QUALITIES), {"default": "auto"}),
            size=(list(SIZES), {"default": "1024x1024"}),
            custom_width=("INT", {"default": 1024, "min": 16, "max": 3840, "step": 16}),
            custom_height=("INT", {"default": 1024, "min": 16, "max": 3840, "step": 16}),
            n=("INT", {"default": 1, "min": 1, "max": 10}),
            background=(["auto", "opaque", "transparent"], {"default": "auto"}),
            moderation=(["auto", "low"], {"default": "auto"}),
            output_format=(["png", "jpeg", "webp"], {"default": "png"}),
            output_compression=("INT", {"default": -1, "min": -1, "max": 100}),
            complexity=(["api_default", "low", "medium", "high"], {"default": "api_default"}),
            skip_error=("BOOLEAN", {"default": False}), seed=EXECUTION_SEED_SPEC,
            async_mode=("BOOLEAN", {"default": True}), poll_interval=("INT", {"default": 5, "min": 2, "max": 60}),
            max_poll_time=("INT", {"default": 3600, "min": 60, "max": 7200, "step": 60}))
        return {"required": {"prompt": ("STRING", {"default": "", "multiline": True})}, "optional": optional}

    @classmethod
    def VALIDATE_INPUTS(cls, strict=False, **values):
        try:
            validate(values if strict else {key: value for key, value in values.items() if value is not None}, strict)
        except Exception as error:
            return str(error)
        return True

    def generate(self, prompt, api_key="", skip_error=False, seed=0, **values):
        del seed
        try:
            key = api_key.strip() if isinstance(api_key, str) else ""
            if not key:
                raise GPTImage26Error("API key is empty; enter a Workshop key in this workflow or connect its Settings apikey output")
            values = {"prompt": prompt, **values}
            for group in self.INPUT_TYPES().values():
                for name, spec in group.items():
                    if len(spec) > 1 and "default" in spec[1]:
                        values.setdefault(name, spec[1]["default"])
            validate(values, strict=True)
            request, files = payload(values), prepare_files(values)
            bar = legacy.comfy.utils.ProgressBar(100) if legacy.COMFYUI_AVAILABLE else None
            progress = (lambda value: bar.update_absolute(int(value), 100)) if bar else None
            result = submit(key, request, files, values["async_mode"])
            wire_model = result.get("_zhenzhen_wire_model", values["model"])
            completed, identifier = legacy._find_image_result(result), ""
            if completed is None and values["async_mode"]:
                identifier = legacy._extract_task_id(result)
                if not identifier:
                    raise GPTImage26Error("Submission has no task ID or images; not retried. Check the website task list.")
                completed = poll(key, identifier, values["poll_interval"], values["max_poll_time"], progress)
            images, urls, masks = decode_result(completed if completed is not None else result)
            if progress:
                progress(100)
            mode = ("image_edit" if files else "text_to_image") + ("_async" if values["async_mode"] else "")
            safe = json.loads(legacy._safe_response_json(completed or result, mode, identifier))
            safe.update(selected_model=values["model"], wire_model=wire_model)
            return images, "\n".join(urls), json.dumps(safe, ensure_ascii=False, indent=2), masks
        except Exception as error:
            if not skip_error:
                raise
            return (torch.ones(1, 512, 512, 3), "", json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False), torch.zeros(1, 512, 512))
