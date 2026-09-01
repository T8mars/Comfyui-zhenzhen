"""Opt-in paid verification for all eight FLUX 3 Video models."""

from __future__ import annotations

import concurrent.futures
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import av
import cv2
import numpy as np
import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import seedance_low_price_nodes as nodes


def make_frame(reverse: bool = False) -> torch.Tensor:
    width, height = 640, 360
    horizontal = torch.linspace(0.0, 1.0, width)
    if reverse:
        horizontal = torch.flip(horizontal, dims=[0])
    red = horizontal.view(1, 1, width, 1).expand(1, height, width, 1)
    green = torch.linspace(0.15, 0.85, height).view(1, height, 1, 1).expand(1, height, width, 1)
    blue = torch.full_like(red, 0.35)
    frame = torch.cat((red, green, blue), dim=-1)
    frame[:, 100:260, 240:400, :] = torch.tensor([0.95, 0.80, 0.18])
    return frame


def make_reference_video(path: Path) -> None:
    width, height, fps, frame_count = 640, 360, 24.0, 72
    container = av.open(str(path), mode="w")
    stream = container.add_stream("libx264", rate=int(fps))
    stream.width = width
    stream.height = height
    stream.pix_fmt = "yuv420p"
    try:
        for index in range(frame_count):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            frame[:, :] = (72, 46, 28)
            x = 60 + int((width - 180) * index / (frame_count - 1))
            cv2.circle(frame, (x, height // 2), 55, (40, 205, 245), -1)
            video_frame = av.VideoFrame.from_ndarray(frame, format="rgb24")
            for packet in stream.encode(video_frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("FLUX 3 reference MP4 is empty")


def result_path(video: Any) -> Path | None:
    if isinstance(video, str):
        return Path(video)
    if isinstance(video, dict):
        value = video.get("file_path") or video.get("path")
        return Path(value) if isinstance(value, str) else None
    for attribute in ("path", "file_path"):
        value = getattr(video, attribute, None)
        if isinstance(value, str):
            return Path(value)
    if hasattr(video, "get_stream_source"):
        source = video.get_stream_source()
        if isinstance(source, str):
            return Path(source)
        name = getattr(source, "name", None)
        if isinstance(name, str):
            return Path(name)
    return None


def validate_result(model: str, result: tuple[Any, ...]) -> None:
    if not result[1] or not result[3]:
        raise RuntimeError(f"{model} omitted its result URL or task id")
    path = result_path(result[0])
    if path is None or not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"{model} returned no readable MP4")
    capture = cv2.VideoCapture(str(path))
    try:
        decoded, frame = capture.read()
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not decoded or frame is None or min(width, height, frames) <= 0 or fps <= 0:
            raise RuntimeError(f"{model} MP4 did not decode")
    finally:
        capture.release()
    print(
        f"{model} SUCCESS decode={width}x{height} fps={fps:.2f} frames={frames}",
        flush=True,
    )


def generate_with_retry(model: str, config: dict[str, Any], **overrides) -> tuple[Any, ...]:
    kwargs: dict[str, Any] = {
        "model": model,
        "prompt": "A white paper airplane glides through a sunlit greenhouse with smooth cinematic camera movement",
        "seconds": "5",
        "resolution": "hd",
        "ratio": "16:9",
        "draft": False,
        "audio_mode": "api_default",
        "safety_tolerance": "api_default",
        "api_config": config,
        "skip_error": False,
    }
    kwargs.update(overrides)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            result = nodes.Comfly_flux3_video_lowprice().generate(**kwargs)
            validate_result(model, result)
            return result
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
    raise RuntimeError(
        f"{model} failed after 3 attempts ({type(last_error).__name__})"
    ) from None


def run_parallel(calls):
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(calls)) as executor:
        pending = {
            executor.submit(generate_with_retry, model, config, **kwargs): model
            for model, config, kwargs in calls
        }
        for future in concurrent.futures.as_completed(pending):
            model = pending[future]
            results[model] = future.result()
    return results


def main() -> None:
    api_key = os.environ.get("SEEDANCE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set SEEDANCE_API_KEY to run paid live verification")
    config = {
        "base_url": "https://api.seedance.nz",
        "api_key": api_key,
        "timeout": 90,
        "upload_timeout": 180,
        "poll_interval": 4,
        "max_poll_time": 2400,
    }
    first_frame = make_frame()

    with tempfile.TemporaryDirectory(prefix="zhenzhen_flux3_live_") as temp_dir:
        temp_path = Path(temp_dir)
        reference_video = temp_path / "reference.mp4"
        make_reference_video(reference_video)
        previous_output = os.environ.get("SEEDANCE_OUTPUT_DIR")
        os.environ["SEEDANCE_OUTPUT_DIR"] = temp_dir
        try:
            draft_sources = run_parallel(
                [
                    (
                        "flux-3-video-t2v",
                        config,
                        {"draft": True},
                    ),
                    (
                        "flux-3-video-global-t2v",
                        config,
                        {"draft": True},
                    ),
                ]
            )
            for model, result in draft_sources.items():
                if not result[2]:
                    raise RuntimeError(f"{model} returned no draft_cache")

            run_parallel(
                [
                    (
                        "flux-3-video-i2v",
                        config,
                        {"prompt": "Animate the reference image naturally", "image1": first_frame},
                    ),
                    (
                        "flux-3-video-global-i2v",
                        config,
                        {"prompt": "Animate the reference image naturally", "image1": first_frame},
                    ),
                    (
                        "flux-3-video-v2v",
                        config,
                        {"prompt": "Restyle the source while preserving motion", "input_video": str(reference_video)},
                    ),
                    (
                        "flux-3-video-global-v2v",
                        config,
                        {"prompt": "Restyle the source while preserving motion", "input_video": str(reference_video)},
                    ),
                ]
            )

            run_parallel(
                [
                    (
                        "flux-3-video-draft-enhance",
                        config,
                        {"prompt": "", "draft_cache": draft_sources["flux-3-video-t2v"][2]},
                    ),
                    (
                        "flux-3-video-global-draft-enhance",
                        config,
                        {"prompt": "", "draft_cache": draft_sources["flux-3-video-global-t2v"][2]},
                    ),
                ]
            )
        finally:
            if previous_output is None:
                os.environ.pop("SEEDANCE_OUTPUT_DIR", None)
            else:
                os.environ["SEEDANCE_OUTPUT_DIR"] = previous_output
    print("LIVE_CHECKS 8/8 SUCCESS", flush=True)


if __name__ == "__main__":
    main()
