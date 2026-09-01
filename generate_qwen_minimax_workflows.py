from __future__ import annotations

import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW_DIR = ROOT / "workflow"
CONFIG_TYPE = "ZHENZHEN_SEEDANCE2_CONFIG"
PLUGIN_VERSION = "2.0.2"

QWEN_MODELS = (
    "qwen-image-3.0-t2i",
    "qwen-image-3.0-i2i",
    "qwen-image-3.0-pro-t2i",
    "qwen-image-3.0-pro-i2i",
    "qwen-image-3.0-global-t2i",
    "qwen-image-3.0-global-i2i",
    "qwen-image-3.0-global-pro-t2i",
    "qwen-image-3.0-global-pro-i2i",
)
MINIMAX_MODELS = (
    "minimax-h3-ow-t2v",
    "minimax-h3-ow-r2v",
    "minimax-h3-ow-i2v",
)
MINIMAX_FAST_MODELS = (
    "minimax-h3-ow-i2v-fast",
    "minimax-h3-ow-r2v-fast",
    "minimax-h3-ow-fl2va-audio-drive-fast",
    "minimax-h3-ow-ref2va-audio-drive-fast",
    "minimax-h3-ow-t2v-fast",
)
MINIMAX_FAST_AUDIO_MODELS = (
    "minimax-h3-ow-fl2va-audio-drive-fast",
    "minimax-h3-ow-ref2va-audio-drive-fast",
)
MINIMAX_WORKFLOW_FILENAMES = {
    "minimax-h3-ow-t2v": "zhenzhen-minimax-h3-ow-t2v文生视频（贞贞的平价AI小屋）.json",
    "minimax-h3-ow-r2v": "zhenzhen-minimax-h3-ow-r2v参考图生视频（贞贞的平价AI小屋）.json",
    "minimax-h3-ow-i2v": "zhenzhen-minimax-h3-ow-i2v图生视频（贞贞的平价AI小屋）.json",
    "minimax-h3-ow-i2v-fast": "zhenzhen-minimax-h3-ow-fast-i2v图生视频（贞贞的平价AI小屋）.json",
    "minimax-h3-ow-r2v-fast": "zhenzhen-minimax-h3-ow-fast-r2v参考生视频（贞贞的平价AI小屋）.json",
    "minimax-h3-ow-fl2va-audio-drive-fast": "zhenzhen-minimax-h3-ow-fl2va-audio-drive-fast音频驱动视频（贞贞的平价AI小屋）.json",
    "minimax-h3-ow-ref2va-audio-drive-fast": "zhenzhen-minimax-h3-ow-ref2va-audio-drive-fast音频驱动视频（贞贞的平价AI小屋）.json",
    "minimax-h3-ow-t2v-fast": "zhenzhen-minimax-h3-ow-t2v-fast文生视频（贞贞的平价AI小屋）.json",
}


def node_properties(node_type: str, core: bool = False) -> dict:
    return {
        "cnr_id": "comfy-core" if core else "zhenzhen",
        "ver": "0.27.0" if core else PLUGIN_VERSION,
        "Node name for S&R": node_type,
    }


def load_image(node_id: int, link_id: int, filename: str = "选择参考图.png") -> dict:
    return {
        "id": node_id,
        "type": "LoadImage",
        "title": filename,
        "pos": [30, 40],
        "size": [270, 314],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [],
        "outputs": [
            {"name": "IMAGE", "type": "IMAGE", "links": [link_id]},
            {"name": "MASK", "type": "MASK", "links": None},
        ],
        "properties": node_properties("LoadImage", core=True),
        "widgets_values": [filename, "image"],
    }


def load_audio(node_id: int, link_id: int, filename: str = "选择驱动音频.wav") -> dict:
    return {
        "id": node_id,
        "type": "LoadAudio",
        "title": filename,
        "pos": [30, 390],
        "size": [270, 130],
        "flags": {},
        "order": 1,
        "mode": 0,
        "inputs": [],
        "outputs": [{"name": "AUDIO", "type": "AUDIO", "links": [link_id]}],
        "properties": node_properties("LoadAudio", core=True),
        "widgets_values": [filename, None, ""],
    }


def settings_node(node_id: int, link_ids: list[int], order: int, pos: list[int]) -> dict:
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
        "properties": node_properties("T8Zhenzhen_API_Settings"),
        "widgets_values": ["seedance_low_price", "", "", False],
    }


def base_workflow(name: str, nodes: list[dict], links: list[list], last_node: int, last_link: int) -> dict:
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"comfyui-zhenzhen/{name}")),
        "revision": 0,
        "last_node_id": last_node,
        "last_link_id": last_link,
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {"frontendVersion": "1.45.20"},
        "version": 0.4,
    }


def save_image_node(node_id: int, link_id: int, prefix: str, order: int) -> dict:
    return {
        "id": node_id,
        "type": "SaveImage",
        "pos": [980, 150],
        "size": [280, 270],
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": [{"name": "images", "type": "IMAGE", "link": link_id}],
        "outputs": [{"name": "images", "type": "IMAGE", "links": None}],
        "properties": node_properties("SaveImage", core=True),
        "widgets_values": [prefix],
    }


def save_video_node(node_id: int, link_id: int, prefix: str, order: int) -> dict:
    return {
        "id": node_id,
        "type": "SaveVideo",
        "pos": [980, 170],
        "size": [300, 190],
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": [{"name": "video", "type": "VIDEO", "link": link_id}],
        "outputs": [{"name": "video", "type": "VIDEO", "links": None}],
        "properties": node_properties("SaveVideo", core=True),
        "widgets_values": [prefix, "auto", "auto"],
    }


def qwen_workflow(model: str) -> tuple[str, dict]:
    editing = model.endswith("-i2i")
    load_id = 1 if editing else None
    settings_id = 2 if editing else 1
    qwen_id = settings_id + 1
    save_id = qwen_id + 1
    image_link = 1 if editing else None
    config_link = 2 if editing else 1
    result_link = config_link + 1
    short = model.replace("qwen-image-3.0-", "")
    mode_name = "图像编辑" if editing else "文生图"
    filename = f"zhenzhen-{model}{mode_name}（贞贞的平价AI小屋）.json"
    nodes = []
    links = []
    if editing:
        nodes.append(load_image(load_id, image_link))
        links.append([image_link, load_id, 0, qwen_id, 1, "IMAGE"])
    nodes.append(
        settings_node(
            settings_id,
            [config_link],
            1 if editing else 0,
            [30, 390 if editing else 430],
        )
    )
    qwen_inputs = [
        {"name": "api_config", "shape": 7, "type": CONFIG_TYPE, "link": config_link},
        {"name": "image1", "shape": 7, "type": "IMAGE", "link": image_link},
        {"name": "image2", "shape": 7, "type": "IMAGE", "link": None},
        {"name": "image3", "shape": 7, "type": "IMAGE", "link": None},
    ]
    nodes.append({
        "id": qwen_id,
        "type": "Comfly_qwen_image_3_0_lowprice",
        "title": f"Qwen Image 3.0 {mode_name}（{short}）",
        "pos": [400, 70],
        "size": [500, 570],
        "flags": {},
        "order": 2 if editing else 1,
        "mode": 0,
        "inputs": qwen_inputs,
        "outputs": [
            {"name": "image", "type": "IMAGE", "links": [result_link]},
            {"name": "image_url", "type": "STRING", "links": None},
            {"name": "task_id", "type": "STRING", "links": None},
            {"name": "response", "type": "STRING", "links": None},
        ],
        "properties": node_properties("Comfly_qwen_image_3_0_lowprice"),
        "widgets_values": [
            model,
            "保持主体结构清晰，使用干净的摄影棚光线和细腻材质" if editing else "一件精致的玻璃工艺品放在白色摄影台上，柔和自然光，细节清晰",
            "模糊，低清晰度",
            True,
            "auto",
            "1k",
            "1:1",
            "1024*1024",
            1,
            -1,
            False,
        ],
    })
    nodes.append(save_image_node(save_id, result_link, f"qwen_image_3/{short}", 3 if editing else 2))
    links.extend([
        [config_link, settings_id, 1, qwen_id, 0, CONFIG_TYPE],
        [result_link, qwen_id, 0, save_id, 0, "IMAGE"],
    ])
    return filename, base_workflow(filename, nodes, links, save_id, result_link)


def minimax_workflow(model: str) -> tuple[str, dict]:
    fast = model in MINIMAX_FAST_MODELS
    audio_drive = model in MINIMAX_FAST_AUDIO_MODELS
    t2v_fast = model == "minimax-h3-ow-t2v-fast"
    needs_image = (
        model.endswith("-i2v")
        or model.endswith("-r2v")
        or "-i2v-fast" in model
        or "-r2v-fast" in model
        or audio_drive
    )
    next_node_id = 1
    next_link_id = 1
    load_id = next_node_id if needs_image else None
    if needs_image:
        next_node_id += 1
        image_link = next_link_id
        next_link_id += 1
    else:
        image_link = None
    audio_id = next_node_id if audio_drive else None
    if audio_drive:
        next_node_id += 1
        audio_link = next_link_id
        next_link_id += 1
    else:
        audio_link = None
    settings_id = next_node_id
    model_id = settings_id + 1
    save_id = model_id + 1
    config_link = next_link_id
    result_link = config_link + 1
    mode_name = (
        "文生视频"
        if "-t2v" in model
        else (
            "音频驱动视频"
            if audio_drive
            else ("参考生视频" if "-r2v" in model else "图生视频")
        )
    )
    filename = MINIMAX_WORKFLOW_FILENAMES[model]
    nodes = []
    links = []
    if needs_image:
        nodes.append(load_image(load_id, image_link))
        links.append([image_link, load_id, 0, model_id, 0, "IMAGE"])
    if audio_drive:
        nodes.append(load_audio(audio_id, audio_link))
        links.append([audio_link, audio_id, 0, model_id, 10, "AUDIO"])
    nodes.append(
        settings_node(
            settings_id,
            [config_link],
            int(needs_image) + int(audio_drive),
            [30, 560 if audio_drive else (390 if needs_image else 430)],
        )
    )
    fast_inputs = [
        {
            "name": f"image{index}",
            "shape": 7,
            "type": "IMAGE",
            "link": image_link if index == 1 else None,
        }
        for index in range(1, 10)
    ] + [{"name": "api_config", "shape": 7, "type": CONFIG_TYPE, "link": config_link}]
    if audio_drive or t2v_fast:
        fast_inputs.append({
            "name": "audio",
            "shape": 7,
            "type": "AUDIO",
            "link": audio_link,
        })
    nodes.append({
        "id": model_id,
        "type": (
            "Comfly_minimax_h3_ow_fast_video_lowprice"
            if fast
            else "Comfly_minimax_h3_ow_video_lowprice"
        ),
        "title": f"MiniMax H3 OW{' Fast' if fast else ''} {mode_name}",
        "pos": [400, 90],
        "size": [470, 410],
        "flags": {},
        "order": int(needs_image) + int(audio_drive) + 1,
        "mode": 0,
        "inputs": (
            fast_inputs
            if fast
            else [
                {"name": "image1", "shape": 7, "type": "IMAGE", "link": image_link},
                {"name": "api_config", "shape": 7, "type": CONFIG_TYPE, "link": config_link},
            ]
        ),
        "outputs": [
            {"name": "video", "type": "VIDEO", "links": [result_link]},
            {"name": "video_url", "type": "STRING", "links": None},
            {"name": "task_id", "type": "STRING", "links": None},
            {"name": "response", "type": "STRING", "links": None},
        ],
        "properties": node_properties(
            "Comfly_minimax_h3_ow_fast_video_lowprice"
            if fast
            else "Comfly_minimax_h3_ow_video_lowprice"
        ),
        "widgets_values": [
            model,
            (
                "保持参考主体一致，表演动作由所连接音频自然驱动，镜头稳定"
                if audio_drive
                else (
                    "保持参考主体一致，镜头缓慢环绕，动作自然连贯"
                    if needs_image
                    else "一只白色纸飞机穿过清晨的玻璃温室，镜头平稳跟随，电影感光线"
                )
            ),
            "5",
            "480p",
            "16:9",
            False,
            *([0, "fixed"] if audio_drive or t2v_fast else []),
        ],
    })
    nodes.append(save_video_node(
        save_id,
        result_link,
        f"video/{model}",
        int(needs_image) + int(audio_drive) + 2,
    ))
    links.extend([
        [config_link, settings_id, 1, model_id, 9 if fast else 1, CONFIG_TYPE],
        [result_link, model_id, 0, save_id, 0, "VIDEO"],
    ])
    return filename, base_workflow(filename, nodes, links, save_id, result_link)


def concurrent_workflow(kind: str) -> tuple[str, dict]:
    image = kind == "image"
    slot_count = 30 if image else 10
    task_type = "COMFLY_IMAGE_FUTURE" if image else "COMFLY_VIDEO_FUTURE"
    collector_type = "ComflyConcurrent_Image_Await" if image else "ComflyConcurrent_Video_Await"
    original_type = (
        "Comfly_qwen_image_3_0_lowprice"
        if image
        else "Comfly_minimax_h3_ow_video_lowprice"
    )
    submit_type = f"ComflyConcurrent_{original_type}_Submit"
    filename = (
        "zhenzhen-qwen-image-3.0并发示例（贞贞的平价AI小屋）.json"
        if image
        else "zhenzhen-minimax-h3-ow并发示例（贞贞的平价AI小屋）.json"
    )
    settings = settings_node(1, [1, 2], 0, [30, 430])
    submit_nodes = []
    models = (
        ("qwen-image-3.0-t2i", "qwen-image-3.0-pro-t2i")
        if image
        else ("minimax-h3-ow-t2v", "minimax-h3-ow-t2v")
    )
    prompts = (
        "蓝色玻璃立方体放在白色摄影台上，柔和自然光，细节清晰",
        "红色金属球体放在白色摄影台上，柔和自然光，细节清晰",
    ) if image else (
        "一只白色纸飞机穿过清晨的玻璃温室，镜头平稳跟随",
        "日落时城市灯光逐渐亮起，缓慢稳定的航拍镜头",
    )
    for index in range(2):
        node_id = index + 2
        config_slot = 0 if image else 1
        inputs = (
            [
                {"name": "api_config", "shape": 7, "type": CONFIG_TYPE, "link": index + 1},
                {"name": "image1", "shape": 7, "type": "IMAGE", "link": None},
                {"name": "image2", "shape": 7, "type": "IMAGE", "link": None},
                {"name": "image3", "shape": 7, "type": "IMAGE", "link": None},
            ]
            if image
            else [
                {"name": "image1", "shape": 7, "type": "IMAGE", "link": None},
                {"name": "api_config", "shape": 7, "type": CONFIG_TYPE, "link": index + 1},
            ]
        )
        widgets = (
            [models[index], prompts[index], "", True, "auto", "1k", "1:1", "1024*1024", 1, -1, False]
            if image
            else [models[index], prompts[index], "5", "480p", "16:9", False]
        )
        submit_nodes.append({
            "id": node_id,
            "type": submit_type,
            "title": f"并发提交 {index + 1}",
            "pos": [400, 30 + index * 440],
            "size": [480, 390],
            "flags": {},
            "order": index + 1,
            "mode": 0,
            "inputs": inputs,
            "outputs": [{"name": "task", "type": task_type, "links": [index + 3]}],
            "properties": node_properties(submit_type),
            "widgets_values": widgets,
        })

    collector_inputs = [
        {
            "name": f"task_{index}",
            "shape": 7,
            "type": task_type,
            "link": index + 2 if index <= 2 else None,
        }
        for index in range(1, slot_count + 1)
    ]
    collector_outputs = [
        {
            "name": f"{'image' if image else 'video'}_{index}",
            "type": "IMAGE" if image else "VIDEO",
            "links": [index + 4] if index <= 2 else None,
        }
        for index in range(1, slot_count + 1)
    ]
    collector_outputs.append({"name": "status", "type": "STRING", "links": None})
    collector = {
        "id": 4,
        "type": collector_type,
        "title": f"并发接收{'图片' if image else '视频'}",
        "pos": [940, 220],
        "size": [360, 760 if image else 430],
        "flags": {},
        "order": 3,
        "mode": 0,
        "inputs": collector_inputs,
        "outputs": collector_outputs,
        "properties": node_properties(collector_type),
        "widgets_values": ["fail_fast"],
    }
    saves = (
        [
            save_image_node(5, 5, "qwen_image_3/concurrent_1", 4),
            save_image_node(6, 6, "qwen_image_3/concurrent_2", 5),
        ]
        if image
        else [
            save_video_node(5, 5, "video/minimax_h3_ow_concurrent_1", 4),
            save_video_node(6, 6, "video/minimax_h3_ow_concurrent_2", 5),
        ]
    )
    saves[0]["pos"] = [1370, 100]
    saves[1]["pos"] = [1370, 440]
    links = [
        [1, 1, 1, 2, 0 if image else 1, CONFIG_TYPE],
        [2, 1, 1, 3, 0 if image else 1, CONFIG_TYPE],
        [3, 2, 0, 4, 0, task_type],
        [4, 3, 0, 4, 1, task_type],
        [5, 4, 0, 5, 0, "IMAGE" if image else "VIDEO"],
        [6, 4, 1, 6, 0, "IMAGE" if image else "VIDEO"],
    ]
    return filename, base_workflow(
        filename,
        [settings, *submit_nodes, collector, *saves],
        links,
        6,
        6,
    )


def write_workflow(filename: str, workflow: dict) -> None:
    path = WORKFLOW_DIR / filename
    path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    for model in QWEN_MODELS:
        write_workflow(*qwen_workflow(model))
    for model in MINIMAX_MODELS:
        write_workflow(*minimax_workflow(model))
    for model in MINIMAX_FAST_MODELS:
        write_workflow(*minimax_workflow(model))
    write_workflow(*concurrent_workflow("image"))
    write_workflow(*concurrent_workflow("video"))
    print(
        "Generated "
        f"{len(QWEN_MODELS) + len(MINIMAX_MODELS) + len(MINIMAX_FAST_MODELS) + 2} "
        "workflows"
    )


if __name__ == "__main__":
    main()
