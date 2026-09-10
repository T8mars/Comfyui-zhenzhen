"""Generate API-key-free GPT Image 2.5 example workflows."""

from __future__ import annotations

import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW_DIR = ROOT / "workflow"
SETTINGS_TYPE = "T8Zhenzhen_API_Settings"
NODE_TYPE = "T8Zhenzhen_GPT_Image_2_5_Workshop"


def node_properties(node_type: str, core: bool = False) -> dict:
    if core:
        return {
            "Node name for S&R": node_type,
            "cnr_id": "comfy-core",
            "ver": "0.27.0",
        }
    return {
        "Node name for S&R": node_type,
        "cnr_id": "zhenzhen",
        "ver": "2.3.8",
    }


def settings_node(link_id: int) -> dict:
    return {
        "id": 1,
        "type": SETTINGS_TYPE,
        "title": "Zhenzhen API Settings（AI工坊）",
        "pos": [40, 420],
        "size": [360, 174],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [],
        "outputs": [
            {"name": "apikey", "type": "STRING", "links": [link_id]},
            {
                "name": "api_config",
                "type": "ZHENZHEN_SEEDANCE2_CONFIG",
                "links": None,
            },
        ],
        "properties": node_properties(SETTINGS_TYPE),
        "widgets_values": ["zhenzhen", "", "", False],
    }


def load_image_node(node_id: int, filename: str, output_link: int, x: int) -> dict:
    return {
        "id": node_id,
        "type": "LoadImage",
        "pos": [x, 40],
        "size": [300, 300],
        "flags": {},
        "order": node_id - 1,
        "mode": 0,
        "inputs": [],
        "outputs": [
            {"name": "IMAGE", "type": "IMAGE", "links": [output_link]},
            {"name": "MASK", "type": "MASK", "links": None},
        ],
        "properties": node_properties("LoadImage", core=True),
        "widgets_values": [filename, "image"],
    }


def image_node(
    node_id: int,
    key_link: int,
    output_link: int,
    prompt: str,
    image_links: dict[int, int] | None = None,
) -> dict:
    image_links = image_links or {}
    inputs = [
        {
            "name": f"image{index}",
            "shape": 7,
            "type": "IMAGE",
            "link": image_links.get(index),
        }
        for index in range(1, 15)
    ]
    inputs.extend(
        [
            {"name": "mask", "shape": 7, "type": "MASK", "link": None},
            {
                "name": "prompt",
                "type": "STRING",
                "widget": {"name": "prompt"},
                "link": None,
            },
            {
                "name": "api_key",
                "shape": 7,
                "type": "STRING",
                "widget": {"name": "api_key"},
                "link": key_link,
            },
            {
                "name": "model",
                "type": "COMBO",
                "widget": {"name": "model"},
                "link": None,
            },
            {
                "name": "quality",
                "type": "COMBO",
                "widget": {"name": "quality"},
                "link": None,
            },
            {
                "name": "size",
                "type": "COMBO",
                "widget": {"name": "size"},
                "link": None,
            },
            {
                "name": "custom_width",
                "type": "INT",
                "widget": {"name": "custom_width"},
                "link": None,
            },
            {
                "name": "custom_height",
                "type": "INT",
                "widget": {"name": "custom_height"},
                "link": None,
            },
            {
                "name": "n",
                "type": "INT",
                "widget": {"name": "n"},
                "link": None,
            },
            {
                "name": "background",
                "type": "COMBO",
                "widget": {"name": "background"},
                "link": None,
            },
            {
                "name": "moderation",
                "type": "COMBO",
                "widget": {"name": "moderation"},
                "link": None,
            },
            {
                "name": "skip_error",
                "type": "BOOLEAN",
                "widget": {"name": "skip_error"},
                "link": None,
            },
            {
                "name": "seed",
                "type": "INT",
                "widget": {"name": "seed"},
                "link": None,
            },
        ]
    )
    return {
        "id": node_id,
        "type": NODE_TYPE,
        "title": "GPT Image 2.5（AI工坊）",
        "pos": [470, 80],
        "size": [560, 760],
        "flags": {},
        "order": node_id,
        "mode": 0,
        "inputs": inputs,
        "outputs": [
            {"name": "image", "type": "IMAGE", "links": [output_link]},
            {"name": "image_urls", "type": "STRING", "links": None},
            {"name": "response", "type": "STRING", "links": None},
        ],
        "properties": node_properties(NODE_TYPE),
        "widgets_values": [
            prompt,
            "",
            "gpt-image-2.5-flare",
            "auto",
            "1024x1024",
            1024,
            1024,
            1,
            "auto",
            "auto",
            False,
            0,
            "fixed",
        ],
    }


def save_image_node(node_id: int, input_link: int, prefix: str) -> dict:
    return {
        "id": node_id,
        "type": "SaveImage",
        "pos": [1110, 180],
        "size": [300, 270],
        "flags": {},
        "order": node_id,
        "mode": 0,
        "inputs": [{"name": "images", "type": "IMAGE", "link": input_link}],
        "outputs": [],
        "properties": node_properties("SaveImage", core=True),
        "widgets_values": [prefix],
    }


def workflow_document(name: str, nodes: list[dict], links: list[list]) -> dict:
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"zhenzhen-gpt-image-25:{name}")),
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


def text_to_image_workflow() -> dict:
    nodes = [
        settings_node(1),
        image_node(
            2,
            key_link=1,
            output_link=2,
            prompt="A cinematic product photograph of a crystal perfume bottle on black stone.",
        ),
        save_image_node(3, 2, "zhenzhen-gpt-image-2.5-text-to-image"),
    ]
    links = [
        [1, 1, 0, 2, 16, "STRING"],
        [2, 2, 0, 3, 0, "IMAGE"],
    ]
    return workflow_document("text-to-image", nodes, links)


def image_edit_workflow() -> dict:
    nodes = [
        settings_node(3),
        load_image_node(2, "请选择第一张参考图.png", 1, 20),
        load_image_node(3, "请选择第二张参考图.png", 2, 340),
        image_node(
            4,
            key_link=3,
            output_link=4,
            prompt="Combine the subjects from both references in one coherent cinematic scene.",
            image_links={1: 1, 2: 2},
        ),
        save_image_node(5, 4, "zhenzhen-gpt-image-2.5-multi-image-edit"),
    ]
    nodes[3]["pos"] = [690, 70]
    nodes[4]["pos"] = [1330, 180]
    links = [
        [1, 2, 0, 4, 0, "IMAGE"],
        [2, 3, 0, 4, 1, "IMAGE"],
        [3, 1, 0, 4, 16, "STRING"],
        [4, 4, 0, 5, 0, "IMAGE"],
    ]
    return workflow_document("image-edit", nodes, links)


def main() -> None:
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    workflows = {
        "zhenzhen-GPT-Image-2.5-文生图（贞贞的AI工坊）.json": text_to_image_workflow(),
        "zhenzhen-GPT-Image-2.5-多图编辑（贞贞的AI工坊）.json": image_edit_workflow(),
    }
    for filename, document in workflows.items():
        path = WORKFLOW_DIR / filename
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(path)


if __name__ == "__main__":
    main()
