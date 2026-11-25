"""Domestic and global Magi 2 video generation."""

import math
import mimetypes
import subprocess

from . import seedance_low_price_nodes as api
from .h3_comfy_contracts import slots
from .kling_v4_low_price_nodes import probe_video
from .nov21_contracts import audio_bytes, boolean, choice, image_bytes, text
from .nov21_low_price_nodes import OPTIONS, PROMPT, _LegacyVideoNode, combo


KEY = "T8Zhenzhen_Magi_2_Video_LowPrice"
DISPLAY_NAME = "zhenzhen-Magi 2 文生 / 首尾帧 / 参考生视频（平价小屋）"
MODELS = ["magi-2", "magi-2-global"]
MODES = ["auto", "text", "frame", "reference"]
RATIOS = ["api_default", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]
CAPS = {"image": 10, "video": 5, "audio": 5}
SEED_MAX = 2147483647
Error = api.SeedanceLowPriceError


def request(values, strict=False):
    model = choice(values, "model", MODELS)
    mode = choice(values, "generation_type", MODES)
    ratio = choice(values, "ratio", RATIOS)
    prompt = text(values, "prompt", maximum=15000, required=strict).strip()
    seconds = values.get("seconds", 5)
    if type(seconds) is not int or not 4 <= seconds <= 30:
        raise Error("Magi 2 duration must be 4-30 whole seconds")
    seed = values.get("seed", 0)
    if type(seed) is not int or not 0 <= seed <= SEED_MAX:
        raise Error(f"Magi 2 seed must be between 0 and {SEED_MAX}")
    metadata = {"resolution": "1080p", "generate_audio": boolean(
        {"generate_audio": values.get("generate_audio", True)}, "generate_audio"), "seed": seed}
    if ratio != "api_default":
        metadata["ratio"] = ratio
    refs = {family: slots(values, family, cap) for family, cap in CAPS.items()}
    images, has_av = refs["image"], bool(refs["audio"] or refs["video"])
    if mode == "auto":
        mode = "reference" if has_av or len(images) >= 3 else "frame" if images else "text"
    else:
        metadata["generation_type"] = mode
    if strict:
        if mode == "text" and (images or has_av):
            raise Error("Text mode does not accept references")
        if mode == "frame" and (has_av or [index for index, _ in images] not in ([1], [1, 2])):
            raise Error("Frame mode needs image1 as the start frame, optionally image2 as the end frame, and no video/audio")
        if mode == "reference" and not (images or has_av):
            raise Error("Reference mode needs at least one image, video or audio")
    return {"model": model, "prompt": prompt, "seconds": str(seconds), "metadata": metadata}, refs


def check_durations(family, durations):
    if any(not math.isfinite(value) or not 2 <= value <= 30 for value in durations):
        raise Error(f"Each Magi 2 reference {family} must be 2-30 seconds")
    if sum(durations) > 30:
        raise Error(f"Total Magi 2 reference {family} duration must not exceed 30 seconds")


def prepare(values):
    body, refs = request(values, strict=True)
    media = [("images", f"magi_image{index}.png", "image/png", image_bytes(image, f"image{index}"))
             for index, image in refs["image"]]
    durations = []
    for index, video in refs["video"]:
        data, extension = api.video_to_upload_bytes(video)
        try:
            durations.append(probe_video(data, extension)["duration"])
        except (Error, OSError, subprocess.SubprocessError) as error:
            raise Error(f"Could not determine the duration of Magi 2 reference video{index}") from error
        filename = f"magi_video{index}.{extension}"
        media.append(("video_url", filename, mimetypes.guess_type(filename)[0] or "video/mp4", data))
    check_durations("video", durations)
    durations = []
    for index, audio in refs["audio"]:
        data = audio_bytes(audio)
        durations.append(audio["waveform"].shape[-1] / audio["sample_rate"])
        media.append(("audio_urls", f"magi_audio{index}.wav", "audio/wav", data))
    check_durations("audio", durations)
    return body, media


class T8ZhenzhenMagi2Video(_LegacyVideoNode):
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = False
    plan = staticmethod(request)
    prepare = staticmethod(prepare)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": combo(MODELS),
            "generation_type": (MODES, {"default": "auto", "tooltip": "Auto treats 1-2 images as frames. Select reference for character or style images."}),
            "prompt": PROMPT,
            "seconds": ("INT", {"default": 5, "min": 4, "max": 30, "step": 1}),
            "ratio": (RATIOS, {"default": "api_default", "tooltip": "In frame mode, api_default follows the first frame's aspect ratio."}),
            "generate_audio": ("BOOLEAN", {"default": True}),
            "seed": ("INT", {"default": 0, "min": 0, "max": SEED_MAX, "control_after_generate": True}),
        }, "optional": {
            **{f"{family}{index}": (type_, {"tooltip": tooltip})
               for family, type_, tooltip in (
                   ("image", "IMAGE", "One image per socket; in frame mode image1 is start, image2 is end."),
                   ("video", api.VIDEO_TYPE, "2-30 seconds per clip; at most 30 seconds of video in total."),
                   ("audio", api.AUDIO_TYPE, "2-30 seconds per clip; at most 30 seconds of audio in total."),
               ) for index in range(1, CAPS[family] + 1)},
            "api_config": OPTIONS["api_config"], "skip_error": OPTIONS["skip_error"],
        }}
