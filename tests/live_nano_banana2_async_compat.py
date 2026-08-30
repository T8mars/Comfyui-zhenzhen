"""Paid Nano Banana 2 Edit async compatibility check.

Set ZHENZHEN_API_KEY before running. The script does not print or persist the
key, task identifier, result URL, or generated image.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
COMFY_ROOT = PLUGIN_ROOT.parents[1]
sys.path.insert(0, str(COMFY_ROOT))

import comfy_api.latest  # noqa: E402,F401


def load_comfly():
    package_name = "zhenzhen_nano_banana2_live_package"
    package = types.ModuleType(package_name)
    package.__path__ = [str(PLUGIN_ROOT)]
    sys.modules[package_name] = package
    module_name = f"{package_name}.Comfly"
    spec = importlib.util.spec_from_file_location(module_name, PLUGIN_ROOT / "Comfly.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def make_reference_image(size=512):
    image = torch.zeros((1, size, size, 3), dtype=torch.float32)
    image[:, :, :, 0] = torch.linspace(0.15, 0.85, size).view(1, 1, size)
    image[:, :, :, 1] = torch.linspace(0.8, 0.2, size).view(1, size, 1)
    image[:, size // 4 : size // 2, size // 4 : 3 * size // 4, 2] = 0.9
    return image


def main():
    api_key = os.environ.get("ZHENZHEN_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set ZHENZHEN_API_KEY to run paid live verification")

    comfly = load_comfly()
    node_class = comfly.NODE_CLASS_MAPPINGS["Comfly_nano_banana2_edit"]
    if node_class is not comfly.Comfly_nano_banana2_edit_async_compatible:
        raise RuntimeError("Nano Banana 2 Edit is not mapped to the async-compatible class")

    image, response, image_url = node_class().generate_image(
        prompt="Keep the composition and turn it into a clean watercolor illustration.",
        mode="img2img",
        model="nano-banana-pro",
        aspect_ratio="1:1",
        image_size="1K",
        image1=make_reference_image(),
        apikey=api_key,
        response_format="url",
        seed=0,
        skip_error=False,
    )
    if not torch.is_tensor(image) or image.ndim != 4 or image.shape[-1] != 3:
        raise RuntimeError("Nano Banana 2 Edit did not return a ComfyUI IMAGE tensor")
    if image.shape[1] < 256 or image.shape[2] < 256:
        raise RuntimeError("Nano Banana 2 Edit returned an unexpectedly small image")
    if not str(image_url).startswith(("http://", "https://")):
        raise RuntimeError("Nano Banana 2 Edit did not expose the completed image URL")
    if "Generated " not in str(response):
        raise RuntimeError("Nano Banana 2 Edit returned incomplete response metadata")

    print(
        f"nano_banana2_edit_live=ok shape={tuple(image.shape)} async_mapping=ok",
        flush=True,
    )


if __name__ == "__main__":
    main()
