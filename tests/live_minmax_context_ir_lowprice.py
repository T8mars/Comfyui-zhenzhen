"""Opt-in paid verification for the three MiniMax H3 Context IR models.

The API key is read only from SEEDANCE_API_KEY. Task identifiers, result text,
responses, and uploaded media URLs are not printed or written to tracked files.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

import torch


PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import seedance_low_price_nodes as nodes


def make_reference_image() -> torch.Tensor:
    axis = torch.linspace(0.0, 1.0, 512)
    horizontal = axis.view(1, 1, 512, 1).expand(1, 512, 512, 1)
    vertical = axis.view(1, 512, 1, 1).expand(1, 512, 512, 1)
    blue = torch.full_like(horizontal, 0.3)
    image = torch.cat((horizontal, vertical, blue), dim=-1)
    image[:, 150:362, 150:362, :] = torch.tensor([0.92, 0.72, 0.18])
    return image


def make_reference_video(path: pathlib.Path) -> None:
    ffmpeg = pathlib.Path(
        os.environ.get(
            "FFMPEG_PATH",
            r"F:\AI-T8-video-onekey\ffmpeg\bin\ffmpeg.exe",
        )
    )
    if not ffmpeg.is_file():
        raise RuntimeError("Set FFMPEG_PATH to an ffmpeg executable")
    subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x4f82c0:s=512x512:r=24:d=4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-y",
            str(path),
        ],
        check=True,
    )


def run_model(
    model: str,
    api_config: dict,
    image: torch.Tensor,
    video_path: pathlib.Path,
    audio: dict,
) -> None:
    kwargs = {
        "model": model,
        "prompt": (
            "Keep the subject consistent while creating clear natural movement and "
            "a smooth cinematic camera path"
        ),
        "seconds": "4",
        "ratio": "16:9",
        "api_config": api_config,
        "skip_error": False,
        "seed": 0,
    }
    if model == nodes.MINMAX_H3_CONTEXT_IR_IMAGE_MODEL:
        kwargs["image1"] = image
    elif model == nodes.MINMAX_H3_CONTEXT_IR_MULTIMODAL_MODEL:
        kwargs.update(
            {
                "ratio": "adaptive",
                "image1": image,
                "video1": str(video_path),
                "audio1": audio,
            }
        )

    result = nodes.Comfly_minmax_h3_context_ir_lowprice().enhance(**kwargs)
    result_text = result["result"][0]
    if not isinstance(result_text, str) or not result_text.strip():
        raise RuntimeError(f"{model} returned empty result_text")
    print(f"{model} SUCCESS result_chars={len(result_text)}", flush=True)


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
        "max_poll_time": 1800,
    }
    image = make_reference_image()
    audio = {
        "waveform": torch.zeros((1, 1, 16000 * 4), dtype=torch.float32),
        "sample_rate": 16000,
    }
    with tempfile.TemporaryDirectory(prefix="zhenzhen_context_ir_live_") as temp_dir:
        video_path = pathlib.Path(temp_dir) / "reference.mp4"
        make_reference_video(video_path)
        for model in nodes.MINMAX_H3_CONTEXT_IR_MODELS:
            run_model(model, api_config, image, video_path, audio)
    print("LIVE_CHECKS 3/3 SUCCESS", flush=True)


if __name__ == "__main__":
    main()
