"""Opt-in real node tests; credentials are accepted only from process environment."""

import contextlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from unittest.mock import patch

import av
import numpy as np
from PIL import Image, ImageDraw
import torch

from nov08_fixture import api, image, nodes, kling, flash, module


def video_details(value):
    data, extension = api.video_to_upload_bytes(value)
    with av.open(io.BytesIO(data)) as container:
        stream = container.streams.video[0]
        count = 0
        for frame in container.decode(video=0):
            assert frame.width > 0 and frame.height > 0
            count += 1
        assert count > 1
        return {"width": stream.width, "height": stream.height, "frames": count, "bytes": len(data)}


def main():
    if os.environ.get("RUN_LIVE_NOV08") != "1":
        raise SystemExit("RUN_LIVE_NOV08=1 is required")
    key = os.environ.get("SEEDANCE_API_KEY", "").strip()
    if not key:
        raise SystemExit("SEEDANCE_API_KEY is required")
    visible = sys.stdout
    def report(value):
        visible.write(json.dumps(value) + "\n")
        visible.flush()
    config = {"base_url": "https://api.seedance.nz", "api_key": key}
    module("Comfly")
    tile = Image.new("RGB", (640, 640), "#247d91")
    draw = ImageDraw.Draw(tile)
    draw.rectangle((220, 180, 420, 460), fill="white")
    tensor = torch.from_numpy(np.asarray(tile, dtype=np.float32).copy() / 255).unsqueeze(0)
    only = set(os.environ.get("NOV08_CASES", "").split(",")) - {""}
    cases = ["g26-2k", "g26-4k", "g26-gif", "kling-text", "kling-image", "kling-video", "omni-text", "omni-image", "omni-video"]
    failed, last_videos = False, {}
    import folder_paths
    with tempfile.TemporaryDirectory(prefix="zhenzhen-nov08-live-") as folder, patch.object(folder_paths, "get_output_directory", return_value=folder):
        clip = Path(folder) / "reference.mp4"
        with av.open(str(clip), "w") as container:
            stream = container.add_stream("libx264", rate=24)
            stream.width, stream.height, stream.pix_fmt = 1280, 720, "yuv420p"
            for index in range(120):
                frame_image = Image.new("RGB", (1280, 720), "#e3f5ed")
                painter = ImageDraw.Draw(frame_image)
                offset = index // 4
                painter.rounded_rectangle((530, 100, 750, 300), 30, fill="#2586c8")
                painter.rectangle((565, 160, 715, 240), fill="#17232b")
                painter.ellipse((585, 185, 605, 205), fill="white")
                painter.ellipse((675, 185, 695, 205), fill="white")
                painter.rounded_rectangle((550, 320, 730, 570), 20, fill="#2586c8")
                painter.rectangle((470, 350 - offset, 520, 530 - offset), fill="#2586c8")
                painter.rectangle((760, 350, 810, 530), fill="#2586c8")
                painter.rectangle((565, 570, 625, 665), fill="#17232b")
                painter.rectangle((655, 570, 715, 665), fill="#17232b")
                array = np.asarray(frame_image).copy()
                for packet in stream.encode(av.VideoFrame.from_ndarray(array, format="rgb24")):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
        for case in cases:
            if only and case not in only:
                continue
            report({"case": case, "phase": "starting"})
            started = time.monotonic()
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    if case.startswith("g26"):
                        values = {"prompt": "A white ceramic teapot on a light gray table, studio photograph, clean composition.",
                            "resolution": case.split("-")[1] if case != "g26-gif" else "1k", "quality": "high", "filename_prefix": case}
                        if case == "g26-gif":
                            values.update(mode="gif", prompt="A white ball slowly bounces in a blue studio, seamless looping GIF.")
                        result = nodes.T8ZhenzhenImageG26().generate(api_config=config, **values)["result"]
                        assert len(result) == 8 and result[1] and result[2] and torch.isfinite(result[0]).all()
                        with Image.open(result[4]) as saved:
                            frames = getattr(saved, "n_frames", 1)
                            for index in range(frames):
                                saved.seek(index)
                                saved.load()
                            if case == "g26-gif":
                                assert saved.format == "GIF" and frames > 1
                        details = {"shape": list(result[0].shape), "bytes": Path(result[4]).stat().st_size, "frames": frames}
                    else:
                        family, mode = case.split("-")
                        node = kling.T8ZhenzhenKling4Omni() if family == "kling" else flash.T8ZhenzhenOmni12FlashLowPrice()
                        values = {"prompt": "A white geometric sculpture rotates slowly in a clean blue studio.", "seconds": 3,
                            "resolution": "720p" if family == "kling" else "360p"}
                        if family == "kling":
                            values["model"] = flash.KLING_MODEL
                        if mode == "image":
                            values["image1"] = tensor
                        elif mode == "video":
                            values["video1"] = last_videos.get(family, str(clip))
                        result = node.generate(api_config=config, **values)
                        assert len(result) == 4 and result[1] and result[2]
                        details = video_details(result[0])
                        last_videos[family] = result[0]
                report({"case": case, "status": "PASS", "seconds_elapsed": round(time.monotonic() - started, 1), **details})
            except Exception as error:
                message = re.sub(r"https?://\S+|sk-[A-Za-z0-9]+|task_[A-Za-z0-9]+", "<omitted>", str(error).replace(key, "<key>"))
                report({"case": case, "status": "FAIL", "error": message[:500]})
                failed = True
    report({"status": "FAIL" if failed else "PASS", "temporary_media_cleaned": True})
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
