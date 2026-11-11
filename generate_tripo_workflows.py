"""Credential-free examples for all 25 Tripo models and four linked variants."""

import copy
import json

from generate_nov08_workflows import ROOT, native, generated, document, connect, save, module

tripo = module("tripo_contracts")
nodes = module("tripo_low_price_nodes")
NATIVE_3D = {item["type"]: item for item in json.loads((ROOT / "workflow/meshy-6-global-text-to-3d-lowprice.json").read_text(encoding="utf-8"))["nodes"]}


def start(name):
    workflow = document(name)
    config = native("T8Zhenzhen_API_Settings", 1, [30, 1400])
    config["widgets_values"] = ["seedance_low_price", "", "", False]
    workflow["nodes"] = [config]
    return workflow


def add(workflow, family, values, position=None):
    node = generated(nodes.TRIPO_KEYS[family], len(workflow["nodes"]) + 1, values, position)
    workflow["nodes"].append(node)
    connect(workflow, workflow["nodes"][0], 1, node, "api_config")
    return node


def link_widget(workflow, source, output, target, name):
    if not any(item["name"] == name for item in target["inputs"]):
        target["inputs"].append({"name": name, "type": "STRING", "widget": {"name": name}, "link": None})
    connect(workflow, source, output, target, name)


def image(workflow, node, index, field=None):
    source = native("LoadImage", len(workflow["nodes"]) + 1, [30, 30 + (index - 1)*340])
    source["widgets_values"][0] = f"select_tripo_{tripo.VIEWS[index-1]}.png"
    workflow["nodes"].append(source)
    connect(workflow, source, 0, node, field or f"image{index}")


def outputs(workflow, node, x=1100, preview=True):
    for kind in (["Preview3D", "SaveGLB"] if preview else ["SaveGLB"]):
        sink = copy.deepcopy(NATIVE_3D[kind])
        sink.update(id=len(workflow["nodes"])+1, order=len(workflow["nodes"]), pos=[x, 40 if kind == "Preview3D" else 760])
        for item in sink["inputs"]:
            item["link"] = None
        if kind == "SaveGLB":
            sink["widgets_values"] = ["3d/tripo"]
        workflow["nodes"].append(sink)
        connect(workflow, node, 0, sink, "model_file" if kind == "Preview3D" else "mesh")


def main():
    for family, models in tripo.MODELS.items():
        for model in models:
            workflow = start(model)
            values = {"model": model}
            if family == "generate" and "text-to-3d" in model:
                values["prompt"] = "A simple low-poly toy robot with a square head, two arms and two legs."
            if family in ("convert", "texture", "retopology", "mesh"):
                values["model_url"] = "https://example.com/model.glb"
            if model == "tripo-retopology-v1":
                values["face_limit"] = 10000
            if family == "texture":
                values["texture_prompt_text"] = "Glossy blue ceramic with clean surface detail."
            node = add(workflow, family, values)
            if model == "tripo-mesh-complete":
                before = add(workflow, "mesh", {"model": "tripo-mesh-segment-v1", "model_url": "https://example.com/model.glb"}, [450, 40])
                node["pos"] = [1100, 40]
                link_widget(workflow, before, 4, node, "tripo_segment_task_id")
            if family == "generate" and "text-to-3d" not in model:
                for index in range(1, 3 if "multiview" in model else 2):
                    image(workflow, node, index)
            if family == "splat" or model.endswith("smartsegment"):
                image(workflow, node, 1)
            if family != "splat":
                outputs(workflow, node, 1750 if model == "tripo-mesh-complete" else 1100, preview=family != "convert")
            save("zhenzhen-" + model + "-lowprice", workflow)

    for mode in ("image", "images"):
        name = "zhenzhen-tripo-texture-" + mode + "-lowprice"
        workflow = start(name)
        node = add(workflow, "texture", {"model_url": "https://example.com/model.glb", "texture_prompt_mode": mode})
        for index in range(1, 2 if mode == "image" else 5):
            image(workflow, node, index)
        outputs(workflow, node)
        save(name, workflow)
    name = "zhenzhen-tripo-smartsegment-model-lowprice"
    workflow = start(name)
    node = add(workflow, "mesh", {"model": "tripo-mesh-smartsegment", "seg_type": "model", "model_url": "https://example.com/model.glb"})
    outputs(workflow, node)
    save(name, workflow)
    name = "zhenzhen-tripo-generate-segment-complete-lowprice"
    workflow = start(name)
    first = add(workflow, "generate", {"model": "tripo-p-p1-text-to-3d", "face_limit": 1000, "texture": "false", "pbr": "false",
        "prompt": "A simple low-poly toy robot with a square head, two arms and two legs."}, [450, 40])
    second = add(workflow, "mesh", {"model": "tripo-mesh-segment-v1"}, [1100, 40])
    third = add(workflow, "mesh", {"model": "tripo-mesh-complete", "completion_mode": "quick_cap"}, [1750, 40])
    link_widget(workflow, first, 1, second, "model_url")
    link_widget(workflow, second, 4, third, "tripo_segment_task_id")
    outputs(workflow, third, 2400)
    save(name, workflow)
    print("Saved 29 blank-key Tripo workflows; existing examples unchanged.")


if __name__ == "__main__":
    main()
