"""Moss Image generation and single-reference editing for the low-price channel."""

from __future__ import annotations

import json

try:
    from . import seedance_low_price_nodes as api
    from .execution_seed import EXECUTION_SEED_SPEC
except ImportError:
    import seedance_low_price_nodes as api
    from execution_seed import EXECUTION_SEED_SPEC


MOSS_MODEL = "moss-image"
MOSS_RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"]


class T8ZhenzhenMossImageLowPrice:
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "prompt": ("STRING", {"multiline": True, "default": "",
                                   "tooltip": "Required image description or editing instruction."}),
            "ratio": (MOSS_RATIOS, {"default": "9:16"}),
        }, "optional": {
            "image1": ("IMAGE", {"tooltip": "One optional reference image; disconnect for text generation. Batches are not supported."}),
            "api_config": (api.CONFIG_TYPE,),
            "skip_error": ("BOOLEAN", {"default": False}),
            "seed": EXECUTION_SEED_SPEC,
        }}

    @classmethod
    def VALIDATE_INPUTS(cls, prompt=None, ratio=None, image1=None, strict=False, **kwargs):
        if ratio not in MOSS_RATIOS and (strict or ratio is not None):
            return "Unsupported Moss aspect ratio"
        if not strict:
            return True
        if not str(prompt or "").strip():
            return "Moss prompt is required"
        if image1 is not None:
            if (not isinstance(image1, api.torch.Tensor) or image1.ndim != 4 or image1.shape[0] != 1
                    or min(image1.shape[1:3]) < 1 or image1.shape[3] not in (3, 4)
                    or not api.torch.isfinite(image1).all()):
                return "Moss requires one valid reference IMAGE, not a batch"
        return True

    @classmethod
    def build_payload(cls, values, images):
        if len(images) > 1:
            raise api.SeedanceLowPriceError("Moss accepts at most one reference image")
        arguments = {"prompt": values.get("prompt"), "ratio": values.get("ratio", "9:16"),
                     "image1": values.get("image1")}
        validation = cls.VALIDATE_INPUTS(**arguments, strict=True)
        if validation is not True:
            raise api.SeedanceLowPriceError(validation)
        payload = {"model": MOSS_MODEL, "prompt": str(arguments["prompt"]).strip(),
                   "metadata": {"ratio": arguments["ratio"]}}
        if images:
            payload["images"] = list(images)
        return payload

    def generate(self, prompt="", ratio="9:16", image1=None, api_config=None, skip_error=False, seed=0):
        del seed
        try:
            validation = self.VALIDATE_INPUTS(prompt=prompt, ratio=ratio, image1=image1, strict=True)
            if validation is not True:
                raise api.SeedanceLowPriceError(validation)
            config = api.resolve_config(api_config)
            bar = api.comfy.utils.ProgressBar(100) if api.COMFYUI_AVAILABLE else None

            def progress(value):
                if bar is not None:
                    bar.update_absolute(int(value), 100)

            progress(0)
            images = []
            if image1 is not None:
                images.append(api.upload_media(api.image_to_png_bytes(image1), "moss_reference.png", "image/png", config))
            progress(15)
            task_id, submitted = api.submit_image_task(self.build_payload({"prompt": prompt, "ratio": ratio}, images), config)
            progress(20)
            result = api.poll_image_task(task_id, config, on_progress=lambda value: progress(20 + value * .75))
            progress(95)
            try:
                url = api.extract_image_url(result)
            except api.SeedanceLowPriceError:
                url = api.extract_image_urls(result)[0]
            image = api.download_image(url)
            progress(100)
            response = json.dumps({"status": "SUCCESS", "model": MOSS_MODEL, "task_id": task_id,
                                   "submit": submitted, "result": result}, ensure_ascii=False, indent=2)
            return image, url, task_id, response
        except Exception as error:
            if not skip_error:
                raise
            return (api.torch.ones((1, 512, 512, 3)), "", "",
                    json.dumps({"status": "error", "model": MOSS_MODEL,
                                "message": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
