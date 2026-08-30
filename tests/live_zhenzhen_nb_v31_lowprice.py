"""Opt-in paid live verification for Zhenzhen Image NB and Video V3.1 Lite."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import seedance_low_price_nodes as nodes


IMAGE_CASES = (
    (nodes.ZHENZHEN_IMAGE_NB_FLASH_MODEL, "1k"),
    (nodes.ZHENZHEN_IMAGE_NB_2_MODEL, "0.5k"),
    (nodes.ZHENZHEN_IMAGE_NB_2_LITE_MODEL, "1k"),
    (nodes.ZHENZHEN_IMAGE_NB_PRO_MODEL, "1k"),
)


def assert_image(result) -> None:
    image = result[0]
    if not isinstance(image, torch.Tensor) or image.ndim != 4 or image.shape[-1] != 3:
        raise RuntimeError("live image result is not a ComfyUI IMAGE tensor")
    if not result[1] or not result[2]:
        raise RuntimeError("live image result omitted its URL or task id")


def make_reference() -> torch.Tensor:
    image = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
    image[:, :, :, 0] = 0.82
    image[:, 12:52, 12:52, 1] = 0.65
    image[:, 20:44, 20:44, 2] = 0.95
    return image


def run_image_checks(config) -> None:
    node = nodes.Comfly_zhenzhen_image_nb_lowprice()
    reference = make_reference()
    for model, resolution in IMAGE_CASES:
        text_result = node.generate_image(
            model=model,
            prompt="a small cobalt ceramic cup on a clean white studio table, soft daylight",
            resolution=resolution,
            size="1:1",
            n=1,
            api_config=config,
        )
        assert_image(text_result)
        print(f"{model} text_to_image SUCCESS", flush=True)

        edit_result = node.generate_image(
            model=model,
            prompt="keep the simple geometric subject, replace the background with pale gray paper",
            resolution=resolution,
            size="1:1",
            n=1,
            api_config=config,
            image1=reference,
        )
        assert_image(edit_result)
        print(f"{model} image_edit SUCCESS", flush=True)


def run_video_check(config) -> None:
    result = nodes.Comfly_zhenzhen_video_v31_lowprice().generate(
        model=nodes.ZHENZHEN_VIDEO_V31_LITE_MODEL,
        prompt="a white paper airplane gliding through warm sunrise clouds, smooth camera movement",
        seconds="8",
        resolution="720p",
        ratio="16:9",
        api_config=config,
    )
    video = result[0]
    if not result[1] or not result[2]:
        raise RuntimeError("live video result omitted its URL or task id")
    if isinstance(video, str):
        path = Path(video)
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError("live video download is missing or empty")
    elif video is None:
        raise RuntimeError("live video result is empty")
    print("zhenzhen-video-v31-lite text_to_video SUCCESS", flush=True)


def main() -> None:
    api_key = os.environ.get("SEEDANCE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set SEEDANCE_API_KEY to run paid live verification")
    config = {
        "base_url": "https://api.seedance.nz",
        "api_key": api_key,
        "timeout": 90,
        "upload_timeout": 180,
        "poll_interval": 3,
        "max_poll_time": 1800,
    }
    with tempfile.TemporaryDirectory(prefix="zhenzhen_nb_v31_live_") as output_dir:
        previous_output = os.environ.get("SEEDANCE_OUTPUT_DIR")
        os.environ["SEEDANCE_OUTPUT_DIR"] = output_dir
        try:
            run_image_checks(config)
            run_video_check(config)
        finally:
            if previous_output is None:
                os.environ.pop("SEEDANCE_OUTPUT_DIR", None)
            else:
                os.environ["SEEDANCE_OUTPUT_DIR"] = previous_output
    print("LIVE_CHECKS 9/9 SUCCESS", flush=True)


if __name__ == "__main__":
    main()
