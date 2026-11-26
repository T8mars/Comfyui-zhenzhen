"""November 21 image, speech, video and 3D nodes for the Low Price channel."""

import json
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from zipfile import BadZipFile

from . import h3_token_contracts as h3, nov21_contracts as spec, seedance_low_price_nodes as api
from .aug22_low_price_nodes import File3D, placeholder_file3d
from .execution_seed import EXECUTION_SEED_SPEC
from .h3_turbo_low_price_nodes import get_config
from .hitem_meshy_contracts import prepare_model
from .image_artifacts import download_file
from .kling_v4_low_price_nodes import poll_kling_task, submit_kling_task
from .nov05_low_price_nodes import poll_3d, submit_3d


KEYS = {kind: f"T8Zhenzhen_{name}_LowPrice" for kind, name in {
    "long": "Kling_V4_Long_Image", "tts": "Gemini_25_TTS",
    "wf": "Minimax_H3_ComfyUI_Max_10020_Token", "jy": "Minimax_H3_ComfyUI_Max_10021_Token",
    "charswap": "Minimax_H3_ComfyUI_CharSwap_Token", "digital": "Minimax_H3_ComfyUI_Digital_Human_Token",
    "heygen": "HeyGen_Avatar_6", "miora": "Miora_3D",
}.items()}
PROMPT = ("STRING", {"default": "", "multiline": True})
OPTIONS = {"api_config": (api.CONFIG_TYPE,), "skip_error": ("BOOLEAN", {"default": False}), "seed": EXECUTION_SEED_SPEC}
Error = api.SeedanceLowPriceError


def combo(values, default=None):
    return (values, {"default": values[0] if default is None else default})


def slots(family, count, type_):
    return {f"{family}{i}": (type_,) for i in range(1, count + 1)}


def progress_bar():
    bar = api.comfy.utils.ProgressBar(100) if api.COMFYUI_AVAILABLE else None
    return lambda value: bar.update_absolute(int(value), 100) if bar is not None else None


def result(values, task, final, display):
    return {"ui": {"text": display}, "result": (*values, task, json.dumps(final, ensure_ascii=False))}


class _LowPriceNode:
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    ZHENZHEN_VALIDATE_CONCURRENT_AT_EXECUTION = True

    @classmethod
    def VALIDATE_INPUTS(cls, strict=False, **values):
        try:
            # Connected widgets are resolved during execution, including the prompt.
            cls.plan(values if strict else {k: v for k, v in values.items() if v is not None}, strict)
            return True
        except (Error, ValueError) as error:
            return str(error)

    def execute(self, api_config=None, skip_error=False, seed=0, **values):
        if not self.SEEDANCE_EXPLICIT_CACHE_ONLY_SEED:
            values["seed"] = seed
        config = None
        try:
            prepared = self.prepare(values)
            config = get_config(api_config)
            if config["base_url"] != api.DEFAULT_BASE_URL:
                raise Error("Connect the Low Price API Settings channel")
            return self.run(prepared, config, progress_bar())
        except Exception as error:
            key = config["api_key"] if config else None
            message = str(error).replace(key, "[REDACTED]") if key else str(error)
            if not skip_error:
                if message != str(error):
                    raise Error(message) from None
                raise
            return self.error_result(message)


class T8ZhenzhenKlingLongImage(_LowPriceNode):
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    plan = staticmethod(spec.long_image)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"skill": combo(["ecommerce", "webpage"]), "prompt": PROMPT,
            "resolution": combo(["1k", "2k"]), "length": combo(["medium", "short", "long"]),
            "nsfw_check": ("BOOLEAN", {"default": False})},
            "optional": {**slots("image", 3, "IMAGE"), "style_image": ("IMAGE",), "subject_image": ("IMAGE",), **OPTIONS}}

    def prepare(self, values):
        body, refs = self.plan(values, True)
        return body, [(name, spec.long_image_bytes(image, name)) for name, image in refs]

    def run(self, prepared, config, progress):
        body, materials = prepared
        for index, (name, data) in enumerate(materials, 1):
            url = api.upload_media(data, f"{name}.png", "image/png", config)
            if body["skill"] == "webpage":
                body.setdefault("image_with_roles", []).append({"url": url, "role": name})
            else:
                body.setdefault("images", []).append(url)
            progress(15 * index / len(materials))
        task, _ = api.submit_image_task(body, config, retry_server_errors=False)
        progress(20)
        final = api.poll_image_task(task, config, on_progress=lambda value: progress(20 + value * .75))
        urls = api.extract_image_urls(final)
        if len(urls) != 1:
            raise Error(f"Kling Long Image expected one image, got {len(urls)}")
        image = api.download_image(urls[0])
        progress(100)
        return result((image, urls[0]), task, final, urls)

    def error_result(self, message):
        return result((api.torch.zeros((1, 64, 64, 3)), ""), "", {"error": message}, [message])


class T8ZhenzhenGemini25TTS(_LowPriceNode):
    RETURN_TYPES = (api.AUDIO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio", "audio_url", "task_id", "response")
    plan = staticmethod(spec.gemini_tts)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": combo(spec.GEMINI_TTS, spec.GEMINI_TTS[1]), "prompt": PROMPT,
            "voice": combo(spec.GEMINI_VOICES, "Kore"), "instructions": PROMPT},
            "optional": OPTIONS.copy()}

    def prepare(self, values):
        return self.plan(values, True)

    def run(self, body, config, progress):
        task, _ = api.submit_audio_task(body, config, retry_server_errors=False)
        progress(20)
        final = api.poll_audio_task(task, config, on_progress=lambda value: progress(20 + value * .75))
        url = api.extract_audio_url(final)
        audio = api.download_audio(url, "wav", 24000)
        progress(100)
        return result((audio, url), task, final, [url])

    def error_result(self, message):
        return result((api.make_error_audio(), ""), "", {"error": message}, [message])


class _LegacyVideoNode(_LowPriceNode):
    RETURN_TYPES = (api.VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")

    def run(self, prepared, config, progress):
        body, materials = prepared
        for index, (field, filename, mime, data) in enumerate(materials, 1):
            url = api.upload_media(data, filename, mime, config)
            destination = body if field == "images" else body["metadata"]
            destination.setdefault(field, []).append(url)
            progress(15 * index / len(materials))
        task, _ = submit_kling_task(body, config, label=body["model"])
        progress(20)
        final = poll_kling_task(task, config, label=body["model"], on_progress=lambda value: progress(20 + value * .75))
        url = api.extract_legacy_video_url(final)
        video = api.download_video(url)
        progress(100)
        return result((video, url), task, final, [url])

    def error_result(self, message):
        return result((api.make_error_video(message), ""), "", {"error": message}, [message])


class _H3Token(_LegacyVideoNode):
    @classmethod
    def INPUT_TYPES(cls):
        _, _, audio, video, minimum = h3.PROFILES[cls.KIND]
        charswap = cls.KIND == "charswap"
        required = {"prompt": PROMPT, "seconds": combo([str(i) for i in range(minimum, 16)], "5"),
                    "ratio": combo(["auto"] if charswap else h3.RATIOS)}
        if charswap:
            required.update(duration_mode=combo(["seconds", "frames"]), frames=combo(h3.FRAMES, 124))
        optional = {**slots("image", h3.image_socket_count(cls.KIND), "IMAGE"),
                    **slots("audio", audio, api.AUDIO_TYPE), **slots("video", video, api.VIDEO_TYPE)}
        if video:
            optional["video_urls"] = ("STRING", {"default": "", "tooltip": "One public MP4 URL instead of the local VIDEO input"})
        return {"required": required, "optional": {**optional, **OPTIONS}}

    @classmethod
    def plan(cls, values, strict):
        return h3.plan(cls.KIND, values, strict)

    def prepare(self, values):
        body, refs = self.plan(values, True)
        return body, h3.encode(self.KIND, body, refs)


class T8ZhenzhenH3WFToken(_H3Token):
    KIND = "wf"


class T8ZhenzhenH3JYToken(_H3Token):
    KIND = "jy"


class T8ZhenzhenH3CharSwapToken(_H3Token):
    KIND = "charswap"


class T8ZhenzhenH3DigitalHumanToken(_H3Token):
    KIND = "digital"


class T8ZhenzhenHeyGenAvatar6(_LegacyVideoNode):
    plan = staticmethod(spec.heygen)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": combo(spec.HEYGEN),
            "avatar": ("STRING", {"default": "Abigail Sofa Front", "tooltip": "Available avatar name from the provider's Playground"}),
            "prompt": PROMPT, "voice": ("STRING", {"default": "Warm Pro Narrator"}),
            "motion_prompt": PROMPT, "ratio": combo(spec.HEYGEN_RATIOS), "resolution": combo(["1080p", "2k"])},
            "optional": {"audio": (api.AUDIO_TYPE,), "audio_url": ("STRING", {"default": "", "tooltip": "Public HTTPS MP3/WAV/M4A instead of local AUDIO"}), **OPTIONS}}

    def prepare(self, values):
        body = self.plan(values, True)
        audio = values.get("audio")
        return body, [("audio_urls", "speech.wav", "audio/wav", spec.audio_bytes(audio))] if audio is not None else []


def inspect_miora_file(url, path):
    extension = PurePosixPath(urlsplit(url).path).suffix.lstrip(".").lower()
    with path.open("rb") as stream:
        header = stream.read(12)
    if header[:4] == b"glTF":
        extension = "glb"
    elif header.startswith(b"PK"):
        extension = "zip"
    elif header.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = "png"
    elif extension not in {"obj", "mtl", "jpg", "jpeg", "png", "webp", "zip", "glb", "usdz", "fbx"}:
        extension = "bin"
    return None, extension


class T8ZhenzhenMiora3D(_LowPriceNode):
    CATEGORY = _LowPriceNode.CATEGORY + "/3D"
    RETURN_TYPES = ("FILE_3D",) + ("STRING",) * 5
    RETURN_NAMES = ("model_3d", "model_url", "local_path", "task_id", "files_json", "response")
    plan = staticmethod(spec.miora)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": PROMPT, "generate_type": combo(["normal", "geometry"]),
            "face_count": ("INT", {"default": 500000, "min": 3000, "max": 1500000}),
            "enable_pbr": ("BOOLEAN", {"default": False})},
            "optional": {**{f"image{i}": ("IMAGE", {"tooltip": f"View {i}: {view}"})
                             for i, view in enumerate(spec.MIORA_VIEWS, 1)}, **OPTIONS}}

    def prepare(self, values):
        body, refs = self.plan(values, True)
        return body, [(spec.MIORA_VIEWS[index - 1], spec.image_bytes(image, f"image{index}", 10_000_000)) for index, image in refs]

    def run(self, prepared, config, progress):
        body, materials = prepared
        for index, (view, data) in enumerate(materials, 1):
            body.setdefault("images", []).append(api.upload_media(data, f"{view}.png", "image/png", config))
            progress(15 * index / len(materials))
        task, _ = submit_3d(body, config)
        progress(20)
        final = poll_3d(task, config)
        urls = spec.miora_urls(final)
        files, warnings = [], []
        for index, url in enumerate(urls, 1):
            entry = {"url": url}
            try:
                path, _, _ = download_file(url, f"zhenzhen/miora_{index}", inspect=lambda path: inspect_miora_file(url, path))
            except (Error, OSError) as error:
                entry["error"] = str(error)
                warnings.append(f"Miora could not download artifact {index}: {error}")
            else:
                entry["local_path"] = path
            files.append(entry)
            progress(90 + 10 * index / len(urls))
        primary = None
        for suffix in (".glb", ".zip", ".obj"):
            for entry in files:
                path = entry.get("local_path")
                if not path or not path.endswith(suffix):
                    continue
                try:
                    path, format_ = prepare_model(path)
                except (Error, OSError, BadZipFile):
                    continue
                entry.update(model_path=path, format=format_)
                primary = (File3D(path, file_format=format_), entry["url"], path)
                break
            if primary is not None:
                break
        if primary is None:
            raise Error(f"Miora task {task}: no valid GLB or OBJ was downloaded. Check the saved artifacts and upstream task.")
        return {"ui": {"text": [primary[2], *warnings]}, "result": (*primary, task,
            json.dumps(files, ensure_ascii=False), json.dumps(final, ensure_ascii=False))}

    def error_result(self, message):
        return {"ui": {"text": [message]}, "result": (placeholder_file3d(message), "", "", "", "[]", json.dumps({"error": message}))}


CLASSES = {"long": T8ZhenzhenKlingLongImage, "tts": T8ZhenzhenGemini25TTS, "wf": T8ZhenzhenH3WFToken,
    "jy": T8ZhenzhenH3JYToken, "charswap": T8ZhenzhenH3CharSwapToken, "digital": T8ZhenzhenH3DigitalHumanToken,
    "heygen": T8ZhenzhenHeyGenAvatar6, "miora": T8ZhenzhenMiora3D}
DISPLAY_NAMES = {kind: "zhenzhen-" + title + "（平价小屋）" for kind, title in {
    "long": "Kling 4 长图", "tts": "Gemini 2.5 Pro/Flash TTS",
    "wf": "MiniMax H3 WF 漫剧 Token", "jy": "MiniMax H3 JY 特调 Token",
    "charswap": "MiniMax H3 角色替换 Token", "digital": "MiniMax H3 数字人 Token",
    "heygen": "HeyGen Avatar 6 / Turbo", "miora": "Miora 3D",
}.items()}
