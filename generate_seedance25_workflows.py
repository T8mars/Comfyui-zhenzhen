from __future__ import annotations

import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW_DIR = ROOT / "workflow"
CONFIG_TYPE = "ZHENZHEN_SEEDANCE2_CONFIG"
NODE_TYPE = "Comfly_seedance25_standard_low_price"
PLUGIN_VERSION = "2.0.2"
MAX_IMAGES = 30
MAX_VIDEOS = 10
MAX_AUDIOS = 10
MODELS = (
    "seedance-2.5-standard-t2v",
    "seedance-2.5-standard-i2v",
    "seedance-2.5-standard-multi",
    "seedance-2.5-global-standard-t2v",
    "seedance-2.5-global-standard-i2v",
    "seedance-2.5-global-standard-multi",
)


def properties(node_type: str, core: bool = False) -> dict:
    return {
        "cnr_id": "comfy-core" if core else "zhenzhen",
        "ver": "0.27.0" if core else PLUGIN_VERSION,
        "Node name for S&R": node_type,
    }


def load_node(node_id: int, node_type: str, title: str, link_id: int, pos: list[int]) -> dict:
    output_type = {"LoadImage": "IMAGE", "LoadVideo": "VIDEO", "LoadAudio": "AUDIO"}[node_type]
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
    inputs = [{"name": "api_config", "shape": 7, "type": CONFIG_TYPE, "link": links.get("api_config")}]
    for index in range(1, MAX_IMAGES + 1):
        inputs.append({"name": f"image{index}", "shape": 7, "type": "IMAGE", "link": links.get(f"image{index}")})
    for index in range(1, MAX_VIDEOS + 1):
        inputs.append({"name": f"video{index}", "shape": 7, "type": "VIDEO", "link": links.get(f"video{index}")})
    for index in range(1, MAX_AUDIOS + 1):
        inputs.append({"name": f"audio{index}", "shape": 7, "type": "AUDIO", "link": links.get(f"audio{index}")})
    return inputs


def workflow_for(model: str) -> tuple[str, dict]:
    mode = model.rsplit("-", 1)[-1]
    global_model = "-global-" in model
    nodes: list[dict] = []
    links: list[list] = []
    input_links: dict[str, int | None] = {}
    next_node = 1
    next_link = 1

    if mode == "i2v":
        for slot, title, y in (
            ("image1", "选择首帧图.png", 20),
            ("image2", "选择尾帧图.png", 330),
        ):
            nodes.append(load_node(next_node, "LoadImage", title, next_link, [20, y]))
            input_links[slot] = next_link
            next_node += 1
            next_link += 1
    elif mode == "multi":
        for slot, node_type, title, y in (
            ("image1", "LoadImage", "选择参考图.png", 20),
            ("video1", "LoadVideo", "选择参考视频.mp4", 330),
            ("audio1", "LoadAudio", "选择参考音频.wav", 510),
        ):
            nodes.append(load_node(next_node, node_type, title, next_link, [20, y]))
            input_links[slot] = next_link
            next_node += 1
            next_link += 1

    settings_id = next_node
    config_link = next_link
    input_links["api_config"] = config_link
    nodes.append(settings_node(settings_id, config_link, len(nodes), [20, 700 if mode == "multi" else 650]))
    next_node += 1
    next_link += 1

    model_id = next_node
    video_link = next_link
    mode_label = {"t2v": "文生视频", "i2v": "首尾帧图生视频", "multi": "多模态参考生视频"}[mode]
    region_label = "海外" if global_model else "国内"
    prompt = {
        "t2v": "一架白色纸飞机穿过清晨的玻璃温室，镜头平稳跟随，电影感自然光",
        "i2v": "从首帧自然过渡到尾帧，保持主体一致，镜头运动平稳连贯",
        "multi": "让 @Image 1 中的主体进入 @Video 1 的场景，动作节奏跟随 @Audio 1，保持主体特征和画面连续性",
    }[mode]
    nodes.append({
        "id": model_id,
        "type": NODE_TYPE,
        "title": f"Seedance 2.5 Standard {region_label}{mode_label}",
        "pos": [420, 60],
        "size": [540, 700 if mode == "multi" else 520],
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
            "4",
            "480p",
            "adaptive" if mode == "i2v" else "16:9",
            True,
            False,
            -1,
            False,
        ],
    })

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
        links.append([
            link_id,
            source_by_link[link_id],
            1 if name == "api_config" else 0,
            model_id,
            destination_slots[name],
            CONFIG_TYPE if name == "api_config" else name.rstrip("123456789").upper(),
        ])

    save_id = model_id + 1
    nodes.append({
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
        "widgets_values": [f"video/seedance25/{model}", "auto", "auto"],
    })
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
