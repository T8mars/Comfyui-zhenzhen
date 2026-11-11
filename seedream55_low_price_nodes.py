"""Seedream 5.5 images/layers and Seedance 2.5 draft enhancement."""

import json

try:
    from . import seedance_low_price_nodes as api, seedream55_contracts as seedream55
    from . import kling_v4_low_price_nodes as transport
    from .image_artifacts import output_target
    from .execution_seed import EXECUTION_SEED_SPEC
except ImportError:
    import seedance_low_price_nodes as api
    import seedream55_contracts as seedream55
    import kling_v4_low_price_nodes as transport
    from image_artifacts import output_target
    from execution_seed import EXECUTION_SEED_SPEC

Error = api.SeedanceLowPriceError
DRAFT_MODELS = ["seedance-2.5-standard-draft-to-video", "seedance-2.5-global-standard-draft-to-video"]


def get_config(value=None):
    if api._unwrap_api_config(value) is None:
        raise Error("Connect this workflow's Low Price API Settings with a non-empty API key")
    return api.resolve_config(value)


def submit_task(payload, config, image=False):
    try:
        return transport.submit_kling_task(payload, config, endpoint="image/generations" if image else "videos")[0]
    except Error as error:
        raise Error(str(error).replace("Kling 4", "Seedream 5.5 / Seedance draft")) from None


def poll_task(task, config, image=False, on_progress=None):
    try:
        return transport.poll_kling_task(task, config, endpoint="image/generations" if image else "videos", on_progress=on_progress)
    except Error as error:
        raise Error(str(error).replace("Kling 4", "Seedream 5.5 / Seedance draft")) from None


def download_video_with_path(url, file_extension="mp4"):
    video = api.download_video(url, file_extension=file_extension)
    path = video if isinstance(video, str) else video.get_stream_source()
    return video, path


def layer_urls(final):
    data = final.get("data") if isinstance(final, dict) else None
    nested = data.get("data") if isinstance(data, dict) else None
    content = nested.get("content") if isinstance(nested, dict) else None
    urls = content.get("image_urls") if isinstance(content, dict) else None
    if not isinstance(urls, list) or not urls or any(not isinstance(url, str) or not url.startswith(("http://", "https://")) for url in urls):
        raise Error("Layer decomposition requires a complete non-empty image_urls array")
    return urls


class _Seedream55Base:
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    LAYER = False
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    ZHENZHEN_VALIDATE_CONCURRENT_AT_EXECUTION = True
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING", "MASK", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response", "mask", "local_path")

    @classmethod
    def INPUT_TYPES(cls):
        models = seedream55.LAYER_MODELS if cls.LAYER else seedream55.IMAGE_MODELS
        required = {"model": (models, {"default": models[0]})}
        if cls.LAYER:
            required["image"] = ("IMAGE",)
        required.update(prompt=("STRING", {"default": "", "multiline": True}),
            resolution=(seedream55.LAYER_RESOLUTIONS if cls.LAYER else seedream55.RESOLUTIONS, {"default": "auto" if cls.LAYER else "1k"}))
        if cls.LAYER:
            required.update(max_images=("INT", {"default": 30, "min": 2, "max": 100, "tooltip": "Includes the base image"}),
                text_recognition=("BOOLEAN", {"default": False}))
        else:
            required.update(width=("INT", {"default": 1024, "min": 240, "max": 11520}),
                height=("INT", {"default": 1024, "min": 240, "max": 11520}),
                background=(["auto", "transparent", "opaque"], {"default": "auto"}))
        required.update(output_format=(["png", "jpeg"], {"default": "png"}), watermark=("BOOLEAN", {"default": False}),
            safety_identifier=("STRING", {"default": ""}),
            filename_prefix=("STRING", {"default": "zhenzhen/seedream55_layers" if cls.LAYER else "zhenzhen/seedream55"}))
        optional = {} if cls.LAYER else {f"image{i}": ("IMAGE",) for i in range(1, 11)}
        optional.update(api_config=(api.CONFIG_TYPE,), skip_error=("BOOLEAN", {"default": False}), seed=EXECUTION_SEED_SPEC)
        return {"required": required, "optional": optional}

    @classmethod
    def VALIDATE_INPUTS(cls, strict=False, **kwargs):
        if not strict:
            if any(name in kwargs and kwargs[name] is None for name in ("model", "resolution")):
                return True
            kwargs = {key: value for key, value in kwargs.items() if value is not None}
        try:
            return seedream55.validate(kwargs, layer=cls.LAYER, strict=strict)
        except Error as error:
            return str(error)

    def execute(self, api_config=None, skip_error=False, seed=0, **kwargs):
        del seed
        try:
            return self._execute_inner(api_config=api_config, **kwargs)
        except Exception as error:
            if not skip_error:
                raise
            image = api.torch.zeros(1, 64, 64, 3)
            mask = image.new_zeros(image.shape[:3])
            response = json.dumps({"error": str(error)}, ensure_ascii=False)
            result = ([image], [mask], "[]", 0, "", response, "[]", "[]") if self.LAYER else (image, "", "", response, mask, "")
            return {"ui": {"text": [response]}, "result": result}

    def _execute_inner(self, api_config=None, **kwargs):
        seedream55.validate(kwargs, layer=self.LAYER, strict=True)
        prefix = kwargs.get("filename_prefix", "zhenzhen/seedream55_layers" if self.LAYER else "zhenzhen/seedream55")
        output_target(prefix)
        encoded = seedream55.encode_references({"image1": kwargs["image"]} if self.LAYER else kwargs)
        config = get_config(api_config)
        urls = [api.upload_media(data, f"seedream55_{index}.png", "image/png", config) for index, data in encoded]
        task = submit_task(seedream55.payload(kwargs, urls, self.LAYER), config, image=True)
        final = poll_task(task, config, image=True)
        urls = layer_urls(final) if self.LAYER else [api.extract_image_url(final)]
        metadata = seedream55.layer_metadata(final, urls) if self.LAYER else []
        images, masks, paths, entries = [], [], [], []
        for index, url in enumerate(urls):
            image, mask, path, entry = seedream55.download_original(url, f"{prefix}_{index:03d}")
            images.append(image)
            masks.append(mask)
            paths.append(path)
            entries.append(entry)
        response = json.dumps(final, ensure_ascii=False)
        result = (images, masks, json.dumps(urls), len(urls), task, response, json.dumps(paths), json.dumps(metadata, ensure_ascii=False)) if self.LAYER else (images[0], urls[0], task, response, masks[0], paths[0])
        return {"ui": {"images": entries}, "result": result}


class T8ZhenzhenSeedream55Image(_Seedream55Base):
    pass


class T8ZhenzhenSeedream55Layers(_Seedream55Base):
    LAYER = True
    COMFLY_CONCURRENT_DISABLED = True
    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "INT", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("images", "masks", "image_urls", "image_count", "task_id", "response", "local_paths", "layers_json")
    OUTPUT_IS_LIST = (True, True, False, False, False, False, False, False)


class T8ZhenzhenSeedance25DraftToVideo:
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    ZHENZHEN_VALIDATE_CONCURRENT_AT_EXECUTION = True
    RETURN_TYPES = (api.VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    MODELS = DRAFT_MODELS

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": (cls.MODELS, {"default": cls.MODELS[0]}),
            "draft_task_id": ("STRING", {"default": "", "tooltip": "Completed same-account/region draft task_id within 7 days, not a video URL"}),
            "output_format": (["mp4", "mov"], {"default": "mp4"}), "return_last_frame": ("BOOLEAN", {"default": False})},
            "optional": {"api_config": (api.CONFIG_TYPE,), "skip_error": ("BOOLEAN", {"default": False}), "seed": EXECUTION_SEED_SPEC}}

    @classmethod
    def VALIDATE_INPUTS(cls, model=None, draft_task_id=None, output_format=None, return_last_frame=None, strict=False, **kwargs):
        if model not in (None, *cls.MODELS) or (strict and model is None):
            return "Unsupported Seedance 2.5 draft-to-video model"
        if output_format not in (None, "mp4", "mov") or (strict and output_format is None):
            return "output_format must be mp4 or mov"
        if (strict or return_last_frame is not None) and type(return_last_frame) is not bool:
            return "return_last_frame must be boolean"
        if draft_task_id is not None and not isinstance(draft_task_id, str):
            return "draft_task_id must be text"
        if strict and not (draft_task_id or "").strip():
            return "Connect a completed same-region draft task_id"
        if isinstance(draft_task_id, str) and ("://" in draft_task_id or any(char.isspace() for char in draft_task_id.strip())):
            return "draft_task_id must be a task identifier, not a URL"
        return True

    def build_payload(self, kwargs, media=None):
        kwargs = {"model": self.MODELS[0], "output_format": "mp4", "return_last_frame": False, **kwargs}
        valid = self.VALIDATE_INPUTS(strict=True, **kwargs)
        if valid is not True:
            raise Error(valid)
        return {"model": kwargs.get("model", self.MODELS[0]), "metadata": {"draft_task_id": kwargs["draft_task_id"].strip(),
            "output_format": kwargs.get("output_format", "mp4"), "return_last_frame": kwargs.get("return_last_frame", False)}}

    def execute(self, api_config=None, skip_error=False, seed=0, **kwargs):
        del seed
        try:
            request = self.build_payload(kwargs)
            config = get_config(api_config)
            task = submit_task(request, config)
            final = poll_task(task, config)
            url = api.extract_video_url(final)
            video, _ = download_video_with_path(url, file_extension=request["metadata"]["output_format"])
            return video, url, task, json.dumps(final, ensure_ascii=False)
        except Exception as error:
            if not skip_error:
                raise
            return api.make_error_video(str(error)), "", "", json.dumps({"error": str(error)}, ensure_ascii=False)
