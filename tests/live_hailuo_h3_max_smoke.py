"""Credential-safe live smoke test for both Hailuo H3 Max node paths."""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seedance_low_price_nodes as nodes


KEY_PATTERN = re.compile(r"(?i)\bsk-[A-Za-z0-9_-]+\b")
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


def _safe_error(error: BaseException) -> str:
    message = KEY_PATTERN.sub("[REDACTED_API_KEY]", str(error))
    return URL_PATTERN.sub("[REDACTED_URL]", message)[:500]


def _test_frame() -> np.ndarray:
    height = width = 512
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)
    grid_x, grid_y = np.meshgrid(x, y)
    image = np.stack(
        [grid_x, grid_y, 0.25 + 0.5 * (1.0 - grid_x)],
        axis=-1,
    )
    return image[np.newaxis, ...]


def _result_path(value) -> Path:
    if isinstance(value, str):
        return Path(value)
    for name in ("path", "file_path"):
        candidate = getattr(value, name, None)
        if isinstance(candidate, str):
            return Path(candidate)
    source = getattr(value, "get_stream_source", lambda: None)()
    if isinstance(source, str):
        return Path(source)
    raise RuntimeError("node returned a video object without a readable local path")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=nodes.DEFAULT_BASE_URL)
    args = parser.parse_args()
    api_key = getpass.getpass("Seedance API key: ")
    config = {"base_url": args.base_url, "api_key": api_key}
    cases = (
        {
            "model": nodes.HAILUO_H3_MAX_T2V_MODEL,
            "prompt": (
                "A white paper airplane glides across a quiet sunlit studio, "
                "gentle cinematic camera movement, natural continuous motion"
            ),
        },
        {
            "model": nodes.HAILUO_H3_MAX_I2V_MODEL,
            "prompt": (
                "The colors shimmer softly while the camera moves forward, "
                "preserve the composition and maintain smooth natural motion"
            ),
            "image1": _test_frame(),
        },
    )
    with tempfile.TemporaryDirectory(prefix="hailuo_h3_max_live_") as output_dir:
        os.environ["SEEDANCE_OUTPUT_DIR"] = output_dir
        for case in cases:
            model = case["model"]
            try:
                result = nodes.Comfly_hailuo_h3_max_video_lowprice().generate(
                    seconds="5",
                    resolution="480P",
                    ratio="16:9",
                    api_config=config,
                    skip_error=False,
                    **case,
                )
                path = _result_path(result[0])
                nodes._validate_mp4_file(str(path))
                print(f"LIVE_OK model={model} bytes={path.stat().st_size}")
            except Exception as error:
                print(f"LIVE_FAILED model={model} error={_safe_error(error)}")
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
