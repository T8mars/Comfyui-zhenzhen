"""Independent Low Price MiniMax H3 and Qwen Turbo nodes."""

import json

try:
    from . import seedance_low_price_nodes as api, h3_turbo_contracts as contracts
    from . import kling_v4_low_price_nodes as transport
    from .execution_seed import EXECUTION_SEED_SPEC
except ImportError:
    import seedance_low_price_nodes as api
    import h3_turbo_contracts as contracts
    import kling_v4_low_price_nodes as transport
    from execution_seed import EXECUTION_SEED_SPEC


KEYS = {"video": "T8Zhenzhen_Minimax_H3_ComfyUI_Max_LowPrice",
        "minimax_image": "T8Zhenzhen_Minimax_H3_Image_LowPrice",
        "qwen": "T8Zhenzhen_Qwen_Image_21_Turbo_LowPrice"}


def get_config(value):
    if api._unwrap_api_config(value) is None:
        raise api.SeedanceLowPriceError("Connect this workflow's Low Price API Settings with a non-empty API key")
    return api.resolve_config(value)


def submit_task(body, config, video=False):
    try:
        return transport.submit_kling_task(body, config, endpoint="video/generations" if video else "image/generations")[0]
    except api.SeedanceLowPriceError as error:
        raise api.SeedanceLowPriceError(str(error).replace("Kling 4", "MiniMax H3 / Qwen Turbo")) from None


def poll_task(task, config, video=False, on_progress=None):
    try:
        return transport.poll_kling_task(task, config, endpoint="video/generations" if video else "image/generations", on_progress=on_progress)
    except api.SeedanceLowPriceError as error:
        raise api.SeedanceLowPriceError(str(error).replace("Kling 4", "MiniMax H3 / Qwen Turbo")) from None


class _H3TurboBase:
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    ZHENZHEN_VALIDATE_CONCURRENT_AT_EXECUTION = True
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")

    @classmethod
    def INPUT_TYPES(cls):
        spec = contracts.PROFILES[cls.KIND]
        required = {"prompt": ("STRING", {"default": "", "multiline": True}),
                    "resolution": (spec["resolutions"], {"default": spec["default"]}),
                    "ratio": (spec["ratios"], {"default": spec["ratios"][0]})}
        if cls.KIND == "video":
            required["seconds"] = ([str(i) for i in range(3, 16)], {"default": "5"})
        else:
            if cls.KIND == "minimax_image":
                required["output_format"] = (["jpeg", "png", "webp"], {"default": "jpeg"})
            required["seed"] = ("INT", {"default": -1, "min": -1, "max": 2147483647, "step": 1,
                                        "control_after_generate": True, "tooltip": "-1 omits API seed; 0 is valid."})
        optional = {f"image{i}": ("IMAGE",) for i in range(1, spec["images"] + 1)}
        if cls.KIND == "video":
            optional.update({f"audio{i}": (api.AUDIO_TYPE,) for i in range(1, 4)})
        optional.update(api_config=(api.CONFIG_TYPE,), skip_error=("BOOLEAN", {"default": False}))
        if cls.KIND == "video":
            optional["seed"] = EXECUTION_SEED_SPEC
        return {"required": required, "optional": optional}

    @classmethod
    def VALIDATE_INPUTS(cls, strict=False, **values):
        try:
            return contracts.validate(cls.KIND, values, strict=strict)
        except api.SeedanceLowPriceError as error:
            return str(error)

    def execute(self, api_config=None, skip_error=False, **values):
        if self.KIND == "video":
            values.pop("seed", None)
        try:
            return self._execute_inner(api_config, **values)
        except Exception as error:
            if not skip_error:
                raise
            output = api.make_error_video(str(error)) if self.KIND == "video" else api.torch.zeros(1, 64, 64, 3)
            return {"ui": {"text": [str(error)]}, "result": (output, "", "", json.dumps({"error": str(error)}, ensure_ascii=False))}

    def _execute_inner(self, api_config=None, **values):
        prepared = contracts.encode_media(self.KIND, values)
        config = get_config(api_config)
        bar = api.comfy.utils.ProgressBar(100) if api.COMFYUI_AVAILABLE else None

        def progress(value):
            if bar is not None:
                bar.update_absolute(int(value), 100)

        images, audios = [], []
        for index, (name, data, mime) in enumerate(prepared):
            url = api.upload_media(data, name + (".png" if mime == "image/png" else ".wav"), mime, config)
            (images if mime == "image/png" else audios).append(url)
            progress(15 * (index + 1) / len(prepared))
        body = contracts.payload(self.KIND, values, images, audios)
        video = self.KIND == "video"
        task = submit_task(body, config, video=video)
        progress(20)
        final = poll_task(task, config, video=video, on_progress=lambda value: progress(20 + value * .7))
        url = api.extract_legacy_video_url(final) if video else api.extract_image_urls(final)[0]
        output = (api.download_video if video else api.download_image)(url)
        progress(100)
        response = json.dumps(final, ensure_ascii=False)
        return {"ui": {"text": [url]}, "result": (output, url, task, response)}


class T8ZhenzhenMinimaxH3ComfyUIMax(_H3TurboBase):
    KIND = "video"
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    RETURN_TYPES = (api.VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")


class T8ZhenzhenMinimaxH3Image(_H3TurboBase):
    KIND = "minimax_image"


class T8ZhenzhenQwenImage21Turbo(_H3TurboBase):
    KIND = "qwen"


CLASSES = {cls.KIND: cls for cls in (T8ZhenzhenMinimaxH3ComfyUIMax, T8ZhenzhenMinimaxH3Image, T8ZhenzhenQwenImage21Turbo)}
