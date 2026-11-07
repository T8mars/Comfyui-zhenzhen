"""Independent Image G 2.6/GIF, Krea, Z-image and Hitem/Meshy nodes."""

import json
import time

try:
    from . import seedance_low_price_nodes as api
    from . import image_models_26_contracts as image_contract
    from . import hitem_meshy_contracts as geometry_contract
    from . import image_artifacts as artifacts
    from . import preview_muse_flux_low_price_nodes as common
    from .execution_seed import EXECUTION_SEED_SPEC
    from .aug22_low_price_nodes import File3D, placeholder_file3d, extract_3d_url
except ImportError:
    import seedance_low_price_nodes as api
    import image_models_26_contracts as image_contract
    import hitem_meshy_contracts as geometry_contract
    import image_artifacts as artifacts
    import preview_muse_flux_low_price_nodes as common
    from execution_seed import EXECUTION_SEED_SPEC
    from aug22_low_price_nodes import File3D, placeholder_file3d, extract_3d_url


Error = api.SeedanceLowPriceError


def submit_3d(payload, config):
    try:
        response = api._get_session().post(f"{config['base_url']}/v1/3d/generations",
            headers=api._headers(config["api_key"]), json=payload, timeout=config.get("timeout", 60))
    except api.requests.RequestException as error:
        raise Error(f"3D submission could not be confirmed ({type(error).__name__}); not retried. Check the website task list.") from None
    try:
        data = api._response_json(response)
        if not 200 <= response.status_code < 300:
            raise Error(f"3D submit rejected (HTTP {response.status_code}): {api.extract_error_message(data, 'rejected')}; not retried")
        record = data.get("data") if isinstance(data, dict) else None
        identifier = (data.get("id") or data.get("task_id")) if isinstance(data, dict) else None
        if not identifier and isinstance(record, dict):
            identifier = record.get("id") or record.get("task_id")
        if not identifier:
            raise Error("3D submission has no task ID; not retried. Check the website task list.")
        return str(identifier), data
    finally:
        response.close()


def poll_3d(identifier, config, sleep=time.sleep, clock=time.monotonic):
    start, failures = clock(), 0
    while clock() - start < config.get("max_poll_time", 2400):
        sleep(config.get("poll_interval", 4))
        response = None
        try:
            response = api._get_session().get(f"{config['base_url']}/v1/3d/generations/{identifier}",
                headers=api._headers(config["api_key"], json_content=False), timeout=30)
            if response.status_code != 200:
                if 400 <= response.status_code < 500 and response.status_code not in (408, 429):
                    raise Error(f"3D polling rejected (HTTP {response.status_code})")
                raise api.requests.RequestException("Transient 3D task query failure")
            data = api._response_json(response)
            record = data.get("data") if isinstance(data, dict) else None
            if not isinstance(record, dict) or "status" not in record:
                record = data
            status = record.get("status") if isinstance(record, dict) else None
            if not isinstance(status, str) or not status.strip():
                raise api.requests.RequestException("Missing 3D task status")
        except api.requests.RequestException:
            failures += 1
            if failures >= 6:
                raise Error("3D polling repeatedly failed; no new task was submitted") from None
            continue
        finally:
            if response is not None:
                response.close()
        failures = 0
        if status.strip().upper() in {"SUCCESS", "SUCCEEDED", "COMPLETED"}:
            return data
        if status.strip().upper() in {"FAILURE", "FAILED", "CANCELED", "CANCELLED"}:
            raise Error(api.extract_error_message(record, "3D generation failed"))
    raise Error("3D polling timed out; the upstream task may still be running")


def validate_resolved(validator, values, strict=False):
    # ComfyUI supplies None for connected controls before upstream execution.
    if not strict:
        if any(values.get(key, "") is None for key in ("model", "mode", "size", "frame_size", "frame_count")):
            return True
        values = {key: value for key, value in values.items() if value is not None}
    return validator(values, strict=strict)


class _BasicImage:
    KIND, MAX_IMAGES = "z_image", 0
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    FUNCTION = "generate"
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        required = {"prompt": ("STRING", {"default": "", "multiline": True})}
        if cls.KIND == "krea":
            required = {"model": (image_contract.KREA_MODELS, {"default": image_contract.KREA_MODELS[0]}), **required,
                "size": ([*image_contract.KREA_SIZES, "custom"], {"default": "1:1"}),
                "width": ("INT", {"default": 1024, "min": 256, "max": 4096}),
                "height": ("INT", {"default": 1024, "min": 256, "max": 4096}),
                "model_variant": (["berry", "jam"], {"default": "berry"}),
                "reasoning_level": (["low", "medium"], {"default": "low"}),
                "output_format": (["png", "jpeg"], {"default": "png"}),
                "negative_prompt": ("STRING", {"default": "", "multiline": True})}
        else:
            required["ratio"] = (image_contract.RATIOS, {"default": "1:1"})
        required["seed"] = ("INT", {"default": -1, "min": -1, "max": 2147483647 if cls.KIND == "krea" else 9007199254740991,
            "control_after_generate": True, "tooltip": "Native API seed; -1 omits the seed."})
        optional = {f"image{i}": ("IMAGE",) for i in range(1, cls.MAX_IMAGES + 1)}
        optional.update(api_config=(api.CONFIG_TYPE,), skip_error=("BOOLEAN", {"default": False}))
        return {"required": required, "optional": optional}

    @classmethod
    def VALIDATE_INPUTS(cls, strict=False, **values):
        return validate_resolved(lambda data, strict: image_contract.validate_basic(cls.KIND, data, strict), values, strict)

    @classmethod
    def build_payload(cls, values, images):
        return image_contract.basic_payload(cls.KIND, values, images)

    def generate(self, api_config=None, skip_error=False, **values):
        try:
            valid = self.VALIDATE_INPUTS(strict=True, **values)
            if valid is not True:
                raise Error(valid)
            encoded = common.encode_references(values, self.MAX_IMAGES, per_file=30 * 1024 * 1024)
            config = api.resolve_config(api_config)
            images = [api.upload_media(data, f"reference_{index}.png", "image/png", config) for index, data in encoded]
            identifier, _ = common.submit_request(self.build_payload(values, images), config)
            final = common.poll_request(identifier, config)
            url = api.extract_image_urls(final)[0]
            return api.download_image(url), url, identifier, json.dumps(final, ensure_ascii=False)
        except Exception as error:
            if not skip_error:
                raise
            return api.torch.ones((1, 512, 512, 3)), "", "", json.dumps({"status": "error", "message": str(error)})


class T8ZhenzhenZImage(_BasicImage):
    pass


class T8ZhenzhenKreaV3(_BasicImage):
    KIND, MAX_IMAGES = "krea", 8


class T8ZhenzhenImageG26:
    CATEGORY = _BasicImage.CATEGORY
    FUNCTION = "generate"
    RETURN_TYPES = ("IMAGE",) + ("STRING",) * 7
    RETURN_NAMES = ("image", "image_url", "task_id", "response", "local_path", "urls_json", "paths_json", "durations_json")
    OUTPUT_NODE = True
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    ZHENZHEN_DEFER_CONCURRENT_ERRORS = True

    @classmethod
    def INPUT_TYPES(cls):
        required = {
            "model": (image_contract.G26_MODELS, {"default": image_contract.G26_MODELS[0]}),
            "mode": (["image", "gif"], {"default": "image"}),
            "prompt": ("STRING", {"default": "", "multiline": True}),
            "size": (image_contract.IMAGE_SIZES, {"default": "1:1"}),
            "width": ("INT", {"default": 1024, "min": 16, "max": 3840, "step": 16}),
            "height": ("INT", {"default": 1024, "min": 16, "max": 3840, "step": 16}),
            "resolution": (["1k", "2k", "4k"], {"default": "1k"}),
            "quality": (image_contract.QUALITIES, {"default": "auto"}),
            "complexity": (["api_default", "low", "medium", "high"], {"default": "api_default"}),
            "n": ("INT", {"default": 1, "min": 1, "max": 4}),
            "output_format": (["png", "jpeg", "webp"], {"default": "png"}),
            "output_compression": ("INT", {"default": -1, "min": -1, "max": 100}),
            "frame_size": (image_contract.FRAME_SIZES, {"default": "512x512"}),
            "frame_width": ("INT", {"default": 512, "min": 16, "max": 3840, "step": 16}),
            "frame_height": ("INT", {"default": 512, "min": 16, "max": 3840, "step": 16}),
            "frame_count": ("INT", {"default": 9, "min": 2, "max": 16}),
            "frame_duration_ms": ("INT", {"default": 200, "min": 20, "step": 10}),
            "mask_url": ("STRING", {"default": ""}), "markup_url": ("STRING", {"default": ""}),
            "filename_prefix": ("STRING", {"default": "zhenzhen/g26"}),
        }
        optional = {f"image{i}": ("IMAGE",) for i in range(1, 17)}
        optional.update(api_config=(api.CONFIG_TYPE,), skip_error=("BOOLEAN", {"default": False}), seed=EXECUTION_SEED_SPEC)
        return {"required": required, "optional": optional}

    @classmethod
    def VALIDATE_INPUTS(cls, strict=False, **values):
        return validate_resolved(image_contract.validate_g26, values, strict)

    build_payload = staticmethod(image_contract.g26_payload)

    def generate(self, api_config=None, skip_error=False, **values):
        try:
            valid = self.VALIDATE_INPUTS(strict=True, **values)
            if valid is not True:
                raise Error(valid)
            prefix = values.get("filename_prefix", "zhenzhen/g26")
            artifacts.output_target(prefix)
            maximum = image_contract.G26_LOWPRICE_MAX_REFERENCES if values.get("model", image_contract.G26_MODELS[0]) == image_contract.G26_MODELS[0] else 16
            encoded = common.encode_references(values, maximum)
            config = api.resolve_config(api_config)
            refs = [api.upload_media(data, f"reference_{index}.png", "image/png", config) for index, data in encoded]
            identifier, _ = common.submit_request(self.build_payload(values, refs), config)
            final = common.poll_request(identifier, config)
            urls = api.extract_image_urls(final)
            images, paths, entries, durations, gifs = [], [], [], [], []
            for url in urls:
                image, path, entry, timing, extension = artifacts.download_original(url, prefix, values.get("mode", "image") == "gif")
                images.append(image); paths.append(path); entries.append(entry); durations.append(timing)
                if extension == "gif" and image.shape[0] > 1:
                    gifs.append(entry)
            if not images:
                raise Error("Image task has no result URLs")
            if len({tuple(image.shape[1:]) for image in images}) != 1:
                raise Error("Result dimensions differ; originals were saved but cannot form one IMAGE batch")
            result = (api.torch.cat(images), urls[0], identifier, json.dumps(final, ensure_ascii=False), paths[0],
                      json.dumps(urls), json.dumps(paths), json.dumps(durations))
            ui = {"images": entries}
            if gifs:
                ui["zhenzhen_gifs"] = gifs
            return {"ui": ui, "result": result}
        except Exception as error:
            if not skip_error:
                raise
            result = (api.torch.ones((1, 512, 512, 3)), "", "", json.dumps({"status": "error", "message": str(error)}), "", "[]", "[]", "[]")
            return {"ui": {}, "result": result}


class _Image3D:
    FAMILY = "hitem"
    CATEGORY = "zhenzhen/Seedance2 Low Price/3D"
    FUNCTION = "generate"
    OUTPUT_NODE = True
    RETURN_TYPES = ("FILE_3D", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("model_3d", "model_url", "local_path", "task_id", "response")
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True

    @classmethod
    def INPUT_TYPES(cls):
        required = {"model": (geometry_contract.models(cls.FAMILY), {"default": geometry_contract.models(cls.FAMILY)[0]})}
        if cls.FAMILY == "meshy":
            required.update(topology=(["api_default", "triangle", "quad"], {"default": "api_default"}),
                target_polycount=("INT", {"default": 0, "min": 0, "max": 300000}),
                symmetry_mode=(["api_default", "off", "auto", "on"], {"default": "api_default"}))
            for field in geometry_contract.BOOLEAN_FIELDS:
                required[field] = (geometry_contract.OPTIONAL_BOOLEAN, {"default": "api_default"})
        else:
            required.update(request_type=(["mesh", "both"], {"default": "both"}),
                resolution=(["1536pro"] if cls.FAMILY == "portrait" else ["1536", "1536pro"], {"default": "1536pro" if cls.FAMILY == "portrait" else "1536"}),
                face=("INT", {"default": 1000000, "min": 100000, "max": 2000000, "step": 10000}))
        maximum = 1 if cls.FAMILY == "meshy" else 4
        optional = {f"image{i}": ("IMAGE", {"tooltip": geometry_contract.VIEWS[i - 1]}) for i in range(1, maximum + 1)}
        optional.update(api_config=(api.CONFIG_TYPE,), skip_error=("BOOLEAN", {"default": False}), seed=EXECUTION_SEED_SPEC)
        if cls.FAMILY == "meshy":
            # Append after the legacy seed controls to keep saved widget positions.
            optional.update(prompt=("STRING", {"default": "", "multiline": True}),
                art_style=(["realistic", "sculpture"], {"default": "realistic"}),
                enable_prompt_expansion=("BOOLEAN", {"default": False}))
        return {"required": required, "optional": optional}

    @classmethod
    def VALIDATE_INPUTS(cls, strict=False, **values):
        return validate_resolved(lambda data, strict: geometry_contract.validate(cls.FAMILY, data, strict), values, strict)

    @classmethod
    def build_payload(cls, values, images):
        return geometry_contract.payload(cls.FAMILY, values, images)

    def generate(self, api_config=None, skip_error=False, **values):
        try:
            valid = self.VALIDATE_INPUTS(strict=True, **values)
            if valid is not True:
                raise Error(valid)
            encoded = common.encode_references(values, 1 if self.FAMILY == "meshy" else 4)
            config = api.resolve_config(api_config)
            refs = [api.upload_media(data, f"{geometry_contract.VIEWS[index - 1]}.png", "image/png", config) for index, data in encoded]
            identifier, _ = submit_3d(self.build_payload(values, refs), config)
            final = poll_3d(identifier, config)
            url = extract_3d_url(final)
            downloaded, _, _ = artifacts.download_file(url, "zhenzhen/" + self.FAMILY)
            path, format_ = geometry_contract.prepare_model(downloaded)
            return File3D(path, file_format=format_), url, path, identifier, json.dumps(final, ensure_ascii=False)
        except Exception as error:
            if not skip_error:
                raise
            return placeholder_file3d(str(error)), "", "", "", json.dumps({"status": "error", "message": str(error)})


class T8ZhenzhenHitem3DV2(_Image3D):
    pass


class T8ZhenzhenHitem3DPortrait21(_Image3D):
    FAMILY = "portrait"


class T8ZhenzhenMeshy6Global(_Image3D):
    FAMILY = "meshy"
