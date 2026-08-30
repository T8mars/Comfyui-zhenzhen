"""Opt-in paid verification for all eight Wan 3.0 video models."""

from __future__ import annotations

import os
import sys
import tempfile
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
    axis = torch.linspace(0.0, 1.0, width)
    if reverse:
        axis = torch.flip(axis, dims=[0])
    red = axis.view(1, 1, width, 1).expand(1, height, width, 1)
    green = torch.linspace(0.15, 0.85, height).view(
        1, height, 1, 1
    ).expand(1, height, width, 1)
    blue = torch.full_like(red, 0.30)
    image = torch.cat((red, green, blue), dim=-1)
    image[:, 110:250, 250:390, :] = torch.tensor([0.95, 0.78, 0.18])
    return image


def make_reference_video(path: Path) -> None:
    width, height, fps, frame_count = 640, 360, 24, 48
    container = av.open(str(path), mode="w")
    stream = container.add_stream("libx264", rate=fps)
    stream.width = width
    stream.height = height
    stream.pix_fmt = "yuv420p"
    try:
        for index in range(frame_count):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            frame[:, :] = (70, 42, 25)
            x = 70 + int((width - 140) * index / (frame_count - 1))
            cv2.circle(frame, (x, height // 2), 48, (30, 205, 245), -1)
            video_frame = av.VideoFrame.from_ndarray(frame, format="rgb24")
            for packet in stream.encode(video_frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("Wan 3.0 reference MP4 is empty")


def make_audio() -> dict[str, Any]:
    sample_rate = 44100
    timeline = torch.arange(sample_rate * 2, dtype=torch.float32) / sample_rate
    waveform = (0.10 * torch.sin(2.0 * torch.pi * 220.0 * timeline)).view(
        1, 1, -1
    )
    return {"waveform": waveform, "sample_rate": sample_rate}


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
    if not result[1] or not result[2]:
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
        if (
            not decoded
            or frame is None
            or min(width, height, frames) <= 0
            or fps <= 0
        ):
            raise RuntimeError(f"{model} MP4 did not decode")
    finally:
        capture.release()
    print(
        f"{model} SUCCESS decode={width}x{height} "
        f"fps={fps:.2f} frames={frames}",
        flush=True,
    )


def run_model(
    model: str,
    config: dict[str, Any],
    first_frame: torch.Tensor,
    last_frame: torch.Tensor,
    reference_video: Path,
    audio: dict[str, Any],
) -> None:
    kwargs: dict[str, Any] = {
        "model": model,
        "prompt": "Keep the subject consistent with smooth cinematic movement",
        "seconds": "2",
        "resolution": "480P",
        "ratio": "adaptive",
        "generate_audio": False,
        "enable_thinking": model in nodes.WAN30_THINKING_MODELS,
        "file_url": "",
        "link_url": "",
        "seed": 1,
        "api_config": config,
        "skip_error": False,
    }
    if model in nodes.WAN30_I2V_MODELS:
        kwargs.update({"image1": first_frame, "image2": last_frame})
    elif "-prime-r2v" in model:
        kwargs.update(
            {
                "prompt": (
                    "Use Image 1 as the subject reference and generate subtle, "
                    "natural motion while preserving identity"
                ),
                "image1": first_frame,
            }
        )
    else:
        kwargs.update(
            {
                "prompt": (
                    "Image 1 enters the scene in Video 1 while the motion rhythm "
                    "follows Audio 1; preserve subject identity"
                ),
                "image1": first_frame,
                "video1": str(reference_video),
                "audio1": audio,
            }
        )
    result = nodes.Comfly_wan_3_0_video_lowprice().generate(**kwargs)
    validate_result(model, result)


def main() -> None:
    api_key = os.environ.get("SEEDANCE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set SEEDANCE_API_KEY to run paid live verification")
    selected = os.environ.get("WAN30_LIVE_ONLY", "all").strip()
    if selected == "all":
        models = list(nodes.WAN30_MODELS)
    elif selected == "prime":
        models = [model for model in nodes.WAN30_MODELS if "-prime-" in model]
    else:
        models = [selected]
    if any(model not in nodes.WAN30_MODELS for model in models):
        raise SystemExit(
            "WAN30_LIVE_ONLY must be all, prime, or one exact Wan 3.0 model"
        )

    config = {
        "base_url": "https://api.seedance.nz",
        "api_key": api_key,
        "timeout": 90,
        "upload_timeout": 180,
        "poll_interval": 4,
        "max_poll_time": 2400,
    }
    first_frame = make_frame()
    last_frame = make_frame(reverse=True)
    audio = make_audio()
    with tempfile.TemporaryDirectory(prefix="zhenzhen_wan30_live_") as temp_dir:
        reference_video = Path(temp_dir) / "reference.mp4"
        make_reference_video(reference_video)
        previous_output = os.environ.get("SEEDANCE_OUTPUT_DIR")
        os.environ["SEEDANCE_OUTPUT_DIR"] = temp_dir
        try:
            for model in models:
                run_model(
                    model,
                    config,
                    first_frame,
                    last_frame,
                    reference_video,
                    audio,
                )
        finally:
            if previous_output is None:
                os.environ.pop("SEEDANCE_OUTPUT_DIR", None)
            else:
                os.environ["SEEDANCE_OUTPUT_DIR"] = previous_output
    print(f"LIVE_CHECKS {len(models)}/{len(models)} SUCCESS", flush=True)


if __name__ == "__main__":
    main()
