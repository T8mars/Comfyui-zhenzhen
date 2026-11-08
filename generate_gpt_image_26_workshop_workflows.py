"""Create credential-free GPT Image 2.6 Workshop examples only."""

from generate_nov08_workflows import ROOT, native, generated, document, connect, save
from nov08_fixture import module

nodes = module("gpt_image_26_workshop_nodes")
KEY = "T8Zhenzhen_GPT_Image_2_6_Workshop"


def settings():
    node = native("T8Zhenzhen_API_Settings", 1, [30, 400])
    node["widgets_values"] = ["zhenzhen", "", "", False]
    node["title"] = "Zhenzhen API Settings (AI Workshop)"
    return node


def source(key, identifier, model, position=None, **values):
    size = "3840x2160" if model.endswith("-4k") else "2048x2048" if model.endswith("-2k") else "1024x1024"
    node = generated(key, identifier, {"model": model, "size": size, "prompt": "A blue ceramic teapot on a light gray studio table, soft light.", **values}, position)
    node["inputs"].append({"name": "api_key", "type": "STRING", "shape": 7, "widget": {"name": "api_key"}, "link": None})
    return node


def saver(identifier, prefix, position=None):
    return {"id": identifier, "type": "SaveImage", "pos": position or [1100, 40], "size": [300, 280], "flags": {}, "mode": 0,
        "order": identifier - 1, "inputs": [{"name": "images", "type": "IMAGE", "link": None}], "outputs": [],
        "properties": {"Node name for S&R": "SaveImage"}, "widgets_values": ["zhenzhen/" + prefix]}


def join_alpha(identifier, position=None):
    return {"id": identifier, "type": "JoinImageWithAlpha", "pos": position or [1080, 40], "size": [240, 90], "flags": {}, "mode": 0,
        "order": identifier - 1, "inputs": [{"name": "image", "type": "IMAGE", "link": None}, {"name": "alpha", "type": "MASK", "link": None}],
        "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": None}], "properties": {"Node name for S&R": "JoinImageWithAlpha"}, "widgets_values": []}


def main():
    for model in nodes.MODELS:
        for mode in ("text", "edit"):
            name = "zhenzhen-" + model + "-" + mode + "-workshop"
            workflow = document(name)
            config = settings()
            node = source(KEY, 2, model)
            workflow["nodes"] = [config, node]
            connect(workflow, config, 0, node, "api_key")
            if mode == "edit":
                config["pos"] = [30, 700]
                for index in (1, 2):
                    load = native("LoadImage", len(workflow["nodes"]) + 1, [30, 30 + (index - 1) * 300])
                    load["widgets_values"][0] = f"select_reference_{index}.png"
                    workflow["nodes"].append(load)
                    connect(workflow, load, 0, node, f"image{index}")
            sink = saver(len(workflow["nodes"]) + 1, name)
            workflow["nodes"].append(sink)
            connect(workflow, node, 0, sink, "images")
            save(name, workflow)

    for mode in ("mask", "markup", "transparent"):
        name = "zhenzhen-gpt-image-2.6-" + mode + "-workshop"
        workflow = document(name)
        config = settings()
        node = source(KEY, 2, nodes.MODELS[3] if mode == "transparent" else nodes.MODELS[0],
            background="transparent" if mode == "transparent" else "auto",
            prompt="Isolate the teapot on a transparent background." if mode == "transparent" else "Change only the marked part of the teapot to red ceramic.")
        workflow["nodes"] = [config, node]
        connect(workflow, config, 0, node, "api_key")
        if mode != "transparent":
            load = native("LoadImage", 3, [30, 40])
            workflow["nodes"].append(load)
            connect(workflow, load, 0, node, "image1")
            if mode == "mask":
                connect(workflow, load, 1, node, "mask")
            else:
                annotation = native("LoadImage", 4, [30, 720])
                annotation["widgets_values"][0] = "select_transparent_markup.png"
                annotation["title"] = "Markup PNG"
                alpha = join_alpha(5, [370, 820])
                workflow["nodes"].extend([annotation, alpha])
                connect(workflow, annotation, 0, alpha, "image")
                connect(workflow, annotation, 1, alpha, "alpha")
                connect(workflow, alpha, 0, node, "markup")
            sink = saver(len(workflow["nodes"]) + 1, name)
            workflow["nodes"].append(sink)
            connect(workflow, node, 0, sink, "images")
        else:
            alpha, sink = join_alpha(3), saver(4, name, [1380, 40])
            workflow["nodes"].extend([alpha, sink])
            connect(workflow, node, 0, alpha, "image")
            connect(workflow, node, 3, alpha, "alpha")
            connect(workflow, alpha, 0, sink, "images")
        save(name, workflow)

    name = "zhenzhen-gpt-image-2.6-concurrent-workshop"
    workflow = document(name)
    config = settings()
    collector = generated("ComflyConcurrent_Image_Await", 4, position=[1100, 40])
    workflow["nodes"] = [config, collector]
    for index, model in enumerate((nodes.MODELS[0], nodes.MODELS[3]), 1):
        node = source(f"ComflyConcurrent_{KEY}_Submit", index + 1, model, [450, 40 + (index - 1) * 800])
        sink = saver(index + 4, model, [1730, 40 + (index - 1) * 330])
        workflow["nodes"].extend([node, sink])
        connect(workflow, config, 0, node, "api_key")
        connect(workflow, node, 0, collector, f"task_{index}")
        connect(workflow, collector, index - 1, sink, "images")
    save(name, workflow)
    print("Saved 16 GPT Image 2.6 Workshop workflows with empty API keys.")


if __name__ == "__main__":
    main()
