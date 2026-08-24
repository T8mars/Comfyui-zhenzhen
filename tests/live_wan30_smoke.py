"""Manual real-API smoke test for the four Wan 3.0 node paths.

The API key is read without echo and is never written to disk. Runtime task
identifiers and result URLs are intentionally not printed.
"""

from __future__ import annotations

import getpass
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seedance_low_price_nodes as nodes


REFERENCE_IMAGE = Path(
    r"F:\AI-T8-video-onekey\ComfyUI\input\example.png"
)
REFERENCE_VIDEO = Path(
    r"F:\AI-T8-video-onekey\ComfyUI\input\404770867-bf3b8970-ca7b-447f-8301-72dfe028055b (1).mp4"
)


def _image_pair():
    image = Image.open(REFERENCE_IMAGE).convert("RGB")
    array = np.asarray(image, dtype=np.float32) / 255.0
    first = array[np.newaxis, ...]
    last = np.flip(array, axis=1).copy()[np.newaxis, ...]
    return first, last


def _audio():
    sample_rate = 16000
    seconds = 4
    timeline = np.arange(sample_rate * seconds, dtype=np.float32) / sample_rate
    waveform = (0.04 * np.sin(2 * np.pi * 220 * timeline))[None, None, :]
    return {"waveform": waveform, "sample_rate": sample_rate}


def _video_path(video):
    if isinstance(video, str):
        return Path(video)
    if hasattr(video, "get_stream_source"):
        source = video.get_stream_source()
        if isinstance(source, str):
            return Path(source)
    for attribute in ("path", "file_path"):
        value = getattr(video, attribute, None)
        if isinstance(value, str):
            return Path(value)
    raise RuntimeError("node result did not expose a local video path")


def _probe(path: Path):
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height:format=duration",
        "-of",
        "default=noprint_wrappers=1",
        str(path),
    ]
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    fields = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key] = value
    return fields


def _sanitize_error(exc: Exception) -> str:
    message = str(exc)
    message = re.sub(r"https?://\S+", "<url>", message)
    message = re.sub(
        r"(?i)\b(?:task[_-]?[a-z0-9_-]{8,}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\b",
        "<id>",
        message,
    )
    return message[:500]


def main() -> int:
    api_key = getpass.getpass("Seedance API key: ").strip()
    first, last = _image_pair()
    audio = _audio()
    failures = []
    with tempfile.TemporaryDirectory(prefix="wan30-live-") as output_dir:
        os.environ["SEEDANCE_OUTPUT_DIR"] = output_dir
        os.environ["SEEDANCE_POLL_INTERVAL"] = "2"
        config = {"base_url": nodes.DEFAULT_BASE_URL, "api_key": api_key}
        api_key = ""

        requested_models = sys.argv[1:] or nodes.WAN30_MODELS
        unknown = [model for model in requested_models if model not in nodes.WAN30_MODELS]
        if unknown:
            raise ValueError("unsupported model filter")
        for model in requested_models:
            kwargs = {
                "model": model,
                "prompt": (
                    "主体保持一致，镜头平稳推进，动作自然连续"
                    if model.endswith("-i2v")
                    else "Image 1 中的主体进入 Video 1 的场景，动作节奏跟随 Audio 1"
                ),
                "seconds": "2",
                "resolution": "480P",
                "ratio": "adaptive",
                "generate_audio": False,
                "enable_thinking": model.startswith("wan-3.0-global-"),
                "file_url": "",
                "link_url": "",
                "seed": 1,
                "api_config": config,
            }
            if model.endswith("-i2v"):
                kwargs.update({"image1": first, "image2": last})
            else:
                kwargs.update(
                    {
                        "image1": first,
                        "video1": str(REFERENCE_VIDEO),
                        "audio1": audio,
                    }
                )
            try:
                video, _video_url, _task_id, _response = (
                    nodes.Comfly_wan_3_0_video_lowprice().generate(**kwargs)
                )
                path = _video_path(video)
                header = path.read_bytes()[:64]
                if len(header) < 12 or b"ftyp" not in header[4:32]:
                    raise RuntimeError("result failed MP4 header validation")
                probe = _probe(path)
                print(
                    f"{model} OK bytes={path.stat().st_size} "
                    f"codec={probe.get('codec_name', '')} "
                    f"size={probe.get('width', '')}x{probe.get('height', '')} "
                    f"duration={probe.get('duration', '')}"
                )
            except Exception as exc:
                failures.append(model)
                print(
                    f"{model} FAIL type={type(exc).__name__} "
                    f"message={_sanitize_error(exc)}"
                )

        config["api_key"] = ""
        os.environ.pop("SEEDANCE_OUTPUT_DIR", None)
        os.environ.pop("SEEDANCE_POLL_INTERVAL", None)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
