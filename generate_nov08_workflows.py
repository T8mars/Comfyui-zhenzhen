"""Generate only the examples for the November 8 model update."""

import copy
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tests"))
from nov08_fixture import module, flash

plugin = module("Comfly")
parallel = module("ComflyConcurrent")
MAPPINGS = {**plugin.NODE_CLASS_MAPPINGS, **parallel.CONCURRENT_NODE_CLASS_MAPPINGS}
KLING_KEY = "T8Zhenzhen_Kling_V4_Omni_LowPrice"
OMNI_KEY = "T8Zhenzhen_Video_G_Omni_12_Flash_LowPrice"
TEMPLATE = json.loads((ROOT / "workflow/kling-v4-omni-image-video-lowprice.json").read_text(encoding="utf-8"))
NATIVE = {node["type"]: node for node in TEMPLATE["nodes"]}


def native(kind, identifier, position):
    node = copy.deepcopy(NATIVE[kind])
    node.update(id=identifier, pos=position, order=identifier - 1)
    for item in node.get("inputs", []):
        item["link"] = None
    for item in node.get("outputs", []):
        item["links"] = None
    return node


def generated(key, identifier, values=None, position=None):
    cls = MAPPINGS[key]
    schema = cls.INPUT_TYPES()
    inputs, widgets = [], []
    values = values or {}
    for group in ("required", "optional"):
        for name, spec in schema.get(group, {}).items():
            kind, options = spec[0], spec[1] if len(spec) > 1 else {}
            if isinstance(kind, list) or kind in {"STRING", "INT", "FLOAT", "BOOLEAN"}:
                widgets.append(values.get(name, options.get("default", kind[0] if isinstance(kind, list) else "")))
                if options.get("control_after_generate"):
                    widgets.append("fixed")
            else:
                inputs.append({"name": name, "type": str(kind), "shape": 7, "link": None})
    return {"id": identifier, "type": key, "pos": position or [450, 40], "size": [550, 650],
        "flags": {}, "order": identifier - 1, "mode": 0, "inputs": inputs,
        "outputs": [{"name": name, "type": str(kind), "links": None} for name, kind in zip(cls.RETURN_NAMES, cls.RETURN_TYPES)],
        "properties": {"Node name for S&R": key, "cnr_id": "zhenzhen"}, "widgets_values": widgets}


def connect(workflow, source, output, target, field):
    index = next(i for i, item in enumerate(target["inputs"]) if item["name"] == field)
    identifier = len(workflow["links"]) + 1
    source["outputs"][output]["links"] = (source["outputs"][output]["links"] or []) + [identifier]
    target["inputs"][index]["link"] = identifier
    workflow["links"].append([identifier, source["id"], output, target["id"], index, target["inputs"][index]["type"]])


def document(name):
    return {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, "zhenzhen-nov08/" + name)), "revision": 0,
        "last_node_id": 0, "last_link_id": 0, "nodes": [], "links": [], "groups": [], "config": {},
        "extra": {"ds": {"scale": .7, "offset": [20, 20]}}, "version": .4}


def save(name, workflow):
    workflow["last_node_id"] = max(node["id"] for node in workflow["nodes"])
    workflow["last_link_id"] = len(workflow["links"])
    (ROOT / "workflow" / (name + ".json")).write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    for key, model in ((KLING_KEY, flash.KLING_MODEL), (OMNI_KEY, flash.OMNI_MODEL)):
        for mode in ("text", "images", "local-video", "url-video"):
            workflow = document(model + mode)
            settings = native("T8Zhenzhen_API_Settings", 1, [30, 440])
            values = {"model": model, "prompt": "A white geometric sculpture rotates slowly in a blue studio.",
                "seconds": 3, "resolution": "720p", "video_urls": "https://example.com/reference.mp4" if mode == "url-video" else ""}
            node = generated(key, 2, values)
            workflow["nodes"] = [settings, node]
            connect(workflow, settings, 1, node, "api_config")
            if mode == "images":
                for index in (1, 2):
                    source = native("LoadImage", len(workflow["nodes"]) + 1, [30, 30 + (index - 1) * 300])
                    source["widgets_values"][0] = f"select_reference_{index}.png"
                    workflow["nodes"].append(source)
                    connect(workflow, source, 0, node, f"image{index}")
            if mode == "local-video":
                source = native("LoadVideo", 3, [30, 40])
                workflow["nodes"].append(source)
                connect(workflow, source, 0, node, "video1")
            sink = native("SaveVideo", len(workflow["nodes"]) + 1, [1080, 40])
            sink["widgets_values"][0] = "zhenzhen/" + model + "-" + mode
            workflow["nodes"].append(sink)
            connect(workflow, node, 0, sink, "video")
            save(model + "-" + mode, workflow)
    for resolution in ("2k", "4k"):
        name = "zhenzhen-image-g-v2.6-lowprice-" + resolution
        workflow = document(name)
        settings = native("T8Zhenzhen_API_Settings", 1, [30, 400])
        node = generated("T8Zhenzhen_Image_G26_LowPrice", 2, {"resolution": resolution,
            "prompt": "A white ceramic teapot on a light gray studio table, soft light and fine surface detail.",
            "quality": "high", "filename_prefix": "zhenzhen/" + name})
        sink = {"id": 3, "type": "SaveImage", "pos": [1080, 40], "size": [300, 280], "flags": {}, "order": 2, "mode": 0,
            "inputs": [{"name": "images", "type": "IMAGE", "link": None}], "outputs": [],
            "properties": {"Node name for S&R": "SaveImage"}, "widgets_values": ["zhenzhen/" + name]}
        workflow["nodes"] = [settings, node, sink]
        connect(workflow, settings, 1, node, "api_config")
        connect(workflow, node, 0, sink, "images")
        save(name, workflow)
    name = "nov08-flash-video-concurrent-lowprice"
    workflow = document(name)
    settings = native("T8Zhenzhen_API_Settings", 1, [30, 380])
    collector = generated("ComflyConcurrent_Video_Await", 4, position=[1060, 40])
    workflow["nodes"] = [settings, collector]
    for index, (key, model) in enumerate(((KLING_KEY, flash.KLING_MODEL), (OMNI_KEY, flash.OMNI_MODEL)), 1):
        source = generated(f"ComflyConcurrent_{key}_Submit", index + 1,
            {"model": model, "prompt": "A white geometric sculpture rotates slowly in a blue studio."}, [450, 40 + (index - 1) * 730])
        sink = native("SaveVideo", index + 4, [1700, 40 + (index - 1) * 330])
        sink["widgets_values"][0] = "zhenzhen/concurrent-" + model
        workflow["nodes"].extend([source, sink])
        connect(workflow, settings, 1, source, "api_config")
        connect(workflow, source, 0, collector, f"task_{index}")
        connect(workflow, collector, index - 1, sink, "video")
    save(name, workflow)
    print("Saved 11 blank-key November 8 workflows; existing examples unchanged.")


if __name__ == "__main__":
    main()
