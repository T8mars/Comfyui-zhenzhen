"""Generate credential-free Seedream V5 Flash example workflows."""

import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW_DIR = ROOT / "workflow"
PLUGIN_ID = "zhenzhen"
CONFIG_NODE = "T8Zhenzhen_API_Settings"
IMAGE_NODE = "Comfly_sd2_seedream_v5_pro_lowprice"
LAYER_NODE = "Comfly_seedream_v5_pro_layer_decomposition_lowprice"


def node(node_id, node_type, pos, size, order, inputs, outputs, widgets, title=None):
    properties = {"Node name for S&R": node_type}
    if node_type not in {"LoadImage", "SaveImage", "JoinImageWithAlpha"}:
        properties["cnr_id"] = PLUGIN_ID
    else:
        properties["cnr_id"] = "comfy-core"
    result = {
        "id": node_id,
        "type": node_type,
        "pos": list(pos),
        "size": list(size),
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": inputs,
        "outputs": outputs,
        "properties": properties,
        "widgets_values": widgets,
    }
    if title:
        result["title"] = title
    return result


def config_node(link_id, target_id, target_slot):
    config = node(
        1,
        CONFIG_NODE,
        (60, 80),
        (340, 175),
        0,
        [],
        [
            {"name": "apikey", "type": "STRING", "links": None},
            {"name": "api_config", "type": "ZHENZHEN_SEEDANCE2_CONFIG", "links": [link_id]},
        ],
        ["seedance_low_price", "", "", False],
    )
    return config, [link_id, 1, 1, target_id, target_slot, "ZHENZHEN_SEEDANCE2_CONFIG"]


def load_image(node_id, link_id, filename="请选择参考图片.png"):
    return node(
        node_id,
        "LoadImage",
        (60, 300),
        (315, 314),
        0,
        [],
        [
            {"name": "IMAGE", "type": "IMAGE", "links": [link_id]},
            {"name": "MASK", "type": "MASK", "links": None},
        ],
        [filename, "image"],
    )


def save_image(node_id, link_id, prefix, order):
    return node(
        node_id,
        "SaveImage",
        (1120, 135),
        (315, 270),
        order,
        [{"name": "images", "type": "IMAGE", "link": link_id}],
        [{"name": "images", "type": "IMAGE", "links": None}],
        [prefix],
    )


def write_workflow(filename, nodes, links):
    workflow = {
        "id": str(uuid.uuid4()),
        "revision": 0,
        "last_node_id": max(item["id"] for item in nodes),
        "last_link_id": max(link[0] for link in links),
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {"ds": {"scale": 0.85, "offset": [80, 120]}},
        "version": 0.4,
    }
    path = WORKFLOW_DIR / filename
    path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path.name)


def image_workflow(prefix, family, editing):
    mode_label = "图像编辑" if editing else "文生图"
    filename = f"zhenzhen-{prefix}{mode_label}（贞贞的平价AI小屋）.json"
    generator_id = 3 if editing else 2
    config_link_id = 2 if editing else 1
    output_link_id = config_link_id + 1
    config, config_link = config_node(config_link_id, generator_id, 0)
    nodes = [config]
    links = [config_link]
    inputs = [
        {"name": "api_config", "shape": 7, "type": "ZHENZHEN_SEEDANCE2_CONFIG", "link": config_link_id}
    ]
    if editing:
        nodes.append(load_image(2, 1))
        links.append([1, 2, 0, generator_id, 1, "IMAGE"])
    for index in range(1, 11):
        inputs.append({
            "name": f"image{index}",
            "shape": 7,
            "type": "IMAGE",
            "link": 1 if editing and index == 1 else None,
        })
    prompt = (
        "保留主体身份与构图，将背景改为雨后街景，暖色电影灯光，细节清晰"
        if editing
        else "雨后街角的咖啡店，暖色灯光，电影质感，细节清晰"
    )
    generator = node(
        generator_id,
        IMAGE_NODE,
        (430, 80),
        (560, 600),
        2 if editing else 1,
        inputs,
        [
            {"name": "image", "type": "IMAGE", "links": [output_link_id]},
            {"name": "image_url", "type": "STRING", "links": None},
            {"name": "task_id", "type": "STRING", "links": None},
            {"name": "response", "type": "STRING", "links": None},
        ],
        [
            "image_edit" if editing else "text_to_image",
            prompt,
            "1k",
            1024,
            1024,
            "png",
            False,
            family,
            0,
            "fixed",
        ],
        f"{prefix} {mode_label}",
    )
    nodes.append(generator)
    save_id = generator_id + 1
    nodes.append(save_image(save_id, output_link_id, Path(filename).stem, 3 if editing else 2))
    links.append([output_link_id, generator_id, 0, save_id, 0, "IMAGE"])
    write_workflow(filename, nodes, links)


def layer_workflow(prefix, model):
    filename = f"zhenzhen-{prefix}图层拆分（贞贞的平价AI小屋）.json"
    config, config_link = config_node(2, 3, 1)
    source = load_image(2, 1, "请选择待拆分图片.png")
    layer = node(
        3,
        LAYER_NODE,
        (430, 80),
        (530, 400),
        2,
        [
            {"name": "image", "type": "IMAGE", "link": 1},
            {"name": "api_config", "shape": 7, "type": "ZHENZHEN_SEEDANCE2_CONFIG", "link": 2},
        ],
        [
            {"name": "images", "type": "IMAGE", "links": [3]},
            {"name": "masks", "type": "MASK", "links": [4]},
            {"name": "image_urls", "type": "STRING", "links": None},
            {"name": "image_count", "type": "INT", "links": None},
            {"name": "task_id", "type": "STRING", "links": None},
            {"name": "response", "type": "STRING", "links": None},
        ],
        ["", "auto", "png", False, 0, "fixed", model],
        f"{prefix} 图层拆分",
    )
    join = node(
        4,
        "JoinImageWithAlpha",
        (1010, 115),
        (280, 100),
        3,
        [
            {"name": "image", "type": "IMAGE", "link": 3},
            {"name": "alpha", "type": "MASK", "link": 4},
        ],
        [{"name": "image", "type": "IMAGE", "links": [5]}],
        [],
    )
    save = save_image(5, 5, Path(filename).stem, 4)
    write_workflow(
        filename,
        [config, source, layer, join, save],
        [
            [1, 2, 0, 3, 0, "IMAGE"],
            config_link,
            [3, 3, 0, 4, 0, "IMAGE"],
            [4, 3, 1, 4, 1, "MASK"],
            [5, 4, 0, 5, 0, "IMAGE"],
        ],
    )


if __name__ == "__main__":
    families = [
        ("seedream-v5-flash", "seedream-v5-flash (domestic)"),
        ("dola-seedream-5.0-flash", "dola-seedream-5.0-flash (overseas)"),
    ]
    for prefix, family in families:
        image_workflow(prefix, family, False)
        image_workflow(prefix, family, True)
        layer_workflow(prefix, f"{prefix}-layer-decomposition")
