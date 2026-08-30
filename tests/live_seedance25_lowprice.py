"""Opt-in paid live verification for all six Seedance 2.5 Standard models."""

from __future__ import annotations

import concurrent.futures
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

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
    width, height, fps, frame_count = 640, 360, 24.0, 48
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError("could not create live-test MP4")
    try:
        for index in range(frame_count):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            frame[:, :] = (72, 46, 28)
            x = 60 + int((width - 180) * index / (frame_count - 1))
            cv2.circle(frame, (x, height // 2), 55, (40, 205, 245), -1)
            writer.write(frame)
    finally:
        writer.release()
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("live-test MP4 is empty")


def make_audio() -> dict[str, Any]:
    sample_rate = 44100
    timeline = torch.arange(sample_rate * 4, dtype=torch.float32) / sample_rate
    waveform = (0.10 * torch.sin(2.0 * torch.pi * 220.0 * timeline)).view(1, 1, -1)
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
        raise RuntimeError(f"{model} omitted URL or task id")
    path = result_path(result[0])
    if path is None or not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"{model} returned no readable MP4")
    capture = cv2.VideoCapture(str(path))
    try:
        decoded, frame = capture.read()
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not decoded or frame is None or min(width, height, frame_count) <= 0 or fps <= 0:
            raise RuntimeError(f"{model} MP4 did not decode")
    finally:
        capture.release()
    print(
        f"{model} SUCCESS decode={width}x{height} fps={fps:.2f} frames={frame_count}",
        flush=True,
    )


def run_model(
    model: str,
    config: dict[str, Any],
    first_frame: torch.Tensor,
    last_frame: torch.Tensor,
    reference_video: Path,
    audio: dict[str, Any],
) -> tuple[Any, ...]:
    kwargs: dict[str, Any] = {
        "model": model,
        "prompt": "A white paper airplane glides through a sunlit greenhouse, smooth cinematic camera movement",
        "seconds": "4",
        "resolution": "480p",
        "ratio": "16:9",
        "generate_audio": True,
        "return_last_frame": True,
        "seed": -1,
        "api_config": config,
        "skip_error": False,
    }
    if model in nodes.SEEDANCE25_I2V_MODELS:
        kwargs.update({
            "prompt": "Move naturally from the first frame to the last frame while preserving the subject",
            "ratio": "adaptive",
            "return_last_frame": False,
            "image1": first_frame,
            "image2": last_frame,
        })
    elif model in nodes.SEEDANCE25_MULTI_MODELS:
        kwargs.update({
            "prompt": "Place @Image 1 in @Video 1 and synchronize the movement with @Audio 1 while preserving identity",
            "image1": first_frame,
            "video1": str(reference_video),
            "audio1": audio,
        })

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            result = nodes.Comfly_seedance25_standard_low_price().generate(**kwargs)
            validate_result(model, result)
            return result
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(8 * (attempt + 1))
    raise RuntimeError(
        f"{model} failed after 3 attempts ({type(last_error).__name__})"
    ) from None


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
    last_frame = make_frame(reverse=True)
    audio = make_audio()
    results: list[tuple[Any, ...]] = []
    live_only = os.environ.get("SEEDANCE25_LIVE_ONLY", "all").strip().lower()
    if live_only == "all":
        selected_models = list(nodes.SEEDANCE25_MODELS)
    elif live_only in {"t2v", "i2v", "multi"}:
        selected_models = [
            model for model in nodes.SEEDANCE25_MODELS if model.endswith(f"-{live_only}")
        ]
    elif live_only in nodes.SEEDANCE25_MODELS:
        selected_models = [live_only]
    else:
        raise SystemExit(
            "SEEDANCE25_LIVE_ONLY must be all, t2v, i2v, multi, or one exact model"
        )

    with tempfile.TemporaryDirectory(prefix="zhenzhen_seedance25_live_") as temp_dir:
        temp_path = Path(temp_dir)
        reference_video = temp_path / "reference.mp4"
        make_reference_video(reference_video)
        previous_output = os.environ.get("SEEDANCE_OUTPUT_DIR")
        os.environ["SEEDANCE_OUTPUT_DIR"] = temp_dir
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(selected_models)) as executor:
                futures = {
                    executor.submit(
                        run_model,
                        model,
                        config,
                        first_frame,
                        last_frame,
                        reference_video,
                        audio,
                    ): model
                    for model in selected_models
                }
                for future in concurrent.futures.as_completed(futures):
                    results.append(future.result())
        finally:
            results.clear()
            if previous_output is None:
                os.environ.pop("SEEDANCE_OUTPUT_DIR", None)
            else:
                os.environ["SEEDANCE_OUTPUT_DIR"] = previous_output
    print(f"LIVE_CHECKS {len(selected_models)}/{len(selected_models)} SUCCESS", flush=True)


if __name__ == "__main__":
    main()
