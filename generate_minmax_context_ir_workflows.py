from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
WORKFLOW_DIR = ROOT / "workflow"
CONFIG_TYPE = "ZHENZHEN_SEEDANCE2_CONFIG"
NODE_TYPE = "Comfly_minmax_h3_context_ir_lowprice"
PLUGIN_VERSION = "2.0.2"

MODELS = {
    "minmax-h3-context-ir-text": (
        "文本提示词增强",
        "清晨花园里，一位穿浅色风衣的女性沿石径缓慢前行，镜头平稳跟随，柔和电影光线",
        "16:9",
    ),
    "minmax-h3-context-ir-image": (
        "图像提示词增强",
        "保持主体外观与场景构图，增加自然动作和连贯的电影镜头运动",
        "16:9",
    ),
    "minmax-h3-context-ir-multimodal": (
        "多模态提示词增强",
        "结合图片主体、视频镜头运动和音频节奏，生成连贯且可执行的视频提示词",
        "adaptive",
    ),
}


def properties(node_type: str, core: bool = False) -> dict[str, str]:
    return {
        "cnr_id": "comfy-core" if core else "zhenzhen",
        "ver": "0.27.0" if core else PLUGIN_VERSION,
        "Node name for S&R": node_type,
    }


def settings_node(node_id: int, link_id: int, order: int) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "T8Zhenzhen_API_Settings",
        "title": "Zhenzhen API Settings（国内版）",
        "pos": [20, 690],
        "size": [340, 174],
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": [],
        "outputs": [
            {"name": "apikey", "type": "STRING", "links": None},
            {"name": "api_config", "type": CONFIG_TYPE, "links": [link_id]},
        ],
        "properties": properties("T8Zhenzhen_API_Settings"),
        "widgets_values": ["seedance_low_price", "", "", False],
    }


def load_node(
    node_id: int,
    node_type: str,
    title: str,
    link_id: int,
    order: int,
    pos: list[int],
) -> dict[str, Any]:
    output_type = {
        "LoadImage": "IMAGE",
        "LoadVideo": "VIDEO",
        "LoadAudio": "AUDIO",
    }[node_type]
    widgets = {
        "LoadImage": [title, "image"],
        "LoadVideo": [title],
        "LoadAudio": [title, None, ""],
    }[node_type]
    outputs = [{"name": output_type, "type": output_type, "links": [link_id]}]
    if node_type == "LoadImage":
        outputs.append({"name": "MASK", "type": "MASK", "links": None})
    return {
        "id": node_id,
        "type": node_type,
        "title": title,
        "pos": pos,
        "size": [280, 250 if node_type == "LoadImage" else 150],
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": [],
        "outputs": outputs,
        "properties": properties(node_type, core=True),
        "widgets_values": widgets,
    }


def context_inputs(links: dict[str, int]) -> list[dict[str, Any]]:
    inputs = []
    for family, count, media_type in (
        ("image", 9, "IMAGE"),
        ("video", 3, "VIDEO"),
        ("audio", 3, "AUDIO"),
    ):
        for index in range(1, count + 1):
            name = f"{family}{index}"
            inputs.append(
                {
                    "name": name,
                    "shape": 7,
                    "type": media_type,
                    "link": links.get(name),
                }
            )
    inputs.append(
        {
            "name": "api_config",
            "shape": 7,
            "type": CONFIG_TYPE,
            "link": links["api_config"],
        }
    )
    return inputs


def preview_node(node_id: int, link_id: int, order: int) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "PreviewAny",
        "title": "增强后的提示词",
        "pos": [1010, 150],
        "size": [340, 220],
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": [{"name": "source", "type": "*", "link": link_id}],
        "outputs": [{"name": "STRING", "type": "STRING", "links": None}],
        "properties": properties("PreviewAny", core=True),
        "widgets_values": [],
    }


def workflow(model: str) -> tuple[str, dict[str, Any]]:
    label, prompt, ratio = MODELS[model]
    filename = f"zhenzhen-{model}{label}（贞贞的平价AI小屋）.json"
    is_image = model.endswith("-image")
    is_multimodal = model.endswith("-multimodal")
    nodes: list[dict[str, Any]] = []
    links: list[list[Any]] = []
    incoming: dict[str, int] = {}
    next_node = 1
    next_link = 1

    if is_image or is_multimodal:
        nodes.append(
            load_node(
                next_node,
                "LoadImage",
                "选择首帧图.png" if is_image else "选择参考图.png",
                next_link,
                len(nodes),
                [20, 30],
            )
        )
        incoming["image1"] = next_link
        next_node += 1
        next_link += 1
    if is_multimodal:
        nodes.append(
            load_node(
                next_node,
                "LoadVideo",
                "选择参考视频.mp4",
                next_link,
                len(nodes),
                [20, 320],
            )
        )
        incoming["video1"] = next_link
        next_node += 1
        next_link += 1
        nodes.append(
            load_node(
                next_node,
                "LoadAudio",
                "选择参考音频.wav",
                next_link,
                len(nodes),
                [20, 500],
            )
        )
        incoming["audio1"] = next_link
        next_node += 1
        next_link += 1

    settings_id = next_node
    config_link = next_link
    nodes.append(settings_node(settings_id, config_link, len(nodes)))
    incoming["api_config"] = config_link
    next_node += 1
    next_link += 1

    context_id = next_node
    result_link = next_link
    nodes.append(
        {
            "id": context_id,
            "type": NODE_TYPE,
            "title": f"MiniMax H3 Context IR {label}",
            "pos": [420, 60],
            "size": [520, 650 if is_multimodal else 470],
            "flags": {},
            "order": len(nodes),
            "mode": 0,
            "inputs": context_inputs(incoming),
            "outputs": [
                {"name": "result_text", "type": "STRING", "links": [result_link]},
                {"name": "task_id", "type": "STRING", "links": None},
                {"name": "response", "type": "STRING", "links": None},
            ],
            "properties": properties(NODE_TYPE),
            "widgets_values": [model, prompt, "4", ratio, False, 0],
        }
    )
    next_node += 1
    next_link += 1
    nodes.append(preview_node(next_node, result_link, len(nodes)))

    source_nodes = {node["type"]: node["id"] for node in nodes}
    if "image1" in incoming:
        links.append([incoming["image1"], source_nodes["LoadImage"], 0, context_id, 0, "IMAGE"])
    if "video1" in incoming:
        links.append([incoming["video1"], source_nodes["LoadVideo"], 0, context_id, 9, "VIDEO"])
    if "audio1" in incoming:
        links.append([incoming["audio1"], source_nodes["LoadAudio"], 0, context_id, 12, "AUDIO"])
    links.append([config_link, settings_id, 1, context_id, 15, CONFIG_TYPE])
    links.append([result_link, context_id, 0, next_node, 0, "STRING"])

    document = {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"comfyui-zhenzhen/{filename}")),
        "revision": 0,
        "last_node_id": next_node,
        "last_link_id": result_link,
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {"frontendVersion": "1.45.20"},
        "version": 0.4,
    }
    return filename, document


def main() -> None:
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        filename, document = workflow(model)
        (WORKFLOW_DIR / filename).write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"Generated {len(MODELS)} MiniMax H3 Context IR workflows")


if __name__ == "__main__":
    main()
