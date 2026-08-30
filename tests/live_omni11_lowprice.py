"""Opt-in paid validation for every Omni 1.1 Flash Lowprice mode."""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import types
from pathlib import Path

import cv2
import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "zhenzhen_omni11_live_package"
package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(PLUGIN_ROOT)]
sys.modules[PACKAGE_NAME] = package

advanced = importlib.import_module(f"{PACKAGE_NAME}.aug22_low_price_nodes")
legacy = importlib.import_module(f"{PACKAGE_NAME}.seedance_low_price_nodes")


def require_config() -> dict:
    if os.environ.get("RUN_LIVE_OMNI11", "") != "1":
        raise SystemExit("Set RUN_LIVE_OMNI11=1 to run paid API validation.")
    api_key = os.environ.get("SEEDANCE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("SEEDANCE_API_KEY is required.")
    return {"base_url": "https://api.seedance.nz", "api_key": api_key}


def synthetic_image(color: tuple[float, float, float]) -> torch.Tensor:
    image = torch.zeros((1, 360, 640, 3), dtype=torch.float32)
    image[..., 0] = color[0]
    image[..., 1] = color[1]
    image[..., 2] = color[2]
    image[:, 90:270, 230:410, :] = torch.tensor([0.95, 0.95, 0.95])
    return image


def validate_video(value, label: str) -> dict:
    data = legacy.video_to_mp4_bytes(value)
    if len(data) < 1024:
        raise AssertionError(f"{label}: generated video is unexpectedly small")
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
        handle.write(data)
        path = Path(handle.name)
    try:
        capture = cv2.VideoCapture(str(path))
        ok, frame = capture.read()
        details = {
            "width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": round(float(capture.get(cv2.CAP_PROP_FPS)), 3),
            "frames": int(capture.get(cv2.CAP_PROP_FRAME_COUNT)),
            "bytes": len(data),
        }
        capture.release()
        if not ok or frame is None or details["frames"] <= 0:
            raise AssertionError(f"{label}: downloaded MP4 could not be decoded")
        return details
    finally:
        path.unlink(missing_ok=True)


def remove_result_file(result) -> None:
    video = result[0]
    source = video if isinstance(video, str) else video.get_stream_source()
    if isinstance(source, str):
        Path(source).unlink(missing_ok=True)


def run() -> None:
    config = require_config()
    node = advanced.Comfly_zhenzhen_video_g_omni_1_1_flash_lowprice()
    common = {
        "prompt": "a white geometric sculpture rotates slowly in a clean blue studio",
        "seconds": "4",
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "nsfw_check": False,
        "api_config": config,
    }
    image1 = synthetic_image((0.10, 0.30, 0.65))
    image2 = synthetic_image((0.65, 0.20, 0.15))
    image3 = synthetic_image((0.15, 0.55, 0.25))
    results = []
    try:
        text_result = node.generate(mode="text", **common)
        results.append(text_result)
        print("omni11 text:", validate_video(text_result[0], "text"))

        frame_result = node.generate(mode="frame", image1=image1, **common)
        results.append(frame_result)
        print("omni11 frame:", validate_video(frame_result[0], "frame"))

        images_result = node.generate(
            mode="reference_images",
            image1=image1,
            image2=image2,
            image3=image3,
            **common,
        )
        results.append(images_result)
        print(
            "omni11 reference_images:",
            validate_video(images_result[0], "reference_images"),
        )

        video_result = node.generate(
            mode="reference_video",
            input_video=text_result[0],
            **common,
        )
        results.append(video_result)
        print(
            "omni11 reference_video:",
            validate_video(video_result[0], "reference_video"),
        )
    finally:
        for result in results:
            remove_result_file(result)
    print("omni11: all four paid API modes completed and decoded")


if __name__ == "__main__":
    run()
