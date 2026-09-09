"""Generate safe example workflows for the two VOSR2 upscale nodes."""

from __future__ import annotations

import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW_DIR = ROOT / "workflow"
CONFIG_TYPE = "ZHENZHEN_SEEDANCE2_CONFIG"
SETTINGS_TYPE = "T8Zhenzhen_API_Settings"
IMAGE_NODE_TYPE = "T8Zhenzhen_VOSR2_Image_Upscale_LowPrice"
VIDEO_NODE_TYPE = "T8Zhenzhen_VOSR2_Video_Upscale_LowPrice"


def node_properties(node_type: str, *, core: bool = False) -> dict:
    properties = {"Node name for S&R": node_type}
    if core:
        properties.update({"cnr_id": "comfy-core", "ver": "0.27.0"})
    else:
        properties.update({"cnr_id": "zhenzhen", "ver": "2.3.8"})
    return properties


def settings_node(link_id: int) -> dict:
    return {
        "id": 1,
        "type": SETTINGS_TYPE,
        "title": "Zhenzhen API Settings（国内版）",
        "pos": [40, 390],
        "size": [340, 174],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [],
        "outputs": [
            {"name": "apikey", "type": "STRING", "links": None},
            {"name": "api_config", "type": CONFIG_TYPE, "links": [link_id]},
        ],
        "properties": node_properties(SETTINGS_TYPE),
        "widgets_values": ["seedance_low_price", "", "", False],
    }


def workflow_document(name: str, nodes: list[dict], links: list[list]) -> dict:
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"zhenzhen-vosr2:{name}")),
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


def image_workflow() -> dict:
    nodes = [
        settings_node(2),
        {
            "id": 2,
            "type": "LoadImage",
            "pos": [40, 40],
            "size": [300, 300],
            "flags": {},
            "order": 1,
            "mode": 0,
            "inputs": [],
            "outputs": [
                {"name": "IMAGE", "type": "IMAGE", "links": [1]},
                {"name": "MASK", "type": "MASK", "links": None},
            ],
            "properties": node_properties("LoadImage", core=True),
            "widgets_values": ["请选择一张需要4K超分的图片.png", "image"],
        },
        {
            "id": 3,
            "type": IMAGE_NODE_TYPE,
            "title": "VOSR2 4K 图片超分",
            "pos": [430, 110],
            "size": [430, 250],
            "flags": {},
            "order": 2,
            "mode": 0,
            "inputs": [
                {"name": "input_image", "shape": 7, "type": "IMAGE", "link": 1},
                {"name": "api_config", "shape": 7, "type": CONFIG_TYPE, "link": 2},
            ],
            "outputs": [
                {"name": "image", "type": "IMAGE", "links": [3]},
                {"name": "image_url", "type": "STRING", "links": None},
                {"name": "task_id", "type": "STRING", "links": None},
                {"name": "response", "type": "STRING", "links": None},
            ],
            "properties": node_properties(IMAGE_NODE_TYPE),
            "widgets_values": [False, 0, "fixed"],
        },
        {
            "id": 4,
            "type": "SaveImage",
            "pos": [940, 110],
            "size": [300, 270],
            "flags": {},
            "order": 3,
            "mode": 0,
            "inputs": [{"name": "images", "type": "IMAGE", "link": 3}],
            "outputs": [],
            "properties": node_properties("SaveImage", core=True),
            "widgets_values": ["zhenzhen-vosr2-4k-image-upscale"],
        },
    ]
    links = [
        [1, 2, 0, 3, 0, "IMAGE"],
        [2, 1, 1, 3, 1, CONFIG_TYPE],
        [3, 3, 0, 4, 0, "IMAGE"],
    ]
    return workflow_document("image", nodes, links)


def video_workflow() -> dict:
    nodes = [
        settings_node(2),
        {
            "id": 2,
            "type": "LoadVideo",
            "pos": [40, 40],
            "size": [300, 330],
            "flags": {},
            "order": 1,
            "mode": 0,
            "inputs": [],
            "outputs": [{"name": "VIDEO", "type": "VIDEO", "links": [1]}],
            "properties": node_properties("LoadVideo", core=True),
            "widgets_values": ["请选择需要2K超分的视频.mp4", "image"],
        },
        {
            "id": 3,
            "type": VIDEO_NODE_TYPE,
            "title": "VOSR2 2K 视频超分",
            "pos": [430, 110],
            "size": [430, 250],
            "flags": {},
            "order": 2,
            "mode": 0,
            "inputs": [
                {"name": "input_video", "shape": 7, "type": "VIDEO", "link": 1},
                {"name": "api_config", "shape": 7, "type": CONFIG_TYPE, "link": 2},
            ],
            "outputs": [
                {"name": "video", "type": "VIDEO", "links": [3]},
                {"name": "video_url", "type": "STRING", "links": None},
                {"name": "task_id", "type": "STRING", "links": None},
                {"name": "response", "type": "STRING", "links": None},
            ],
            "properties": node_properties(VIDEO_NODE_TYPE),
            "widgets_values": ["", False, 0, "fixed"],
        },
        {
            "id": 4,
            "type": "SaveVideo",
            "pos": [940, 135],
            "size": [300, 190],
            "flags": {},
            "order": 3,
            "mode": 0,
            "inputs": [{"name": "video", "type": "VIDEO", "link": 3}],
            "outputs": [{"name": "video", "type": "VIDEO", "links": None}],
            "properties": node_properties("SaveVideo", core=True),
            "widgets_values": ["video/zhenzhen-vosr2-2k-upscale", "auto", "auto"],
        },
    ]
    links = [
        [1, 2, 0, 3, 0, "VIDEO"],
        [2, 1, 1, 3, 1, CONFIG_TYPE],
        [3, 3, 0, 4, 0, "VIDEO"],
    ]
    return workflow_document("video", nodes, links)


def main() -> None:
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    workflows = {
        "zhenzhen-VOSR2-4K图片超分（贞贞的平价AI小屋）.json": image_workflow(),
        "zhenzhen-VOSR2-2K视频超分（贞贞的平价AI小屋）.json": video_workflow(),
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
