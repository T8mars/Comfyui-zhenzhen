"""MAI Image 2.6 and Flash for the Zhenzhen low-price channel."""

from __future__ import annotations

import json

try:
    from . import seedance_low_price_nodes as api
    from .execution_seed import EXECUTION_SEED_SPEC
except ImportError:
    import seedance_low_price_nodes as api
    from execution_seed import EXECUTION_SEED_SPEC


MAI_MODELS = ["mai-image-2-6", "mai-image-2-6-flash"]
MAI_RESOLUTIONS = ["1k", "2k"]
MAI_SIZES = ["auto", "1:1", "16:9", "9:16", "21:9", "9:21", "2:3", "3:2",
             "3:4", "4:3", "4:5", "5:4", "1:2", "2:1", "1:3", "3:1",
             "1:4", "4:1", "custom_ratio", "custom_pixels"]
MAI_MAX_IMAGES = 5
MAI_MAX_PIXELS = 2359296


class T8ZhenzhenMAIImage26LowPrice:
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": (MAI_MODELS, {"default": MAI_MODELS[0]}),
            "prompt": ("STRING", {"multiline": True, "default": "",
                                   "tooltip": "Generation or editing instruction; about 32000 tokens upstream."}),
            "resolution": (MAI_RESOLUTIONS, {"default": "1k"}),
            "size": (MAI_SIZES, {"default": "1:1"}),
            "custom_ratio": ("STRING", {"default": "16:9",
                                         "tooltip": "Positive integer W:H, between 1:4 and 4:1."}),
            "width": ("INT", {"default": 1536, "min": 768, "max": 3072, "step": 32}),
            "height": ("INT", {"default": 1024, "min": 768, "max": 3072, "step": 32}),
            "auto_aspect_ratio": ("BOOLEAN", {"default": False}),
            "web_grounding": ("BOOLEAN", {"default": False,
                                           "tooltip": "Use Bing to retrieve current information."}),
        }, "optional": {
            **{f"image{i}": ("IMAGE", {"tooltip": f"Reference {i}/5; exactly one image per slot."})
               for i in range(1, MAI_MAX_IMAGES + 1)},
            "api_config": (api.CONFIG_TYPE,),
            "skip_error": ("BOOLEAN", {"default": False}),
            "seed": EXECUTION_SEED_SPEC,
        }}

    @staticmethod
    def sizing_payload(values):
        resolution = str(values.get("resolution", "1k")).lower()
        automatic = bool(values.get("auto_aspect_ratio", False))
        size = str(values.get("size", "1:1")).strip()
        if not automatic and size == "custom_pixels":
            width, height = values.get("width", 1536), values.get("height", 1024)
            if (type(width) is not int or type(height) is not int
                    or min(width, height) < 768 or width * height > MAI_MAX_PIXELS):
                raise api.SeedanceLowPriceError(
                    "MAI pixel dimensions require integer sides >=768 and area <=2359296"
                )
            return {"width": width // 32 * 32, "height": height // 32 * 32}
        if resolution not in MAI_RESOLUTIONS:
            raise api.SeedanceLowPriceError("MAI resolution must be 1k or 2k")
        if automatic:
            return {"size": "auto", "resolution": resolution, "auto_aspect_ratio": True}
        if size == "custom_ratio":
            size = str(values.get("custom_ratio", "")).strip()
        if size != "auto":
            parts = size.split(":")
            if len(parts) != 2 or not all(part.isascii() and part.isdecimal() for part in parts):
                raise api.SeedanceLowPriceError("MAI size requires auto or a positive integer W:H ratio")
            try:
                width, height = map(int, parts)
            except ValueError:
                raise api.SeedanceLowPriceError("MAI size requires a positive integer W:H ratio") from None
            if min(width, height) < 1 or width > height * 4 or height > width * 4:
                raise api.SeedanceLowPriceError("MAI aspect ratio must be between 1:4 and 4:1")
        return {"size": size, "resolution": resolution, "auto_aspect_ratio": False}

    @classmethod
    def VALIDATE_INPUTS(cls, model=None, prompt=None, strict=False, has_images=False, **values):
        if model not in (None, *MAI_MODELS):
            return "Unsupported MAI Image model"
        if strict and not str(prompt or "").strip():
            return "MAI prompt is required"
        if strict:
            references = [values[f"image{i}"] for i in range(1, MAI_MAX_IMAGES + 1)
                          if values.get(f"image{i}") is not None]
            for image in references:
                shape = getattr(image, "shape", ())
                if len(shape) != 4 or int(shape[0]) != 1:
                    return "Each MAI reference input requires exactly one IMAGE"
            if not references and not has_images:
                try:
                    cls.sizing_payload(values)
                except api.SeedanceLowPriceError as exc:
                    return str(exc)
        return True

    @classmethod
    def build_payload(cls, values, images):
        if len(images) > MAI_MAX_IMAGES:
            raise api.SeedanceLowPriceError("MAI accepts at most five reference images")
        validation = cls.VALIDATE_INPUTS(**{**values, "strict": True, "has_images": bool(images)})
        if validation is not True:
            raise api.SeedanceLowPriceError(validation)
        payload = {"model": values.get("model", MAI_MODELS[0]),
                   "prompt": str(values.get("prompt", "")).strip(), "n": 1,
                   "web_grounding": bool(values.get("web_grounding", False))}
        if images:
            payload["images"] = list(images)
        else:
            payload.update(cls.sizing_payload(values))
        return payload

    def generate(self, model=MAI_MODELS[0], prompt="", resolution="1k", size="1:1",
                 custom_ratio="16:9", width=1536, height=1024, auto_aspect_ratio=False,
                 web_grounding=False, api_config=None, skip_error=False, seed=0, **references):
        del seed
        values = dict(model=model, prompt=prompt, resolution=resolution, size=size,
                      custom_ratio=custom_ratio, width=width, height=height,
                      auto_aspect_ratio=auto_aspect_ratio, web_grounding=web_grounding, **references)
        bar = api.comfy.utils.ProgressBar(100) if api.COMFYUI_AVAILABLE else None

        def progress(value):
            if bar is not None:
                bar.update_absolute(int(value), 100)

        try:
            validation = self.VALIDATE_INPUTS(**values, strict=True)
            if validation is not True:
                raise api.SeedanceLowPriceError(validation)
            config = api.resolve_config(api_config)
            images = [(index, references[f"image{index}"]) for index in range(1, MAI_MAX_IMAGES + 1)
                      if references.get(f"image{index}") is not None]
            urls = []
            for index, image in images:
                urls.append(api.upload_media(api.image_to_png_bytes(image),
                                             f"mai_reference_{index}.png", "image/png", config))
                progress(len(urls) / len(images) * 20)
            task_id, submit = api.submit_image_task(self.build_payload(values, urls), config)
            progress(25)
            result = api.poll_image_task(task_id, config,
                                         on_progress=lambda value: progress(25 + value * .7))
            url = api.extract_image_urls(result)[0]
            progress(95)
            image = api.download_image(url)
            progress(100)
            response = json.dumps({"status": "SUCCESS", "model": model, "task_id": task_id,
                                   "submit": submit, "result": result}, ensure_ascii=False, indent=2)
            return (image, url, task_id, response)
        except Exception as exc:
            if not skip_error:
                raise
            return (api.torch.ones((1, 512, 512, 3)), "", "",
                    json.dumps({"status": "error", "model": model,
                                "message": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
