"""Independent MiniMax H3 ComfyUI workflows for the Low Price channel."""

import json

from . import seedance_low_price_nodes as api, h3_comfy_contracts as contracts
from .h3_turbo_low_price_nodes import get_config, submit_task, poll_task
from .execution_seed import EXECUTION_SEED_SPEC

KEYS = {"charswap": "T8Zhenzhen_Minimax_H3_ComfyUI_CharSwap_LowPrice",
        "wuxi": "T8Zhenzhen_Minimax_H3_ComfyUI_Wuxi_LowPrice",
        "wf": "T8Zhenzhen_Minimax_H3_ComfyUI_Max_10020_LowPrice",
        "selflift": "T8Zhenzhen_Minimax_H3_ComfyUI_Max_10021_LowPrice"}


class _H3ComfyVideo:
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    ZHENZHEN_VALIDATE_CONCURRENT_AT_EXECUTION = True
    RETURN_TYPES = (api.VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")

    @classmethod
    def INPUT_TYPES(cls):
        spec = contracts.PROFILES[cls.KIND]
        required = {
            "prompt": ("STRING", {"default": "", "multiline": True}),
            "seconds": ([str(i) for i in range(spec["min_seconds"], 16)], {"default": "5"}),
            "resolution": (spec["resolutions"], {"default": spec["default"]}),
            "ratio": (contracts.ratios(cls.KIND, spec["default"]), {"default": "auto" if cls.KIND == "charswap" else "16:9"}),
        }
        if cls.KIND == "charswap":
            required.update(duration_mode=(["seconds", "frames"], {"default": "seconds"}),
                            frames=(contracts.FRAMES, {"default": 124}))
        optional = {f"image{i}": ("IMAGE",) for i in range(1, spec.get("image_sockets", spec["images"]) + 1)}
        optional.update({f"audio{i}": (api.AUDIO_TYPE,) for i in range(1, spec["audios"] + 1)})
        optional.update({f"video{i}": (api.VIDEO_TYPE,) for i in range(1, spec["videos"] + 1)})
        if spec["videos"]:
            optional["video_urls"] = ("STRING", {"default": "", "multiline": True,
                "tooltip": "Public MP4 URLs, one per line; local videos count toward the same limit."})
        optional.update(api_config=(api.CONFIG_TYPE,), skip_error=("BOOLEAN", {"default": False}))
        optional["seed"] = ("INT", {"default": -1, "min": -1, "max": 2147483647, "control_after_generate": True}) if spec["seed"] else EXECUTION_SEED_SPEC
        return {"required": required, "optional": optional}

    @classmethod
    def VALIDATE_INPUTS(cls, strict=False, **values):
        try:
            checked = values if strict else {name: value for name, value in values.items() if value is not None}
            return contracts.validate(cls.KIND, checked, strict)
        except (api.SeedanceLowPriceError, ValueError) as error:
            return str(error)

    def execute(self, api_config=None, skip_error=False, **values):
        if not contracts.PROFILES[self.KIND]["seed"]:
            values.pop("seed", None)
        try:
            return self._execute_inner(api_config, **values)
        except Exception as error:
            if not skip_error:
                raise
            return {"ui": {"text": [str(error)]}, "result": (api.make_error_video(str(error)), "", "", json.dumps({"error": str(error)}, ensure_ascii=False))}

    def _execute_inner(self, api_config=None, **values):
        config = get_config(api_config)
        encoded = contracts.encode_media(self.KIND, values)
        bar = api.comfy.utils.ProgressBar(100) if api.COMFYUI_AVAILABLE else None

        def progress(value):
            if bar is not None:
                bar.update_absolute(int(value), 100)

        media = {"images": [], "audios": [], "videos": []}
        for index, (name, data, mime) in enumerate(encoded):
            extension, family = {"image/png": ("png", "images"), "audio/wav": ("wav", "audios"), "video/mp4": ("mp4", "videos")}[mime]
            media[family].append(api.upload_media(data, name + "." + extension, mime, config))
            progress(15 * (index + 1) / len(encoded))
        media["videos"].extend(contracts.video_urls(values.get("video_urls", "")))
        task = submit_task(contracts.payload(self.KIND, values, media["images"], media["audios"], media["videos"]), config, video=True)
        progress(20)
        final = poll_task(task, config, video=True, on_progress=lambda value: progress(20 + value * .75))
        url = api.extract_legacy_video_url(final)
        video = api.download_video(url)
        progress(100)
        return {"ui": {"text": [url]}, "result": (video, url, task, json.dumps(final, ensure_ascii=False))}


class T8ZhenzhenH3CharSwap(_H3ComfyVideo):
    KIND = "charswap"


class T8ZhenzhenH3Wuxi(_H3ComfyVideo):
    KIND = "wuxi"


class T8ZhenzhenH3WF(_H3ComfyVideo):
    KIND = "wf"
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True


class T8ZhenzhenH3SelfLift(_H3ComfyVideo):
    KIND = "selflift"
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True


CLASSES = {cls.KIND: cls for cls in (T8ZhenzhenH3CharSwap, T8ZhenzhenH3Wuxi, T8ZhenzhenH3WF, T8ZhenzhenH3SelfLift)}
