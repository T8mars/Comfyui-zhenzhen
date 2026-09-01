from __future__ import annotations

import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW_DIR = ROOT / "workflow"
CONFIG_TYPE = "ZHENZHEN_SEEDANCE2_CONFIG"
NODE_TYPE = "Comfly_wan_3_0_video_lowprice"
PLUGIN_VERSION = "2.0.2"
MAX_IMAGES = 10
MAX_VIDEOS = 5
MAX_AUDIOS = 5
MODELS = (
    "wan-3.0-i2v",
    "wan-3.0-r2v",
    "wan-3.0-global-i2v",
    "wan-3.0-global-r2v",
    "wan-3.0-prime-i2v",
    "wan-3.0-prime-r2v",
    "wan-3.0-global-prime-i2v",
    "wan-3.0-global-prime-r2v",
)
THINKING_MODELS = {"wan-3.0-global-i2v", "wan-3.0-global-r2v"}


def properties(node_type: str, core: bool = False) -> dict:
    return {
        "cnr_id": "comfy-core" if core else "zhenzhen",
        "ver": "0.27.0" if core else PLUGIN_VERSION,
        "Node name for S&R": node_type,
    }


def load_node(
    node_id: int,
    node_type: str,
    title: str,
    link_id: int,
    pos: list[int],
) -> dict:
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
        "size": [280, 250 if node_type == "LoadImage" else 140],
        "flags": {},
        "order": node_id - 1,
        "mode": 0,
        "inputs": [],
        "outputs": outputs,
        "properties": properties(node_type, core=True),
        "widgets_values": widgets,
    }


def settings_node(node_id: int, link_id: int, order: int, pos: list[int]) -> dict:
    return {
        "id": node_id,
        "type": "T8Zhenzhen_API_Settings",
        "title": "Zhenzhen API Settings（国内版）",
        "pos": pos,
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


def media_inputs(links: dict[str, int | None]) -> list[dict]:
    inputs = [
        {
            "name": "api_config",
            "shape": 7,
            "type": CONFIG_TYPE,
            "link": links.get("api_config"),
        }
    ]
    inputs.extend(
        {
            "name": f"image{index}",
            "shape": 7,
            "type": "IMAGE",
            "link": links.get(f"image{index}"),
        }
        for index in range(1, MAX_IMAGES + 1)
    )
    inputs.extend(
        {
            "name": f"video{index}",
            "shape": 7,
            "type": "VIDEO",
            "link": links.get(f"video{index}"),
        }
        for index in range(1, MAX_VIDEOS + 1)
    )
    inputs.extend(
        {
            "name": f"audio{index}",
            "shape": 7,
            "type": "AUDIO",
            "link": links.get(f"audio{index}"),
        }
        for index in range(1, MAX_AUDIOS + 1)
    )
    return inputs


def workflow_for(model: str) -> tuple[str, dict]:
    is_i2v = model.endswith("-i2v")
    is_global = "-global-" in model
    is_prime = "-prime-" in model
    include_video_audio = not is_i2v and not is_prime
    nodes: list[dict] = []
    links: list[list] = []
    input_links: dict[str, int] = {}
    next_node = 1
    next_link = 1

    if is_i2v:
        for slot, title, y in (
            ("image1", "选择首帧图.png", 20),
            ("image2", "选择尾帧图.png", 330),
        ):
            nodes.append(
                load_node(next_node, "LoadImage", title, next_link, [20, y])
            )
            input_links[slot] = next_link
            next_node += 1
            next_link += 1
    else:
        media_loaders = [
            ("image1", "LoadImage", "选择参考图.png", 20),
        ]
        if include_video_audio:
            media_loaders.extend(
                [
                    ("video1", "LoadVideo", "选择参考视频.mp4", 330),
                    ("audio1", "LoadAudio", "选择参考音频.wav", 510),
                ]
            )
        for slot, node_type, title, y in media_loaders:
            nodes.append(
                load_node(next_node, node_type, title, next_link, [20, y])
            )
            input_links[slot] = next_link
            next_node += 1
            next_link += 1

    settings_id = next_node
    config_link = next_link
    input_links["api_config"] = config_link
    nodes.append(
        settings_node(
            settings_id,
            config_link,
            len(nodes),
            [20, 700 if include_video_audio else 650 if is_i2v else 350],
        )
    )
    next_node += 1
    next_link += 1

    model_id = next_node
    video_link = next_link
    mode_label = (
        "首尾帧图生视频"
        if is_i2v
        else "多模态参考生视频" if include_video_audio else "参考图生视频"
    )
    region_label = "海外" if is_global else "国内"
    tier_label = " Prime 高速" if is_prime else ""
    prompt = (
        "从首帧自然过渡到尾帧，保持主体一致，镜头运动平稳连贯"
        if is_i2v
        else (
            "Image 1 中的主体进入 Video 1 的场景，动作节奏跟随 Audio 1，"
            "保持人物特征和镜头连续性"
            if include_video_audio
            else "以 Image 1 为主体，保持人物特征，生成自然连贯的细微动作"
        )
    )
    nodes.append(
        {
            "id": model_id,
            "type": NODE_TYPE,
            "title": f"Wan 3.0 {region_label}{tier_label}{mode_label}",
            "pos": [420, 60],
            "size": [540, 700 if include_video_audio else 540],
            "flags": {},
            "order": len(nodes),
            "mode": 0,
            "inputs": media_inputs(input_links),
            "outputs": [
                {"name": "video", "type": "VIDEO", "links": [video_link]},
                {"name": "video_url", "type": "STRING", "links": None},
                {"name": "task_id", "type": "STRING", "links": None},
                {"name": "response", "type": "STRING", "links": None},
            ],
            "properties": properties(NODE_TYPE),
            "widgets_values": [
                model,
                prompt,
                "2",
                "480P",
                "adaptive",
                True,
                model in THINKING_MODELS,
                "",
                "",
                1 if name == "api_config" else 0,
                False,
            ],
        }
    )

    destination_slots = {
        "api_config": 0,
        **{f"image{index}": index for index in range(1, MAX_IMAGES + 1)},
        **{
            f"video{index}": MAX_IMAGES + index
            for index in range(1, MAX_VIDEOS + 1)
        },
        **{
            f"audio{index}": MAX_IMAGES + MAX_VIDEOS + index
            for index in range(1, MAX_AUDIOS + 1)
        },
    }
    source_by_link = {
        link_id: node["id"]
        for node in nodes
        for output in node.get("outputs", [])
        for link_id in (output.get("links") or [])
        if link_id != video_link
    }
    for name, link_id in input_links.items():
        media_type = (
            CONFIG_TYPE
            if name == "api_config"
            else name.rstrip("1234567890").upper()
        )
        links.append(
            [
                link_id,
                source_by_link[link_id],
                0,
                model_id,
                destination_slots[name],
                media_type,
            ]
        )

    save_id = model_id + 1
    nodes.append(
        {
            "id": save_id,
            "type": "SaveVideo",
            "pos": [1030, 210],
            "size": [320, 200],
            "flags": {},
            "order": len(nodes),
            "mode": 0,
            "inputs": [{"name": "video", "type": "VIDEO", "link": video_link}],
            "outputs": [{"name": "video", "type": "VIDEO", "links": None}],
            "properties": properties("SaveVideo", core=True),
            "widgets_values": [f"video/wan30/{model}", "auto", "auto"],
        }
    )
    links.append([video_link, model_id, 0, save_id, 0, "VIDEO"])

    filename = f"zhenzhen-{model}{mode_label}（贞贞的平价AI小屋）.json"
    workflow = {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"comfyui-zhenzhen/{filename}")),
        "revision": 0,
        "last_node_id": save_id,
        "last_link_id": video_link,
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {"frontendVersion": "1.45.20"},
        "version": 0.4,
    }
    return filename, workflow


def main() -> None:
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        filename, workflow = workflow_for(model)
        (WORKFLOW_DIR / filename).write_text(
            json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(filename)


if __name__ == "__main__":
    main()
