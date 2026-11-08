"""Opt-in Workshop tests; keys and runtime results never enter example files."""

import contextlib
import io
import json
import os
import re
import sys
import time
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw
import torch

from nov08_fixture import module

nodes = module("gpt_image_26_workshop_nodes")


def reference(color="#237b91"):
    image = Image.new("RGB", (640, 640), "#f1f2f3")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((190, 210, 410, 460), 32, fill=color)
    draw.ellipse((365, 240, 510, 420), outline=color, width=36)
    draw.polygon(((200, 250), (90, 220), (190, 350)), fill=color)
    draw.rectangle((180, 190, 420, 225), fill=color)
    draw.ellipse((270, 145, 330, 205), fill=color)
    return torch.from_numpy(np.asarray(image, dtype=np.float32).copy() / 255).unsqueeze(0)


def main():
    if os.environ.get("RUN_LIVE_GPT26_WORKSHOP") != "1":
        raise SystemExit("RUN_LIVE_GPT26_WORKSHOP=1 is required")
    key = os.environ.get("ZHENZHEN_WORKSHOP_API_KEY", "").strip()
    if not key:
        raise SystemExit("ZHENZHEN_WORKSHOP_API_KEY is required")
    only = set(os.environ.get("GPT26_CASES", "").split(",")) - {""}
    visible, failed = sys.stdout, False
    def report(value):
        visible.write(json.dumps(value) + "\n")
        visible.flush()
    for index, model in enumerate(nodes.MODELS):
        size = "3840x2160" if model.endswith("-4k") else "2048x2048" if model.endswith("-2k") else "1024x1024"
        for mode in ("text", "edit"):
            label = model + ":" + mode
            if only and label not in only:
                continue
            values = {"model": model, "size": size, "n": 1, "quality": "low", "complexity": ("low", "medium", "high")[index % 3],
                "async_mode": True, "poll_interval": 3, "max_poll_time": 900,
                "prompt": "A single blue ceramic teapot on a light gray studio table, soft light, clean product photograph."}
            if mode == "edit":
                values.update(image1=reference(), prompt="Change the blue teapot to red ceramic. Preserve its silhouette and keep the light gray background.")
                if index == 0:
                    count = int(os.environ.get("GPT26_REFERENCE_COUNT", str(nodes.MAX_IMAGES)))
                    for slot in range(2, count + 1):
                        values[f"image{slot}"] = reference(f"#{(slot * 719357) % 16777215:06x}")
                elif index == 1:
                    mask = torch.zeros(1, 640, 640)
                    mask[:, 140:470, 80:520] = 1
                    values["mask"] = mask
                elif index == 2:
                    overlay = torch.zeros(1, 640, 640, 4)
                    overlay[:, 160:180, 160:440, 0] = 1
                    overlay[:, 160:180, 160:440, 3] = 1
                    values["markup"] = overlay
                elif index == 3:
                    values.update(background="transparent", prompt="Isolate the teapot on a transparent background with clean edges.")
                elif index == 4:
                    values.update(output_format="jpeg")
                elif index == 5:
                    values.update(output_format="webp")
                if os.environ.get("GPT26_NO_COMPRESSION") == "1":
                    values.pop("output_compression", None)
                if os.environ.get("GPT26_EDIT_FORMAT"):
                    values["output_format"] = os.environ["GPT26_EDIT_FORMAT"]
            if os.environ.get("GPT26_OUTPUT_FORMAT"):
                values["output_format"] = os.environ["GPT26_OUTPUT_FORMAT"]
            if os.environ.get("GPT26_COMPRESSION"):
                values["output_compression"] = int(os.environ["GPT26_COMPRESSION"])
            report({"case": label, "phase": "starting", "requested_size": size})
            started = time.monotonic()
            try:
                original_submit = nodes.submit
                original_poll = nodes.poll
                def submit(*args, **kwargs):
                    report({"case": label, "phase": "submitting", "reference_files": sum(name in ("image", "image[]") for name, _ in args[2])})
                    return original_submit(*args, **kwargs)
                def poll(*args, **kwargs):
                    report({"case": label, "phase": "polling existing task"})
                    return original_poll(*args, **kwargs)
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                     patch.object(nodes, "submit", side_effect=submit), patch.object(nodes, "poll", side_effect=poll):
                    result = nodes.T8ZhenzhenGPTImage26Workshop().generate(api_key=key, **values)
                image, urls, response, mask = result
                assert image.ndim == 4 and image.shape[0] >= 1 and image.shape[-1] == 3
                assert tuple(mask.shape) == tuple(image.shape[:3]) and torch.isfinite(image).all() and torch.isfinite(mask).all()
                record = {"case": label, "status": "PASS", "shape": list(image.shape), "has_url": bool(urls),
                    "mask_range": [round(float(mask.min()), 3), round(float(mask.max()), 3)],
                    "elapsed_seconds": round(time.monotonic() - started, 1)}
                report(record)
            except Exception as error:
                message = str(error).replace(key, "<key>")
                message = re.sub(r"https?://\S+|sk-[A-Za-z0-9]+|task_[A-Za-z0-9_-]+", "<omitted>", message)
                message = re.sub(r"\(request id:[^)]*\)", "<request omitted>", message)
                report({"case": label, "status": "FAIL", "error": message[:700]})
                failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
