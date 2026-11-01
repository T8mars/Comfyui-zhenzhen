"""HY Preview, Muse and the four independent FLUX 3 image variants."""

from io import BytesIO
import json
import time

try:
    from . import seedance_low_price_nodes as api
    from .execution_seed import EXECUTION_SEED_SPEC
except ImportError:
    import seedance_low_price_nodes as api
    from execution_seed import EXECUTION_SEED_SPEC


HY_MODEL = "zhenzhen-image-hy-v3.5-preview"
MUSE_IMAGE = "zhenzhen-image-muse"
MUSE_VIDEO = "zhenzhen-video-muse"
HY_SIZES = ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9", "custom"]
HY_RESOLUTIONS = ["1K", "2K", "4K"]
MUSE_SIZES = ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"]
MUSE_REFERENCE_BYTES = 11 * 1024 * 1024
FLUX_MODELS = ["flux-3-image-t2i", "flux-3-image-i2i", "flux-3-image-klein-t2i", "flux-3-image-klein-i2i"]
FLUX_RESOLUTIONS = ["768sq", "1k", "1.5k", "2k", "4k"]
FLUX_RATIOS = ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "2:1", "1:2", "21:9", "9:21", "5:7", "7:5"]
NATIVE_SEED = {"default": 0, "min": 0, "max": 9007199254740991, "step": 1, "control_after_generate": True}
Error = api.SeedanceLowPriceError


def references(values, maximum):
    result = []
    for name, value in values.items():
        if not name.startswith("image") or not name[5:].isdigit() or value is None:
            continue
        index = int(name[5:])
        if not 1 <= index <= maximum:
            raise Error(f"At most {maximum} reference images are supported")
        result.append((index, value))
    return sorted(result)


def image_bytes(image):
    shape = getattr(image, "shape", ())
    if len(shape) != 4 or shape[0] != 1 or min(shape[1:3]) < 1 or shape[-1] not in (3, 4):
        raise Error("Each reference socket requires exactly one non-empty RGB/RGBA IMAGE, not a batch")
    array = image.detach().cpu().numpy() if hasattr(image, "detach") else api.np.asarray(image)
    if not api.np.isfinite(array).all():
        raise Error("Reference images must not contain NaN or infinity")
    if api.np.issubdtype(array.dtype, api.np.floating):
        array = api.np.clip(array, 0, 1) * 255
    stream = BytesIO()
    api.Image.fromarray(array[0].astype(api.np.uint8)).save(stream, format="PNG")
    return stream.getvalue()


def encode_references(values, maximum, per_file=50 * 1024 * 1024, total=None):
    encoded = [(index, image_bytes(image)) for index, image in references(values, maximum)]
    if any(len(data) > per_file for _, data in encoded):
        raise Error("Reference image exceeds the file size limit")
    if total is not None and sum(len(data) for _, data in encoded) > total:
        raise Error("Muse reference images must total at most 11 MiB")
    return encoded


def integer(value, minimum, maximum=None):
    return type(value) is int and value >= minimum and (maximum is None or value <= maximum)


def validate(kind, values, strict=False, require_connections=True):
    prompt = values.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        return "prompt must be text"
    if strict and not (prompt or "").strip():
        return "A non-empty prompt is required"
    try:
        refs = references(values, 5 if kind == "hy" else 10 if kind == "flux" else 9)
    except Error as error:
        return str(error)
    if kind != "flux":
        size = values.get("size", "auto")
        if size not in (HY_SIZES if kind == "hy" else MUSE_SIZES) and (strict or size is not None):
            return "Unsupported size"
        if kind != "hy":
            return True
        resolution = values.get("resolution", "1K")
        if not (resolution is None and not strict) and (not isinstance(resolution, str) or resolution.upper() not in HY_RESOLUTIONS):
            return "HY resolution must be 1K, 2K or 4K"
        if size == "custom":
            width = values.get("width", 1024 if strict else None)
            height = values.get("height", 1024 if strict else None)
            if any(not integer(value, 256, 8192) for value in (width, height) if strict or value is not None):
                return "HY width and height must be integers from 256 to 8192"
            if width is not None and height is not None and width * height > 8294400:
                return "HY custom dimensions must not exceed 8,294,400 pixels"
        negative = values.get("negative_prompt", "")
        if not isinstance(negative, str) and (strict or negative is not None):
            return "negative_prompt must be text"
        seed = values.get("seed", 0)
        if not integer(seed, 0) and (strict or seed is not None):
            return "HY seed must be a nonnegative integer"
        return True
    model = values.get("model", FLUX_MODELS[0])
    if model is None and not strict:
        return True
    if model not in FLUX_MODELS:
        return "Unsupported FLUX 3 Image variant"
    for name, choices, default in (("resolution", FLUX_RESOLUTIONS, "1k"), ("aspect_ratio", FLUX_RATIOS, "auto")):
        value = values.get(name, default)
        if value not in choices and (strict or value is not None):
            return f"Unsupported FLUX {name}"
    safety = values.get("safety_tolerance", 2)
    if not integer(safety, 0, 4) and (strict or safety is not None):
        return "safety_tolerance must be an integer from 0 to 4"
    if "-klein-" in model:
        for name, maximum in (("seed", 2147483647), ("steps", 16)):
            value = values.get(name, 0)
            if not integer(value, 0, maximum) and (strict or value is not None):
                return f"Klein {name} must be an integer from 0 to {maximum}"
        output = values.get("output_format", "api_default")
        if output not in ("api_default", "jpeg", "png") and (strict or output is not None):
            return "Klein output_format must be api_default, jpeg or png"
    else:
        grounding = values.get("grounding", True)
        if not isinstance(grounding, bool) and (strict or grounding is not None):
            return "grounding must be a boolean"
    if model.endswith("-t2i") and refs:
        return "FLUX T2I does not accept connected images"
    if strict and require_connections and model.endswith("-i2i") and not refs:
        return "FLUX I2I requires at least one reference image"
    return True


def build_payload(kind, values, images):
    valid = validate(kind, values, strict=True, require_connections=False)
    if valid is not True:
        raise Error(valid)
    if not isinstance(images, (list, tuple)) or any(not isinstance(url, str) or not url.strip() for url in images):
        raise Error("images must be an array of uploaded image URLs")
    maximum = 5 if kind == "hy" else 10 if kind == "flux" else 9
    if len(images) > maximum:
        raise Error(f"At most {maximum} reference images are supported")
    prompt = values["prompt"].strip()
    if kind == "flux":
        model = values.get("model", FLUX_MODELS[0])
        if model.endswith("-i2i") and not images:
            raise Error("FLUX I2I requires 1-10 uploaded images")
        if model.endswith("-t2i") and images:
            raise Error("FLUX T2I does not accept uploaded images")
        # Unlike the legacy FLUX model, these four variants explicitly reject n.
        result = {"model": model, "prompt": prompt, "resolution": values.get("resolution", "1k"),
                  "aspect_ratio": values.get("aspect_ratio", "auto"), "safety_tolerance": values.get("safety_tolerance", 2)}
        if "-klein-" in model:
            result["seed"] = values.get("seed", 0)
            if values.get("steps", 0):
                result["metadata"] = {"steps": values["steps"]}
            if values.get("output_format", "api_default") != "api_default":
                result["output_format"] = values["output_format"]
        else:
            result["grounding"] = values.get("grounding", True)
    else:
        result = {"model": {"hy": HY_MODEL, "muse_image": MUSE_IMAGE, "muse_video": MUSE_VIDEO}[kind], "prompt": prompt, "n": 1}
        if kind == "hy":
            result.update(resolution=values.get("resolution", "1K").upper(), seed=values.get("seed", 0))
            if values.get("size", "auto") == "custom":
                result.update(width=values.get("width", 1024), height=values.get("height", 1024))
            else:
                result["size"] = values.get("size", "auto")
            if values.get("negative_prompt", "").strip():
                result["negative_prompt"] = values["negative_prompt"].strip()
        else:
            result["size"] = values.get("size", "auto")
            if kind == "muse_video":
                result.update(duration=10, resolution="720p", audio=True)
    if images:
        result["images"] = list(images)
    return result


def submit_request(payload, config, video=False):
    endpoint = "video" if video else "image"
    try:
        response = api._get_session().post(f"{config['base_url']}/v1/{endpoint}/generations",
            headers=api._headers(config["api_key"]), json=payload, timeout=config.get("timeout", 60))
    except api.requests.RequestException as error:
        raise Error(f"Submission could not be confirmed ({type(error).__name__}); not retried. Check the website task list.") from None
    try:
        data = api._response_json(response)
        if not 200 <= response.status_code < 300:
            raise Error(f"Submit rejected (HTTP {response.status_code}): {api.extract_error_message(data, 'request rejected')}; not retried")
        task = data.get("data") if isinstance(data, dict) else None
        task_id = (data.get("id") or data.get("task_id")) if isinstance(data, dict) else None
        if not task_id and isinstance(task, dict):
            task_id = task.get("id") or task.get("task_id")
        if not task_id:
            raise Error("Submit response has no task ID; not retried. Check the website task list.")
        return str(task_id), data
    finally:
        response.close()


def poll_request(task_id, config, video=False, on_progress=None, sleep=time.sleep, clock=time.monotonic):
    endpoint, started, failures = "video" if video else "image", clock(), 0
    while True:
        if clock() - started >= config.get("max_poll_time", 1800):
            raise Error("Polling timed out; the upstream task may still be running")
        sleep(config.get("poll_interval", 4))
        response = None
        try:
            response = api._get_session().get(f"{config['base_url']}/v1/{endpoint}/generations/{task_id}",
                headers=api._headers(config["api_key"], json_content=False), timeout=30)
            if response.status_code != 200:
                if 400 <= response.status_code < 500 and response.status_code not in (408, 429):
                    raise Error(f"Polling rejected (HTTP {response.status_code})")
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
                raise Error("Polling repeatedly failed; no new task was submitted") from None
            sleep(min(failures * 2, 10))
            continue
        finally:
            if response is not None:
                response.close()
        failures = 0
        progress = api._coerce_progress(record.get("progress"))
        if on_progress and progress is not None:
            on_progress(progress)
        status = record["status"].strip().upper()
        if status in {"SUCCESS", "SUCCEEDED", "COMPLETED"}:
            return data
        if status in {"FAILURE", "FAILED", "CANCELED", "CANCELLED"}:
            raise Error(f"Task failed: {record.get('fail_reason') or api.extract_error_message(record, 'generation failed')}")


class _Generation:
    KIND = "hy"
    MAX_IMAGES = 5
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        optional = {f"image{i}": ("IMAGE",) for i in range(1, cls.MAX_IMAGES + 1)}
        optional.update(api_config=(api.CONFIG_TYPE,), skip_error=("BOOLEAN", {"default": False}))
        if cls.KIND.startswith("muse"):
            optional["seed"] = EXECUTION_SEED_SPEC
        return {"required": cls.controls(), "optional": optional}

    @classmethod
    def VALIDATE_INPUTS(cls, strict=False, **values):
        return validate(cls.KIND, values, strict)

    @classmethod
    def build_payload(cls, values, images):
        return build_payload(cls.KIND, values, images)

    def generate(self, api_config=None, skip_error=False, **values):
        video = self.KIND == "muse_video"
        try:
            valid = self.VALIDATE_INPUTS(strict=True, **values)
            if valid is not True:
                raise Error(valid)
            encoded = encode_references(values, self.MAX_IMAGES, per_file=(10 if self.KIND == "flux" else 50) * 1024 * 1024,
                                        total=MUSE_REFERENCE_BYTES if self.KIND.startswith("muse") else None)
            config = api.resolve_config(api_config)
            bar = api.comfy.utils.ProgressBar(100) if api.COMFYUI_AVAILABLE else None

            def progress(value):
                if bar is not None:
                    bar.update_absolute(int(value), 100)

            progress(0)
            images = []
            for index, data in encoded:
                images.append(api.upload_media(data, f"reference_{index}.png", "image/png", config))
                progress(len(images) / len(encoded) * 15)
            payload = self.build_payload(values, images)
            task_id, submitted = submit_request(payload, config, video)
            progress(20)
            final = poll_request(task_id, config, video, on_progress=lambda value: progress(20 + value * .75))
            progress(95)
            if video:
                url = api.extract_legacy_video_url(final)
                media = api.download_video(url)
            else:
                try:
                    url = api.extract_image_url(final)
                except Error:
                    url = api.extract_image_urls(final)[0]
                media = api.download_image(url)
            response = json.dumps({"status": "SUCCESS", "model": payload["model"], "task_id": task_id,
                                   "submit": submitted, "result": final}, ensure_ascii=False, indent=2)
            progress(100)
            return media, url, task_id, response
        except Exception as error:
            if not skip_error:
                raise
            message = f"{type(error).__name__}: {error}"
            placeholder = api.make_error_video(message) if video else api.torch.ones((1, 512, 512, 3))
            return placeholder, "", "", json.dumps({"status": "error", "message": message}, ensure_ascii=False)


class T8ZhenzhenHY35Preview(_Generation):
    @classmethod
    def controls(cls):
        return {"prompt": ("STRING", {"default": "", "multiline": True}),
                "size": (HY_SIZES, {"default": "auto"}), "resolution": (HY_RESOLUTIONS, {"default": "1K"}),
                "width": ("INT", {"default": 1024, "min": 256, "max": 8192, "step": 1}),
                "height": ("INT", {"default": 1024, "min": 256, "max": 8192, "step": 1}),
                "negative_prompt": ("STRING", {"default": "", "multiline": True}),
                "seed": ("INT", {**NATIVE_SEED, "tooltip": "Native API seed; 0 requests a random result when execution is needed."})}


class T8ZhenzhenMuseImage(_Generation):
    KIND, MAX_IMAGES = "muse_image", 9
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True

    @classmethod
    def controls(cls):
        return {"prompt": ("STRING", {"default": "", "multiline": True}), "size": (MUSE_SIZES, {"default": "auto"})}


class T8ZhenzhenMuseVideo(T8ZhenzhenMuseImage):
    KIND = "muse_video"
    RETURN_TYPES = (api.VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")


class T8ZhenzhenFlux3ImageVariants(_Generation):
    KIND, MAX_IMAGES = "flux", 10

    @classmethod
    def controls(cls):
        return {"model": (FLUX_MODELS, {"default": FLUX_MODELS[0]}),
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "resolution": (FLUX_RESOLUTIONS, {"default": "1k"}), "aspect_ratio": (FLUX_RATIOS, {"default": "auto"}),
                "grounding": ("BOOLEAN", {"default": True}), "safety_tolerance": ("INT", {"default": 2, "min": 0, "max": 4}),
                "steps": ("INT", {"default": 0, "min": 0, "max": 16, "tooltip": "Klein only; 0 uses the API default."}),
                "output_format": (["api_default", "jpeg", "png"], {"default": "api_default"}),
                "seed": ("INT", {**NATIVE_SEED, "max": 2147483647, "tooltip": "Klein: native API seed. Standard: ComfyUI cache only."})}
