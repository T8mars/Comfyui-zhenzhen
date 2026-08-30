"""Convert the verified ComfyUI_Seedance Aug-22 examples for this plugin."""

from __future__ import annotations

import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REFERENCE_ROOT = ROOT.parent / "ComfyUI_Seedance" / "examples"
OUTPUT_ROOT = ROOT / "workflow"
CONFIG_TYPE = "ZHENZHEN_SEEDANCE2_CONFIG"

SOURCE_FILES = (
    "zhenzhen-video-g-omni-flash-lowprice文生视频.json",
    "zhenzhen-video-g-omni-flash-lowprice首帧生视频.json",
    "zhenzhen-video-g-omni-flash-lowprice三图参考生视频.json",
    "zhenzhen-video-g-omni-flash-lowprice参考视频生成.json",
    "zhenzhen-video-g-omni-1.1-flash-lowprice文生视频.json",
    "zhenzhen-video-g-omni-1.1-flash-lowprice首帧生视频.json",
    "zhenzhen-video-g-omni-1.1-flash-lowprice三图参考生视频.json",
    "zhenzhen-video-g-omni-1.1-flash-lowprice参考视频生成.json",
    "hunyuan3d-v3.1-text-to-3d文生3D.json",
    "hunyuan3d-v3.1-image-to-3d图生3D.json",
    "zhenzhen-image-gk-v2-segment智能分割.json",
    "zhenzhen-image-gk-v2-region-edit分割区域编辑.json",
)

NODE_TYPES = {
    "Zhenzhen_Video_G_Omni_Flash_Lowprice": (
        "Comfly_zhenzhen_video_g_omni_flash_lowprice_v2"
    ),
    "Zhenzhen_Video_G_Omni_1_1_Flash_Lowprice": (
        "Comfly_zhenzhen_video_g_omni_1_1_flash_lowprice"
    ),
    "Hunyuan3D_V3_1": "Comfly_hunyuan3d_v3_1_lowprice",
    "Zhenzhen_Image_GK_V2": "Comfly_zhenzhen_image_gk_v2_lowprice",
    "Zhenzhen_Image_GK_V2_Segment": (
        "Comfly_zhenzhen_image_gk_v2_segment_lowprice"
    ),
    "Zhenzhen_Image_GK_V2_Region_Edit": (
        "Comfly_zhenzhen_image_gk_v2_region_edit_lowprice"
    ),
}


def convert_config_node(node: dict) -> None:
    linked = copy.deepcopy(node.get("outputs", [{}])[0].get("links"))
    node["type"] = "T8Zhenzhen_API_Settings"
    node["title"] = "Zhenzhen API Settings（国内版）"
    node["widgets_values"] = ["seedance_low_price", "", "", False]
    node["outputs"] = [
        {"name": "apikey", "type": "STRING", "links": None},
        {"name": "api_config", "type": CONFIG_TYPE, "links": linked},
    ]
    properties = node.setdefault("properties", {})
    properties["Node name for S&R"] = "T8Zhenzhen_API_Settings"
    properties["cnr_id"] = "zhenzhen"


def convert_node(node: dict) -> None:
    node_type = node.get("type")
    if node_type in {"LoadImage", "LoadVideo"}:
        widgets = list(node.get("widgets_values") or [])
        if widgets:
            widgets[0] = ""
            node["widgets_values"] = widgets
    if node_type == "Seedance_Config":
        convert_config_node(node)
        return
    if node_type in NODE_TYPES:
        node["type"] = NODE_TYPES[node_type]
        properties = node.setdefault("properties", {})
        properties["Node name for S&R"] = node["type"]
        properties["cnr_id"] = "zhenzhen"
    if node_type == "Zhenzhen_Image_GK_V2_Segment":
        node["widgets_values"] = list(node.get("widgets_values") or [])[:2]
    for item in node.get("inputs") or []:
        if item.get("type") == "SEEDANCE_CONFIG":
            item["type"] = CONFIG_TYPE
    for item in node.get("outputs") or []:
        if item.get("type") == "SEEDANCE_CONFIG":
            item["type"] = CONFIG_TYPE


def convert_workflow(source: dict) -> dict:
    workflow = copy.deepcopy(source)
    config_ids = {
        int(node["id"])
        for node in workflow.get("nodes") or []
        if node.get("type") == "Seedance_Config"
    }
    for node in workflow.get("nodes") or []:
        convert_node(node)
    converted_links = []
    for link in workflow.get("links") or []:
        value = list(link)
        if int(value[1]) in config_ids:
            value[2] = 1
            value[5] = CONFIG_TYPE
        converted_links.append(value)
    workflow["links"] = converted_links
    return workflow


def generate() -> list[Path]:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    outputs = []
    for filename in SOURCE_FILES:
        source_path = REFERENCE_ROOT / filename
        workflow = json.loads(source_path.read_text(encoding="utf-8"))
        target = OUTPUT_ROOT / filename
        target.write_text(
            json.dumps(convert_workflow(workflow), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        outputs.append(target)
    return outputs


if __name__ == "__main__":
    for output in generate():
        print(output.name)
