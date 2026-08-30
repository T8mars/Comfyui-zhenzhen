from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
WORKFLOW_DIR = ROOT / "workflow"
CONFIG_TYPE = "ZHENZHEN_SEEDANCE2_CONFIG"
PLUGIN_VERSION = "2.0.2"
HAILUO_NODE = "Comfly_hailuo_h3_video_lowprice"
FLUX3_NODE = "Comfly_flux3_video_lowprice"
HAILUO_MODELS = (
    "hailuo-h3-t2v",
    "hailuo-h3-i2v",
    "hailuo-h3-multi",
    "hailuo-h3-global-t2v",
    "hailuo-h3-global-i2v",
    "hailuo-h3-global-multi",
)
FLUX3_MODELS = (
    "flux-3-video-t2v",
    "flux-3-video-i2v",
    "flux-3-video-v2v",
    "flux-3-video-draft-enhance",
    "flux-3-video-global-t2v",
    "flux-3-video-global-i2v",
    "flux-3-video-global-v2v",
    "flux-3-video-global-draft-enhance",
)


def properties(node_type: str, core: bool = False) -> dict[str, str]:
    return {
        "cnr_id": "comfy-core" if core else "zhenzhen",
        "ver": "0.27.0" if core else PLUGIN_VERSION,
        "Node name for S&R": node_type,
    }


def settings_node(
    node_id: int,
    link_ids: list[int],
    order: int,
    pos: list[int],
) -> dict[str, Any]:
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
            {"name": "api_config", "type": CONFIG_TYPE, "links": link_ids},
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


def save_node(
    node_id: int,
    link_id: int,
    order: int,
    prefix: str,
    pos: list[int],
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "SaveVideo",
        "pos": pos,
        "size": [320, 200],
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": [{"name": "video", "type": "VIDEO", "link": link_id}],
        "outputs": [{"name": "video", "type": "VIDEO", "links": None}],
        "properties": properties("SaveVideo", core=True),
        "widgets_values": [prefix, "auto", "auto"],
    }


def workflow_document(filename: str, nodes: list[dict], links: list[list]) -> dict:
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"comfyui-zhenzhen/{filename}")),
        "revision": 0,
        "last_node_id": max(node["id"] for node in nodes),
        "last_link_id": max(link[0] for link in links),
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {"frontendVersion": "1.45.20"},
        "version": 0.4,
    }


def hailuo_inputs(link_by_name: dict[str, int]) -> list[dict[str, Any]]:
    inputs = [
        {
            "name": "api_config",
            "shape": 7,
            "type": CONFIG_TYPE,
            "link": link_by_name.get("api_config"),
        }
    ]
    for index in range(1, 10):
        inputs.append(
            {
                "name": f"image{index}",
                "shape": 7,
                "type": "IMAGE",
                "link": link_by_name.get(f"image{index}"),
            }
        )
    for index in range(1, 4):
        inputs.append(
            {
                "name": f"video{index}",
                "shape": 7,
                "type": "VIDEO",
                "link": link_by_name.get(f"video{index}"),
            }
        )
    for index in range(1, 4):
        inputs.append(
            {
                "name": f"audio{index}",
                "shape": 7,
                "type": "AUDIO",
                "link": link_by_name.get(f"audio{index}"),
            }
        )
    return inputs


def hailuo_filename(model: str) -> str:
    mode = model.rsplit("-", 1)[-1]
    label = {
        "t2v": "文生视频",
        "i2v": "图生视频首尾帧",
        "multi": "多模态参考生视频",
    }[mode]
    global_label = "-global" if "-global-" in model else ""
    return f"zhenzhen-hailuo-h3{global_label}{label}（贞贞的平价AI小屋）.json"


def hailuo_workflow(model: str) -> tuple[str, dict]:
    mode = model.rsplit("-", 1)[-1]
    global_model = "-global-" in model
    filename = hailuo_filename(model)
    nodes: list[dict[str, Any]] = []
    links: list[list[Any]] = []
    input_links: dict[str, int] = {}
    next_node = 1
    next_link = 1

    media = []
    if mode == "i2v":
        media = [
            ("image1", "LoadImage", "选择首帧图.png", [20, 20]),
            ("image2", "LoadImage", "选择尾帧图.png", [20, 330]),
        ]
    elif mode == "multi":
        media = [
            ("image1", "LoadImage", "选择参考图.png", [20, 20]),
            ("video1", "LoadVideo", "选择参考视频.mp4", [20, 330]),
            ("audio1", "LoadAudio", "选择参考音频.wav", [20, 510]),
        ]
    for name, node_type, title, pos in media:
        nodes.append(
            load_node(next_node, node_type, title, next_link, len(nodes), pos)
        )
        input_links[name] = next_link
        next_node += 1
        next_link += 1

    config_link = next_link
    settings_id = next_node
    input_links["api_config"] = config_link
    nodes.append(
        settings_node(
            settings_id,
            [config_link],
            len(nodes),
            [20, 700 if mode == "multi" else 650],
        )
    )
    next_node += 1
    next_link += 1

    model_id = next_node
    video_link = next_link
    prompt = {
        "t2v": "清晨薄雾中的玻璃温室，一只白色纸飞机缓慢穿过花丛，镜头平稳跟随，柔和电影光线",
        "i2v": "从首帧自然过渡到尾帧，保持主体一致，镜头运动平稳连贯",
        "multi": "让 @Image 1 中的主体进入 @Video 1 的场景，动作节奏跟随 @Audio 1，保持画面连续性",
    }[mode]
    region = "海外" if global_model else "国内"
    nodes.append(
        {
            "id": model_id,
            "type": HAILUO_NODE,
            "title": f"Hailuo H3 {region}{mode.upper()}",
            "pos": [420, 60],
            "size": [520, 650 if mode == "multi" else 500],
            "flags": {},
            "order": len(nodes),
            "mode": 0,
            "inputs": hailuo_inputs(input_links),
            "outputs": [
                {"name": "video", "type": "VIDEO", "links": [video_link]},
                {"name": "video_url", "type": "STRING", "links": None},
                {"name": "task_id", "type": "STRING", "links": None},
                {"name": "response", "type": "STRING", "links": None},
            ],
            "properties": properties(HAILUO_NODE),
            "widgets_values": [
                model,
                prompt,
                "5",
                "768P" if global_model else "2K",
                "adaptive" if mode == "i2v" else "16:9",
                False,
            ],
        }
    )

    destination = {
        "api_config": 0,
        **{f"image{index}": index for index in range(1, 10)},
        **{f"video{index}": 9 + index for index in range(1, 4)},
        **{f"audio{index}": 12 + index for index in range(1, 4)},
    }
    source_by_link = {
        link: node["id"]
        for node in nodes
        for output in node.get("outputs", [])
        for link in (output.get("links") or [])
        if link != video_link
    }
    for name, link_id in input_links.items():
        media_type = (
            CONFIG_TYPE
            if name == "api_config"
            else "IMAGE"
            if name.startswith("image")
            else "VIDEO"
            if name.startswith("video")
            else "AUDIO"
        )
        links.append(
            [
                link_id,
                source_by_link[link_id],
                1 if name == "api_config" else 0,
                model_id,
                destination[name],
                media_type,
            ]
        )

    save_id = model_id + 1
    nodes.append(
        save_node(
            save_id,
            video_link,
            len(nodes),
            f"video/hailuo_h3/{model}",
            [1020, 200],
        )
    )
    links.append([video_link, model_id, 0, save_id, 0, "VIDEO"])
    return filename, workflow_document(filename, nodes, links)


def flux_inputs(
    link_by_name: dict[str, int],
    include_draft_cache: bool = False,
) -> list[dict[str, Any]]:
    inputs = [
        {
            "name": "api_config",
            "shape": 7,
            "type": CONFIG_TYPE,
            "link": link_by_name.get("api_config"),
        }
    ]
    for index in range(1, 11):
        inputs.append(
            {
                "name": f"image{index}",
                "shape": 7,
                "type": "IMAGE",
                "link": link_by_name.get(f"image{index}"),
            }
        )
    inputs.append(
        {
            "name": "input_video",
            "shape": 7,
            "type": "VIDEO",
            "link": link_by_name.get("input_video"),
        }
    )
    if include_draft_cache:
        inputs.append(
            {
                "name": "draft_cache",
                "shape": 7,
                "type": "STRING",
                "link": link_by_name.get("draft_cache"),
                "widget": {"name": "draft_cache"},
            }
        )
    return inputs


def flux_outputs(video_link: int | None, draft_link: int | None = None) -> list[dict]:
    return [
        {"name": "video", "type": "VIDEO", "links": [video_link] if video_link else None},
        {"name": "video_url", "type": "STRING", "links": None},
        {"name": "draft_cache", "type": "STRING", "links": [draft_link] if draft_link else None},
        {"name": "task_id", "type": "STRING", "links": None},
        {"name": "response", "type": "STRING", "links": None},
    ]


def flux_widgets(model: str, prompt: str, draft: bool = False) -> list[Any]:
    return [
        model,
        prompt,
        "5",
        "hd",
        "16:9",
        draft,
        "api_default",
        "api_default",
        "",
        "",
        False,
    ]


def flux_node(
    node_id: int,
    model: str,
    title: str,
    prompt: str,
    input_links: dict[str, int],
    video_link: int | None,
    order: int,
    pos: list[int],
    draft: bool = False,
    draft_link: int | None = None,
    include_draft_cache: bool = False,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": FLUX3_NODE,
        "title": title,
        "pos": pos,
        "size": [540, 560],
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": flux_inputs(input_links, include_draft_cache),
        "outputs": flux_outputs(video_link, draft_link),
        "properties": properties(FLUX3_NODE),
        "widgets_values": flux_widgets(model, prompt, draft=draft),
    }


def flux_workflow(model: str) -> tuple[str, dict]:
    mode = "draft-enhance" if model.endswith("-draft-enhance") else model.rsplit("-", 1)[-1]
    label = {
        "t2v": "文生视频",
        "i2v": "多关键帧图生视频",
        "v2v": "视频编辑",
        "draft-enhance": "草稿增强",
    }[mode]
    filename = f"zhenzhen-{model}{label}（贞贞的平价AI小屋）.json"
    global_model = "-global-" in model
    region = "海外" if global_model else "国内"

    if mode == "draft-enhance":
        source_model = (
            "flux-3-video-global-t2v" if global_model else "flux-3-video-t2v"
        )
        config_source_link, config_enhance_link = 1, 2
        cache_link, video_link = 3, 4
        nodes = [
            settings_node(1, [config_source_link, config_enhance_link], 0, [20, 650]),
            flux_node(
                2,
                source_model,
                f"FLUX 3 {region}草稿生成",
                "一架银色纸飞机穿过清晨薄雾，稳定镜头，柔和电影光线",
                {"api_config": config_source_link},
                None,
                1,
                [420, 20],
                draft=True,
                draft_link=cache_link,
            ),
            flux_node(
                3,
                model,
                f"FLUX 3 {region}草稿增强",
                "",
                {
                    "api_config": config_enhance_link,
                    "draft_cache": cache_link,
                },
                video_link,
                2,
                [1020, 20],
                include_draft_cache=True,
            ),
            save_node(4, video_link, 3, f"video/flux3/{model}", [1640, 180]),
        ]
        links = [
            [config_source_link, 1, 1, 2, 0, CONFIG_TYPE],
            [config_enhance_link, 1, 1, 3, 0, CONFIG_TYPE],
            [cache_link, 2, 2, 3, 12, "STRING"],
            [video_link, 3, 0, 4, 0, "VIDEO"],
        ]
        return filename, workflow_document(filename, nodes, links)

    nodes: list[dict[str, Any]] = []
    links: list[list[Any]] = []
    input_links: dict[str, int] = {}
    next_node = 1
    next_link = 1
    media = []
    if mode == "i2v":
        media = [
            ("image1", "LoadImage", "选择关键帧1.png", [20, 20]),
            ("image2", "LoadImage", "选择关键帧2.png", [20, 330]),
        ]
    elif mode == "v2v":
        media = [
            ("input_video", "LoadVideo", "选择待编辑视频.mp4", [20, 120]),
        ]
    for name, node_type, title, pos in media:
        nodes.append(
            load_node(next_node, node_type, title, next_link, len(nodes), pos)
        )
        input_links[name] = next_link
        next_node += 1
        next_link += 1

    config_link = next_link
    settings_id = next_node
    input_links["api_config"] = config_link
    nodes.append(settings_node(settings_id, [config_link], len(nodes), [20, 650]))
    next_node += 1
    next_link += 1

    model_id = next_node
    video_link = next_link
    prompt = {
        "t2v": "一架银色纸飞机穿过清晨薄雾，稳定镜头，柔和电影光线",
        "i2v": "让关键帧之间自然过渡，保持主体结构一致，镜头运动平稳",
        "v2v": "保留原视频动作与构图，转换为柔和电影光线的高质感场景",
    }[mode]
    nodes.append(
        flux_node(
            model_id,
            model,
            f"FLUX 3 {region}{label}",
            prompt,
            input_links,
            video_link,
            len(nodes),
            [420, 60],
        )
    )

    source_by_link = {
        link: node["id"]
        for node in nodes
        for output in node.get("outputs", [])
        for link in (output.get("links") or [])
        if link != video_link
    }
    destination = {
        "api_config": 0,
        **{f"image{index}": index for index in range(1, 11)},
        "input_video": 11,
    }
    for name, link_id in input_links.items():
        media_type = (
            CONFIG_TYPE
            if name == "api_config"
            else "IMAGE"
            if name.startswith("image")
            else "VIDEO"
        )
        links.append(
            [
                link_id,
                source_by_link[link_id],
                1 if name == "api_config" else 0,
                model_id,
                destination[name],
                media_type,
            ]
        )

    save_id = model_id + 1
    nodes.append(
        save_node(
            save_id,
            video_link,
            len(nodes),
            f"video/flux3/{model}",
            [1040, 200],
        )
    )
    links.append([video_link, model_id, 0, save_id, 0, "VIDEO"])
    return filename, workflow_document(filename, nodes, links)


def main() -> None:
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    for model in HAILUO_MODELS:
        filename, workflow = hailuo_workflow(model)
        (WORKFLOW_DIR / filename).write_text(
            json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(filename)
    for model in FLUX3_MODELS:
        filename, workflow = flux_workflow(model)
        (WORKFLOW_DIR / filename).write_text(
            json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(filename)


if __name__ == "__main__":
    main()
