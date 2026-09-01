"""Opt-in real API validation for the Aug-22 domestic low-price nodes."""

from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path

import cv2
import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
COMFY_ROOT = PLUGIN_ROOT.parents[1]
sys.path.insert(0, str(COMFY_ROOT))

PACKAGE_NAME = "zhenzhen_aug22_live_package"
package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(PLUGIN_ROOT)]
sys.modules[PACKAGE_NAME] = package

advanced = importlib.import_module(f"{PACKAGE_NAME}.aug22_low_price_nodes")
latest = importlib.import_module(f"{PACKAGE_NAME}.latest_image_audio_low_price_nodes")
legacy = importlib.import_module(f"{PACKAGE_NAME}.seedance_low_price_nodes")


def require_live_config() -> dict:
    if os.environ.get("RUN_LIVE_AUG22", "") != "1":
        raise SystemExit("Set RUN_LIVE_AUG22=1 to run paid API validation.")
    api_key = os.environ.get("SEEDANCE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("SEEDANCE_API_KEY is required.")
    return {"base_url": "https://api.seedance.nz", "api_key": api_key}


def synthetic_image(color: tuple[float, float, float]) -> torch.Tensor:
    image = torch.ones((1, 512, 512, 3), dtype=torch.float32)
    image[..., 0] *= color[0]
    image[..., 1] *= color[1]
    image[..., 2] *= color[2]
    image[:, 128:384, 128:384, :] = torch.tensor([0.95, 0.95, 0.95])
    return image


def first_frame(path: Path) -> torch.Tensor:
    capture = cv2.VideoCapture(str(path))
    ok, frame = capture.read()
    capture.release()
    if not ok or frame is None:
        raise RuntimeError("Could not decode the reference video first frame")
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return torch.from_numpy(rgb.copy()).float().div(255.0).unsqueeze(0)


def validate_video(value) -> None:
    data = legacy.video_to_mp4_bytes(value)
    if len(data) < 1024:
        raise AssertionError("Generated video is unexpectedly small")


def validate_image(value) -> None:
    if not torch.is_tensor(value) or value.ndim != 4 or value.shape[-1] != 3:
        raise AssertionError("Generated image is not a ComfyUI IMAGE tensor")


def validate_native_3d(file_3d, local_path: str, label: str) -> None:
    if file_3d.get_bytes()[:4] != b"glTF":
        raise AssertionError("Native File3D output does not contain GLB data")
    advanced._validate_glb(local_path)

    from comfy_extras.nodes_load_3d import Preview3D
    from comfy_extras.nodes_save_3d import SaveGLB

    preview = Preview3D.execute(file_3d)
    preview_path = COMFY_ROOT / "output" / preview.ui.model_file
    if not preview_path.is_file():
        raise AssertionError("Preview3D did not materialize the GLB file")

    SaveGLB.hidden = types.SimpleNamespace(prompt=None, extra_pnginfo=None)
    saved = SaveGLB.execute(file_3d, f"zhenzhen_live/{label}")
    saved_item = saved.ui["3d"][0]
    saved_path = (
        COMFY_ROOT
        / "output"
        / saved_item.get("subfolder", "")
        / saved_item["filename"]
    )
    if not saved_path.is_file():
        raise AssertionError("SaveGLB did not save the native File3D output")
    advanced._validate_glb(str(saved_path))

    preview_path.unlink(missing_ok=True)
    saved_path.unlink(missing_ok=True)
    try:
        saved_path.parent.rmdir()
    except OSError:
        pass


def run_remaining(config: dict, reference_path: Path) -> None:
    if not reference_path.is_file():
        raise RuntimeError("LIVE_AUG22_REMAINING_VIDEO does not exist")
    source_image = first_frame(reference_path)
    video_reference = None
    if os.environ.get("LIVE_AUG22_SKIP_REFERENCE_VIDEO", "") != "1":
        omni = advanced.Comfly_zhenzhen_video_g_omni_flash_lowprice_v2()
        video_reference = omni.generate(
            mode="reference_video",
            prompt="continue the camera movement around the ceramic object",
            seconds="4",
            resolution="720p",
            aspect_ratio="16:9",
            nsfw_check=False,
            input_video=str(reference_path),
            api_config=config,
        )
        validate_video(video_reference[0])
        print("live_aug22: Omni reference-video mode completed")

    hunyuan = advanced.Comfly_hunyuan3d_v3_1_lowprice()
    text_3d = hunyuan.generate(
        model=advanced.HUNYUAN3D_TEXT_MODEL,
        prompt="a compact blue and white ceramic teapot",
        face_count=10000,
        enable_pbr=False,
        generate_type="Normal",
        api_config=config,
    )
    text_result = text_3d["result"]
    validate_native_3d(text_result[0], text_result[2], "hunyuan_text")
    print("live_aug22: Hunyuan text-to-3D and native Preview3D/SaveGLB completed")

    image_3d = hunyuan.generate(
        model=advanced.HUNYUAN3D_IMAGE_MODEL,
        prompt="a clean ceramic object model matching the reference image",
        face_count=10000,
        enable_pbr=False,
        generate_type="Normal",
        image1=source_image,
        api_config=config,
    )
    image_result = image_3d["result"]
    validate_native_3d(image_result[0], image_result[2], "hunyuan_image")
    print("live_aug22: Hunyuan image-to-3D and native Preview3D/SaveGLB completed")

    if video_reference is not None:
        generated_path = video_reference[0].get_stream_source()
        if isinstance(generated_path, str):
            Path(generated_path).unlink(missing_ok=True)
    Path(text_result[2]).unlink(missing_ok=True)
    Path(image_result[2]).unlink(missing_ok=True)
    print("live_aug22: all remaining real API checks passed")


def run() -> None:
    config = require_live_config()
    print("live_aug22: domestic config accepted")
    remaining_video = os.environ.get("LIVE_AUG22_REMAINING_VIDEO", "").strip()
    if remaining_video:
        run_remaining(config, Path(remaining_video))
        return

    source = latest.Comfly_zhenzhen_image_gk_v2_lowprice().generate(
        prompt="a single red ceramic teapot on a clean white studio background",
        size="1:1",
        n=1,
        api_config=config,
    )
    source_image, source_task_id = source[0], source[2]
    validate_image(source_image)
    print("live_aug22: GK v2 source image completed")

    segment = advanced.Comfly_zhenzhen_image_gk_v2_segment_lowprice().segment(
        source_task_id=source_task_id,
        include_mask_rle=False,
        api_config=config,
    )
    image_id = segment["result"][0]
    objects = segment["result"][1]
    if not image_id or not objects:
        raise AssertionError("Segment did not return image_id and objects JSON")
    print("live_aug22: GK v2 segment completed")

    region = advanced.Comfly_zhenzhen_image_gk_v2_region_edit_lowprice().edit(
        image_id=image_id,
        prompt="replace the selected object with a blue ceramic vase",
        selection_mode="object_indices",
        selection_json="[0]",
        api_config=config,
    )
    validate_image(region[0])
    edited_image = region[0]
    print("live_aug22: GK v2 region edit completed")

    omni = advanced.Comfly_zhenzhen_video_g_omni_flash_lowprice_v2()
    common = {
        "prompt": "the studio camera moves slowly around the ceramic object",
        "seconds": "4",
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "nsfw_check": False,
        "api_config": config,
    }
    text_video = omni.generate(mode="text", **common)
    validate_video(text_video[0])
    print("live_aug22: Omni text mode completed")

    frame_video = omni.generate(mode="frame", image1=source_image, **common)
    validate_video(frame_video[0])
    print("live_aug22: Omni frame mode completed")

    reference_video = omni.generate(
        mode="reference_images",
        image1=source_image,
        image2=edited_image,
        image3=synthetic_image((0.15, 0.45, 0.75)),
        **common,
    )
    validate_video(reference_video[0])
    print("live_aug22: Omni reference-images mode completed")

    video_reference = omni.generate(
        mode="reference_video",
        input_video=text_video[0],
        **common,
    )
    validate_video(video_reference[0])
    print("live_aug22: Omni reference-video mode completed")

    hunyuan = advanced.Comfly_hunyuan3d_v3_1_lowprice()
    text_3d = hunyuan.generate(
        model=advanced.HUNYUAN3D_TEXT_MODEL,
        prompt="a compact blue and white ceramic teapot",
        face_count=10000,
        enable_pbr=False,
        generate_type="Normal",
        api_config=config,
    )
    text_result = text_3d["result"]
    validate_native_3d(text_result[0], text_result[2], "hunyuan_text")
    print("live_aug22: Hunyuan text-to-3D and native Preview3D/SaveGLB completed")

    image_3d = hunyuan.generate(
        model=advanced.HUNYUAN3D_IMAGE_MODEL,
        prompt="a clean ceramic teapot model matching the reference image",
        face_count=10000,
        enable_pbr=False,
        generate_type="Normal",
        image1=source_image,
        api_config=config,
    )
    image_result = image_3d["result"]
    validate_native_3d(image_result[0], image_result[2], "hunyuan_image")
    print("live_aug22: Hunyuan image-to-3D and native Preview3D/SaveGLB completed")

    for video_result in (text_video, frame_video, reference_video, video_reference):
        source_path = video_result[0].get_stream_source()
        if isinstance(source_path, str):
            Path(source_path).unlink(missing_ok=True)
    Path(text_result[2]).unlink(missing_ok=True)
    Path(image_result[2]).unlink(missing_ok=True)
    print("live_aug22: all real API checks passed")


if __name__ == "__main__":
    run()
