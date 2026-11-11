"""Blank-key examples for Seedream 5.5 and Seedance 2.5 draft enhancement."""

from generate_nov08_workflows import native, generated, document, connect, save, module
from generate_gpt_image_26_workshop_workflows import saver, join_alpha

nodes = module("seedream55_low_price_nodes")
IMAGE = "T8Zhenzhen_Seedream_55_Image_LowPrice"
LAYER = "T8Zhenzhen_Seedream_55_Layers_LowPrice"
DRAFT = "T8Zhenzhen_Seedance_25_Draft_To_Video_LowPrice"


def start(name, key, values):
    graph = document(name)
    config = native("T8Zhenzhen_API_Settings", 1, [30, 440])
    config["widgets_values"] = ["seedance_low_price", "", "", False]
    node = generated(key, 2, values)
    graph["nodes"] = [config, node]
    connect(graph, config, 1, node, "api_config")
    return graph, node


def load(graph, node, field):
    source = native("LoadImage", len(graph["nodes"])+1, [30, 40])
    source["widgets_values"][0] = "select_seedream55_source.png"
    graph["nodes"].append(source)
    connect(graph, source, 0, node, field)


def save_image(graph, node, name, mask=None):
    source = node
    if mask is not None:
        source = join_alpha(len(graph["nodes"])+1, [1100, 40])
        graph["nodes"].append(source)
        connect(graph, node, 0, source, "image")
        connect(graph, node, mask, source, "alpha")
    sink = saver(len(graph["nodes"])+1, name, [1430 if mask is not None else 1100, 40])
    graph["nodes"].append(sink)
    connect(graph, source, 0, sink, "images")


def save_video(graph, node, name, position=None):
    sink = native("SaveVideo", len(graph["nodes"])+1, position or [1100, 40])
    sink["widgets_values"] = ["zhenzhen/"+name, "auto", "auto"]
    graph["nodes"].append(sink)
    connect(graph, node, 0, sink, "video")


def main():
    for model in nodes.seedream55.IMAGE_MODELS:
        name = "zhenzhen-"+model+"-lowprice"
        edit = model.endswith("-i2i")
        graph, node = start(name, IMAGE, {"model": model, "prompt": "Keep the subject and composition; change the background to a bright studio." if edit else "A red ceramic cup beside a green leaf, clean studio product photograph, no text."})
        if edit:
            load(graph, node, "image1")
        save_image(graph, node, name)
        save(name, graph)
    for model in nodes.seedream55.LAYER_MODELS:
        name = "zhenzhen-"+model+"-lowprice"
        graph, node = start(name, LAYER, {"model": model})
        load(graph, node, "image")
        save_image(graph, node, name, mask=1)
        save(name, graph)
    name = "zhenzhen-seedream55-transparent-lowprice"
    graph, node = start(name, IMAGE, {"background": "transparent", "prompt": "A single green leaf with fine veins, isolated on transparent background."})
    save_image(graph, node, name, mask=4)
    save(name, graph)
    for index, model in enumerate(nodes.DRAFT_MODELS):
        name = "zhenzhen-"+model+"-lowprice"
        graph, node = start(name, DRAFT, {"model": model})
        save_video(graph, node, name)
        save(name, graph)
        name = "zhenzhen-"+model+"-chain-lowprice"
        source_model = "seedance-2.5-"+("global-" if index else "")+"standard-t2v"
        graph, draft = start(name, "Comfly_seedance25_standard_low_price", {"model": source_model, "prompt": "A small blue ball rolls slowly across a white tabletop, locked camera.", "seconds": "4", "resolution": "480p", "draft": True})
        draft["widgets_values"].insert(8, "fixed")
        node = generated(DRAFT, 3, {"model": model}, [1100, 40])
        node["inputs"].append({"name": "draft_task_id", "type": "STRING", "widget": {"name": "draft_task_id"}, "link": None})
        graph["nodes"].append(node)
        connect(graph, graph["nodes"][0], 1, node, "api_config")
        connect(graph, draft, 2, node, "draft_task_id")
        save_video(graph, draft, name+"_draft", [450, 1120])
        save_video(graph, node, name+"_enhanced", [1750, 40])
        save(name, graph)
    print("Saved 11 blank-key Seedream 5.5 / Seedance draft workflows; old examples unchanged.")


if __name__ == "__main__":
    main()
