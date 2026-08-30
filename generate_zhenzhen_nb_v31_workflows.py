"""Generate safe example workflows for Zhenzhen Image NB and Video V3.1 Lite."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parent
WORKFLOW_DIR = ROOT / "workflow"
DOMESTIC_SUFFIX = "（贞贞的平价AI小屋）"
IMAGE_NODE = "Comfly_zhenzhen_image_nb_lowprice"

IMAGE_MODELS = (
    "zhenzhen-image-nb-flash",
    "zhenzhen-image-nb-2",
    "zhenzhen-image-nb-2-lite",
    "zhenzhen-image-nb-pro",
)


def load_template(name: str) -> Dict[str, Any]:
    return json.loads((WORKFLOW_DIR / name).read_text(encoding="utf-8"))


def deterministic_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"comfyui-zhenzhen/{name}"))


def find_node(workflow: Dict[str, Any], node_type: str) -> Dict[str, Any]:
    return next(node for node in workflow["nodes"] if node["type"] == node_type)


def save_workflow(filename: str, workflow: Dict[str, Any]) -> None:
    workflow["id"] = deterministic_id(filename)
    raw = json.dumps(workflow, ensure_ascii=False, indent=2) + "\n"
    (WORKFLOW_DIR / filename).write_text(raw, encoding="utf-8")


def generate_image_workflow(model: str, editing: bool) -> None:
    template_name = (
        f"zhenzhen-image-g-v2-lowprice图生图{DOMESTIC_SUFFIX}.json"
        if editing
        else f"zhenzhen-image-g-v2-lowprice文生图{DOMESTIC_SUFFIX}.json"
    )
    workflow = load_template(template_name)
    source_type = "Comfly_zhenzhen_image_g_v2_lowprice"
    node = find_node(workflow, source_type)
    node["type"] = IMAGE_NODE
    node["title"] = f"{model} {'图像编辑' if editing else '文生图'}"
    node["inputs"] = [
        value
        for value in node["inputs"]
        if not value["name"].startswith("image")
        or int(value["name"].removeprefix("image")) <= 14
    ]
    node["properties"]["Node name for S&R"] = IMAGE_NODE
    node["widgets_values"] = [
        model,
        (
            "保持主体身份与构图，将背景替换为干净的电影感摄影棚"
            if editing
            else "精致的产品摄影，干净摄影棚，自然光，细节清晰"
        ),
        "1k",
        "1:1",
        1,
        False,
    ]

    save_image = find_node(workflow, "SaveImage")
    save_image["widgets_values"] = [
        f"zhenzhen_image_nb_{model.removeprefix('zhenzhen-image-nb-').replace('-', '_')}"
        f"_{'edit' if editing else 't2i'}"
    ]
    mode_name = "图像编辑" if editing else "文生图"
    save_workflow(f"{model}{mode_name}{DOMESTIC_SUFFIX}.json", workflow)


def generate_v31_lite_workflow() -> None:
    workflow = load_template(
        f"zhenzhen-video-v31-fast文生视频{DOMESTIC_SUFFIX}.json"
    )
    node = find_node(workflow, "Comfly_zhenzhen_video_v31_lowprice")
    node["title"] = "Video V3.1 Lite 文生视频"
    node["widgets_values"][0] = "zhenzhen-video-v31-lite"
    node["widgets_values"][1] = (
        "一架纸飞机穿过日出时分的暖色云层，流畅的电影感镜头运动"
    )
    save_video = find_node(workflow, "SaveVideo")
    save_video["widgets_values"][0] = "zhenzhen_video_v31_lite_t2v"
    save_workflow(
        f"zhenzhen-video-v31-lite文生视频{DOMESTIC_SUFFIX}.json",
        workflow,
    )


def main() -> None:
    for model in IMAGE_MODELS:
        generate_image_workflow(model, editing=False)
        generate_image_workflow(model, editing=True)
    generate_v31_lite_workflow()
    print("Generated 9 Zhenzhen Image NB / Video V3.1 Lite workflows.")


if __name__ == "__main__":
    main()
