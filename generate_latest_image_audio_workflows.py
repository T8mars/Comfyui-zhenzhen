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
    "zhenzhen-image-gk-v2文生图.json",
    "zhenzhen-image-gk-v2-edit图像编辑.json",
    "wan-2.7-global-t2i文生图.json",
    "wan-2.7-global-i2i图像编辑.json",
    "wan-2.7-global-i2i-pro图像编辑.json",
    "qwen3-tts-flash语音合成.json",
    "qwen3-tts-instruct-flash指令语音.json",
    "minimax-music-2.6音乐生成.json",
    "minimax-speech-2.8-hd高清语音.json",
    "minimax-speech-2.8-turbo快速语音.json",
    "minimax-voice-clone声音克隆.json",
    "mureka-v8-bgm背景音乐.json",
    "mureka-v9-bgm背景音乐.json",
)

NODE_TYPE_MAP = {
    "Zhenzhen_Image_GK_V2": "Comfly_zhenzhen_image_gk_v2_lowprice",
    "Zhenzhen_Image_GK_V2_Edit": "Comfly_zhenzhen_image_gk_v2_edit_lowprice",
    "Wan_2_7_Global_Image": "Comfly_wan_2_7_global_image_lowprice",
    "Qwen3_TTS": "Comfly_qwen3_tts_lowprice",
    "Minimax_Audio": "Comfly_minimax_audio_lowprice",
    "Mureka_BGM": "Comfly_mureka_bgm_lowprice",
}


def target_filename(source_name: str) -> str:
    stem = Path(source_name).stem
    if not stem.startswith("zhenzhen-"):
        stem = f"zhenzhen-{stem}"
    return f"{stem}（贞贞的平价AI小屋）.json"


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
            continue

        mapped = NODE_TYPE_MAP.get(node_type)
        if mapped:
            node["type"] = mapped
            node["properties"] = {
                "cnr_id": "zhenzhen",
                "ver": "2.0.2",
                "Node name for S&R": mapped,
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
