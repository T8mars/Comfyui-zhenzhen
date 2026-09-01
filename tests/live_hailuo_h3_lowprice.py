"""Opt-in paid verification for domestic/global Hailuo H3 models."""

from __future__ import annotations

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


def console_safe(message: str) -> str:
    encoding = sys.stdout.encoding or "utf-8"
    return message.encode(encoding, errors="replace").decode(encoding)


def make_frame(reverse: bool = False) -> torch.Tensor:
    axis = torch.linspace(0.0, 1.0, 768)
    if reverse:
        axis = torch.flip(axis, dims=[0])
    horizontal = axis.view(1, 1, 768, 1).expand(1, 768, 768, 1)
    vertical = axis.view(1, 768, 1, 1).expand(1, 768, 768, 1)
    blue = torch.full_like(horizontal, 0.28)
    image = torch.cat((horizontal, vertical, blue), dim=-1)
    image[:, 230:538, 230:538, :] = torch.tensor([0.94, 0.78, 0.18])
    return image


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
        raise RuntimeError("Hailuo H3 reference MP4 is empty")


def make_audio() -> dict[str, Any]:
    sample_rate = 44100
    timeline = torch.arange(sample_rate * 5, dtype=torch.float32) / sample_rate
    waveform = (0.12 * torch.sin(2.0 * torch.pi * 220.0 * timeline)).view(1, 1, -1)
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
        if not decoded or frame is None or min(width, height, frames) <= 0 or fps <= 0:
            raise RuntimeError(f"{model} MP4 did not decode")
    finally:
        capture.release()
    print(
        f"{model} SUCCESS decode={width}x{height} fps={fps:.2f} frames={frames}",
        flush=True,
    )


def run_model(
    model: str,
    config: dict[str, Any],
    first_frame: torch.Tensor,
    last_frame: torch.Tensor,
    reference_video: Path,
    audio: dict[str, Any],
    multi_media: str,
) -> tuple[Any, ...]:
    kwargs: dict[str, Any] = {
        "model": model,
        "prompt": "A white paper airplane glides through a sunlit greenhouse with smooth cinematic camera movement",
        "seconds": "5",
        "resolution": "768P",
        "ratio": "16:9",
        "api_config": config,
        "skip_error": False,
    }
    if model in nodes.HAILUO_H3_I2V_MODELS:
        kwargs.update(
            {
                "prompt": "Move naturally from the first frame to the last while preserving the subject",
                "ratio": "adaptive",
                "image1": first_frame,
                "image2": last_frame,
            }
        )
    elif model in nodes.HAILUO_H3_MULTI_MODELS:
        references = []
        if multi_media in {"all", "image"}:
            kwargs["image1"] = first_frame
            references.append("@Image 1")
        if multi_media in {"all", "video"}:
            kwargs["video1"] = str(reference_video)
            references.append("@Video 1")
        if multi_media in {"all", "audio"}:
            kwargs["audio1"] = audio
            references.append("@Audio 1")
        kwargs["prompt"] = (
            "Create a coherent cinematic shot using "
            + ", ".join(references)
            + " while preserving subject identity"
        )

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            result = nodes.Comfly_hailuo_h3_video_lowprice().generate(**kwargs)
            validate_result(model, result)
            return result
        except Exception as exc:
            last_error = exc
            safe_message = console_safe(
                str(exc).replace(config["api_key"], "[REDACTED_API_KEY]")
            )
            print(
                f"{model} attempt {attempt + 1} failed: "
                f"{type(exc).__name__}: {safe_message}",
                flush=True,
            )
            if attempt < 2:
                time.sleep(8 * (attempt + 1))
    safe_message = console_safe(
        str(last_error).replace(config["api_key"], "[REDACTED_API_KEY]")
    )
    raise RuntimeError(
        f"{model} failed after 3 attempts ({type(last_error).__name__}: "
        f"{safe_message})"
    ) from None


def selected_models() -> list[str]:
    selection = os.environ.get("HAILUO_H3_LIVE_ONLY", "global").strip().lower()
    if selection == "all":
        return list(nodes.HAILUO_H3_MODELS)
    if selection == "global":
        return [model for model in nodes.HAILUO_H3_MODELS if "-global-" in model]
    if selection == "domestic":
        return [model for model in nodes.HAILUO_H3_MODELS if "-global-" not in model]
    if selection in nodes.HAILUO_H3_MODELS:
        return [selection]
    raise SystemExit(
        "HAILUO_H3_LIVE_ONLY must be all, global, domestic, or one exact model"
    )


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
    models = selected_models()
    multi_media = os.environ.get("HAILUO_H3_MULTI_MEDIA", "all").strip().lower()
    if multi_media not in {"all", "image", "video", "audio"}:
        raise SystemExit(
            "HAILUO_H3_MULTI_MEDIA must be all, image, video, or audio"
        )
    first_frame = make_frame()
    last_frame = make_frame(reverse=True)
    audio = make_audio()

    with tempfile.TemporaryDirectory(prefix="zhenzhen_hailuo_h3_live_") as temp_dir:
        temp_path = Path(temp_dir)
        reference_video = temp_path / "reference.mp4"
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
                    multi_media,
                )
        finally:
            if previous_output is None:
                os.environ.pop("SEEDANCE_OUTPUT_DIR", None)
            else:
                os.environ["SEEDANCE_OUTPUT_DIR"] = previous_output
    print(f"LIVE_CHECKS {len(models)}/{len(models)} SUCCESS", flush=True)


if __name__ == "__main__":
    main()
