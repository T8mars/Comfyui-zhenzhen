from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REFERENCE_DIR = ROOT.parent / "ComfyUI_Seedance" / "examples"
WORKFLOW_DIR = ROOT / "workflow"
CONFIG_TYPE = "ZHENZHEN_SEEDANCE2_CONFIG"

SOURCE_FILES = (
    "flowmusic-generation音乐生成.json",
    "flowmusic-lyrics歌词生成.json",
    "flowmusic-upload-audio上传音频.json",
    "flowmusic-extend音乐续写.json",
    "flowmusic-replace片段替换.json",
    "flowmusic-cover整曲改编.json",
    "flowmusic-stems人声伴奏分离.json",
    "flowmusic-download-audio下载音频.json",
    "flowmusic-video-clip音乐视频.json",
)


def target_filename(source_name: str) -> str:
    return f"zhenzhen-{Path(source_name).stem}（贞贞的平价AI小屋）.json"


def transform(source_name: str) -> tuple[str, dict]:
    source = json.loads((REFERENCE_DIR / source_name).read_text(encoding="utf-8"))
    workflow = copy.deepcopy(source)
    filename = target_filename(source_name)
    workflow["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"comfyui-zhenzhen/{filename}"))

    for node in workflow.get("nodes", []):
        node_type = node.get("type")
        if node_type == "Seedance_Config":
            node["type"] = "Comfly_seedance2_low_price_settings"
            node["title"] = "Zhenzhen API Settings（国内版）"
            node["outputs"] = [
                {
                    "name": "api_config",
                    "type": CONFIG_TYPE,
                    "links": node.get("outputs", [{}])[0].get("links"),
                }
            ]
            node["properties"] = {
                "cnr_id": "zhenzhen",
                "ver": "2.0.2",
                "Node name for S&R": "Comfly_seedance2_low_price_settings",
            }
            node["widgets_values"] = ["https://api.seedance.nz", ""]
        elif node_type == "Flow_Music":
            node["type"] = "Comfly_flowmusic_lowprice"
            node["properties"] = {
                "cnr_id": "zhenzhen",
                "ver": "2.0.2",
                "Node name for S&R": "Comfly_flowmusic_lowprice",
            }

        for input_item in node.get("inputs", []):
            if input_item.get("type") == "SEEDANCE_CONFIG":
                input_item["type"] = CONFIG_TYPE
        for output in node.get("outputs", []):
            if output.get("type") == "SEEDANCE_CONFIG":
                output["type"] = CONFIG_TYPE

    for link in workflow.get("links", []):
        if len(link) > 5 and link[5] == "SEEDANCE_CONFIG":
            link[5] = CONFIG_TYPE
    return filename, workflow


def main() -> None:
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    for source_name in SOURCE_FILES:
        filename, workflow = transform(source_name)
        path = WORKFLOW_DIR / filename
        path.write_text(
            json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(path.name)


if __name__ == "__main__":
    main()
