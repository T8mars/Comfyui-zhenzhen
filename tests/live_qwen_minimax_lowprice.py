"""Opt-in paid verification for Qwen Image 3.0 and MiniMax H3 OW.

Every model runs through its generated concurrent submit node. The API key is
read only from SEEDANCE_API_KEY and no task identifiers or result URLs are
printed or written to tracked files.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import tempfile
import time
import types
from typing import Any

import cv2
import torch


PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]
COMFY_ROOT = PLUGIN_ROOT.parents[1]
sys.path.insert(0, str(COMFY_ROOT))

import comfy_api.latest  # noqa: E402,F401


def load_modules():
    package_name = "zhenzhen_qwen_minimax_live_package"
    package = types.ModuleType(package_name)
    package.__path__ = [str(PLUGIN_ROOT)]
    sys.modules[package_name] = package
    loaded = {}
    for short_name in ("Comfly", "ComflyConcurrent"):
        module_name = f"{package_name}.{short_name}"
        spec = importlib.util.spec_from_file_location(
            module_name, PLUGIN_ROOT / f"{short_name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        loaded[short_name] = module
    return loaded["Comfly"], loaded["ComflyConcurrent"]


def make_reference() -> torch.Tensor:
    axis = torch.linspace(0.0, 1.0, 512)
    horizontal = axis.view(1, 1, 512, 1).expand(1, 512, 512, 1)
    vertical = axis.view(1, 512, 1, 1).expand(1, 512, 512, 1)
    blue = torch.full_like(horizontal, 0.28)
    image = torch.cat((horizontal, vertical, blue), dim=-1)
    image[:, 150:362, 150:362, :] = torch.tensor([0.92, 0.74, 0.18])
    return image


def make_drive_audio() -> dict[str, Any]:
    sample_rate = 44100
    timeline = torch.arange(sample_rate * 5, dtype=torch.float32) / sample_rate
    waveform = (0.12 * torch.sin(2.0 * torch.pi * 220.0 * timeline)).view(1, 1, -1)
    return {"waveform": waveform, "sample_rate": sample_rate}


def result_path(video: Any) -> pathlib.Path | None:
    if isinstance(video, str):
        return pathlib.Path(video)
    if isinstance(video, dict):
        value = video.get("file_path") or video.get("path")
        return pathlib.Path(value) if isinstance(value, str) else None
    for attribute in ("path", "file_path", "video_path"):
        value = getattr(video, attribute, None)
        if isinstance(value, str):
            return pathlib.Path(value)
    getter = getattr(video, "get_stream_source", None)
    if callable(getter):
        source = getter()
        if isinstance(source, str):
            return pathlib.Path(source)
        name = getattr(source, "name", None)
        if isinstance(name, str):
            return pathlib.Path(name)
    return None


def run_qwen_models(comfly, concurrent, api_config, reference) -> None:
    mapping_key = "Comfly_qwen_image_3_0_lowprice"
    submit_class = concurrent.CONCURRENT_NODE_CLASS_MAPPINGS[
        f"ComflyConcurrent_{mapping_key}_Submit"
    ]
    node_module = sys.modules[comfly.Comfly_qwen_image_3_0_lowprice.__module__]
    for model in node_module.QWEN_IMAGE_30_MODELS:
        kwargs = {
            "model": model,
            "prompt": (
                "Keep the central geometric object recognizable, replace the background "
                "with a clean pale gray studio set, soft natural light"
                if model.endswith("-i2i")
                else "A small cobalt glass sculpture on a clean white studio table, soft daylight"
            ),
            "negative_prompt": "blur, low detail",
            "prompt_extend": True,
            "sizing_mode": "ratio",
            "resolution": "1k",
            "ratio": "1:1",
            "custom_size": "1024*1024",
            "n": 1,
            "seed": -1,
            "api_config": api_config,
            "skip_error": False,
        }
        if model.endswith("-i2i"):
            kwargs["image1"] = reference

        succeeded = False
        for attempt in range(3):
            try:
                task = submit_class().submit(**kwargs)[0]
                result = concurrent.ComflyConcurrentImageAwait().wait_all(
                    failure_mode="fail_fast",
                    task_1=task,
                )
                image = result[0]
                if not torch.is_tensor(image) or image.ndim != 4 or image.shape[-1] != 3:
                    raise RuntimeError("result is not a valid ComfyUI IMAGE tensor")
                print(f"{model} SUCCESS", flush=True)
                succeeded = True
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(8 * (attempt + 1))
        if not succeeded:
            raise RuntimeError(f"{model} did not complete")


def run_minimax_models(comfly, concurrent, api_config, reference) -> None:
    mapping_key = "Comfly_minimax_h3_ow_video_lowprice"
    submit_class = concurrent.CONCURRENT_NODE_CLASS_MAPPINGS[
        f"ComflyConcurrent_{mapping_key}_Submit"
    ]
    node_module = sys.modules[comfly.Comfly_minimax_h3_ow_video_lowprice.__module__]
    selection = os.environ.get("MINIMAX_H3_OW_LIVE_ONLY", "all").strip()
    if selection == "all":
        models = list(node_module.MINIMAX_H3_OW_MODELS)
    elif selection in node_module.MINIMAX_H3_OW_MODELS:
        models = [selection]
    else:
        raise SystemExit(
            "MINIMAX_H3_OW_LIVE_ONLY must be all or one exact MiniMax H3 OW model"
        )
    tasks = []
    for model in models:
        kwargs = {
            "model": model,
            "prompt": (
                "Keep the reference object consistent while the camera slowly arcs around it"
                if model != node_module.MINIMAX_H3_OW_T2V_MODEL
                else "A white paper airplane glides through a sunlit greenhouse, smooth cinematic camera"
            ),
            "seconds": "5",
            "resolution": "480p",
            "ratio": "16:9",
            "api_config": api_config,
            "skip_error": False,
        }
        if model in (
            node_module.MINIMAX_H3_OW_I2V_MODEL,
            node_module.MINIMAX_H3_OW_R2V_MODEL,
        ):
            kwargs["image1"] = reference
        tasks.append(submit_class().submit(**kwargs)[0])

    result = concurrent.ComflyConcurrentVideoAwait().wait_all(
        failure_mode="fail_fast",
        **{f"task_{index + 1}": task for index, task in enumerate(tasks)},
    )
    for model, video in zip(models, result[: len(models)]):
        if video is None:
            raise RuntimeError(f"{model} returned an empty VIDEO")
        path = result_path(video)
        if path is not None and (not path.is_file() or path.stat().st_size <= 0):
            raise RuntimeError(f"{model} downloaded video is missing or empty")
        if path is None:
            raise RuntimeError(f"{model} did not expose a readable local video path")
        capture = cv2.VideoCapture(str(path))
        try:
            if not capture.isOpened():
                raise RuntimeError(f"{model} MP4 could not be opened by OpenCV")
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(capture.get(cv2.CAP_PROP_FPS))
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            decoded, frame = capture.read()
            if (
                not decoded
                or frame is None
                or width <= 0
                or height <= 0
                or fps <= 0
                or frame_count <= 0
            ):
                raise RuntimeError(f"{model} MP4 did not decode into valid frames")
        finally:
            capture.release()
        print(
            f"{model} SUCCESS decode={width}x{height} fps={fps:.2f} frames={frame_count}",
            flush=True,
        )


def run_minimax_fast_models(comfly, concurrent, api_config, reference) -> int:
    mapping_key = "Comfly_minimax_h3_ow_fast_video_lowprice"
    submit_class = concurrent.CONCURRENT_NODE_CLASS_MAPPINGS[
        f"ComflyConcurrent_{mapping_key}_Submit"
    ]
    node_module = sys.modules[
        comfly.Comfly_minimax_h3_ow_fast_video_lowprice.__module__
    ]
    selection = os.environ.get("MINIMAX_H3_OW_FAST_LIVE_ONLY", "all").strip()
    if selection == "all":
        models = list(node_module.MINIMAX_H3_OW_FAST_MODELS)
    elif selection == "new":
        models = [
            node_module.MINIMAX_H3_OW_FAST_FL2VA_AUDIO_MODEL,
            node_module.MINIMAX_H3_OW_FAST_REF2VA_AUDIO_MODEL,
            node_module.MINIMAX_H3_OW_FAST_T2V_MODEL,
        ]
    elif selection in node_module.MINIMAX_H3_OW_FAST_MODELS:
        models = [selection]
    else:
        raise SystemExit(
            "MINIMAX_H3_OW_FAST_LIVE_ONLY must be all, new, or one exact Fast model"
        )
    drive_audio = make_drive_audio()
    for model in models:
        last_error = None
        video = None
        for attempt in range(3):
            try:
                kwargs = dict(
                    model=model,
                    prompt=(
                        "A white paper kite glides through a sunlit greenhouse with smooth "
                        "cinematic camera movement"
                        if model == node_module.MINIMAX_H3_OW_FAST_T2V_MODEL
                        else "Keep the reference subject consistent while the connected audio "
                        "drives a subtle natural performance"
                    ),
                    seconds="5",
                    resolution="480p",
                    ratio="16:9",
                    api_config=api_config,
                    skip_error=False,
                )
                if model != node_module.MINIMAX_H3_OW_FAST_T2V_MODEL:
                    kwargs["image1"] = reference
                if model in node_module.MINIMAX_H3_OW_FAST_AUDIO_MODELS:
                    kwargs["audio"] = drive_audio
                task = submit_class().submit(**kwargs)[0]
                result = concurrent.ComflyConcurrentVideoAwait().wait_all(
                    failure_mode="fail_fast",
                    task_1=task,
                )
                video = result[0]
                break
            except Exception as exc:
                last_error = exc
                if attempt == 2:
                    raise
                time.sleep(12 * (attempt + 1))
        if video is None:
            raise RuntimeError(f"{model} did not complete: {type(last_error).__name__}")
        path = result_path(video)
        if path is None or not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(f"{model} returned no readable local MP4")
        capture = cv2.VideoCapture(str(path))
        try:
            decoded, frame = capture.read()
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(capture.get(cv2.CAP_PROP_FPS))
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            if (
                not capture.isOpened()
                or not decoded
                or frame is None
                or min(width, height, frame_count) <= 0
                or fps <= 0
            ):
                raise RuntimeError(f"{model} MP4 did not decode into valid frames")
        finally:
            capture.release()
        print(
            f"{model} SUCCESS decode={width}x{height} fps={fps:.2f} "
            f"frames={frame_count}",
            flush=True,
        )
    return len(models)


def main() -> None:
    api_key = os.environ.get("SEEDANCE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set SEEDANCE_API_KEY to run paid live verification")
    api_config = {
        "base_url": "https://api.seedance.nz",
        "api_key": api_key,
        "timeout": 90,
        "upload_timeout": 180,
        "poll_interval": 4,
        "max_poll_time": 2400,
    }
    comfly, concurrent = load_modules()
    reference = make_reference()
    live_only = os.environ.get("QWEN_MINIMAX_LIVE_ONLY", "all").strip().lower()
    if live_only not in {"all", "image", "video", "fast"}:
        raise SystemExit(
            "QWEN_MINIMAX_LIVE_ONLY must be all, image, video, or fast"
        )
    with tempfile.TemporaryDirectory(prefix="zhenzhen_qwen_minimax_live_") as output_dir:
        previous_output = os.environ.get("SEEDANCE_OUTPUT_DIR")
        os.environ["SEEDANCE_OUTPUT_DIR"] = output_dir
        fast_total = 0
        try:
            if live_only in {"all", "image"}:
                run_qwen_models(comfly, concurrent, api_config, reference)
            if live_only in {"all", "video"}:
                run_minimax_models(comfly, concurrent, api_config, reference)
            if live_only in {"all", "fast"}:
                fast_total = run_minimax_fast_models(
                    comfly, concurrent, api_config, reference
                )
        finally:
            if previous_output is None:
                os.environ.pop("SEEDANCE_OUTPUT_DIR", None)
            else:
                os.environ["SEEDANCE_OUTPUT_DIR"] = previous_output
            concurrent._shutdown_executors()
    video_selection = os.environ.get("MINIMAX_H3_OW_LIVE_ONLY", "all").strip()
    video_total = 3 if video_selection == "all" else 1
    all_total = 8 + video_total + fast_total
    completed = {
        "all": f"{all_total}/{all_total}",
        "image": "8/8",
        "video": f"{video_total}/{video_total}",
        "fast": f"{fast_total}/{fast_total}",
    }[live_only]
    print(f"LIVE_CHECKS {completed} SUCCESS", flush=True)


if __name__ == "__main__":
    main()
