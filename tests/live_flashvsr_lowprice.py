"""Opt-in paid live verification for the FlashVSR low-price node."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ONEKEY_ROOT = PLUGIN_ROOT.parents[2]
sys.path.insert(0, str(PLUGIN_ROOT))

import seedance_low_price_nodes as nodes


def media_path(value: Any) -> Path | None:
    if isinstance(value, str):
        return Path(value)
    if isinstance(value, dict):
        path = value.get("file_path") or value.get("path")
        return Path(path) if isinstance(path, str) else None
    for attribute in ("file_path", "path"):
        path = getattr(value, attribute, None)
        if isinstance(path, str):
            return Path(path)
    if hasattr(value, "get_stream_source"):
        source = value.get_stream_source()
        if isinstance(source, str):
            return Path(source)
        name = getattr(source, "name", None)
        if isinstance(name, str):
            return Path(name)
    return None


def make_input_video(path: Path, ffmpeg: Path) -> None:
    subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=854x480:rate=24",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )


def probe_video(path: Path, ffprobe: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,nb_frames,duration",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(completed.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError("FlashVSR output contains no video stream")
    stream = streams[0]
    if min(int(stream.get("width", 0)), int(stream.get("height", 0))) <= 0:
        raise RuntimeError("FlashVSR output has invalid dimensions")
    return data


def main() -> None:
    api_key = os.environ.get("SEEDANCE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set SEEDANCE_API_KEY to run paid live verification")

    ffmpeg = Path(os.environ.get(
        "SEEDANCE_FFMPEG",
        ONEKEY_ROOT / "ffmpeg" / "bin" / "ffmpeg.exe",
    ))
    ffprobe = ffmpeg.with_name("ffprobe.exe")
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise SystemExit("Bundled ffmpeg/ffprobe was not found")

    config = {
        "base_url": "https://api.seedance.nz",
        "api_key": api_key,
        "timeout": 90,
        "upload_timeout": 180,
        "poll_interval": 4,
        "max_poll_time": 2400,
    }
    with tempfile.TemporaryDirectory(prefix="zhenzhen_flashvsr_live_") as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / "flashvsr_input_854x480_3s.mp4"
        make_input_video(input_path, ffmpeg)
        previous_output = os.environ.get("SEEDANCE_OUTPUT_DIR")
        os.environ["SEEDANCE_OUTPUT_DIR"] = temp_dir
        try:
            result = nodes.Comfly_fashvsr_video_upscale_lowprice().generate(
                video_url="",
                input_video=str(input_path),
                api_config=config,
                skip_error=False,
                seed=0,
            )
            output_path = media_path(result[0])
            if output_path is None or not output_path.is_file():
                raise RuntimeError("FlashVSR node did not return a local MP4")
            if not result[1] or not result[2]:
                raise RuntimeError("FlashVSR node omitted result URL or task ID")
            probe = probe_video(output_path, ffprobe)
            stream = probe["streams"][0]
            media_format = probe.get("format") or {}
            print(
                "FlashVSR_video_upscale SUCCESS "
                f"codec={stream.get('codec_name')} "
                f"size={stream.get('width')}x{stream.get('height')} "
                f"frames={stream.get('nb_frames')} "
                f"duration={media_format.get('duration')} "
                f"bytes={media_format.get('size')}",
                flush=True,
            )
        finally:
            if previous_output is None:
                os.environ.pop("SEEDANCE_OUTPUT_DIR", None)
            else:
                os.environ["SEEDANCE_OUTPUT_DIR"] = previous_output


if __name__ == "__main__":
    main()
