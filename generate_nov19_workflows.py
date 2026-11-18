"""Blank-key November 19 examples; existing workflows are not rewritten."""

from generate_nov08_workflows import native, generated, document, connect, save, module
from generate_nov17_workflows import load

nodes = module("nov19_low_price_nodes")


def start(name, key, values):
    graph = document(name)
    settings = native("T8Zhenzhen_API_Settings", 1, [30, 550])
    settings["widgets_values"] = ["seedance_low_price", "", "", False]
    node = generated(key, 2, values)
    graph["nodes"] = [settings, node]
    connect(graph, settings, 1, node, "api_config")
    return graph, node


def finish(name, graph, source, media, concurrent=False):
    if concurrent:
        collector = generated("ComflyConcurrent_Image_Await", len(graph["nodes"]) + 1)
        collector["pos"] = [1100, 40]
        graph["nodes"].append(collector)
        connect(graph, source, 0, collector, "task_1")
        source = collector
    field = {"IMAGE": "images", "AUDIO": "audio", "STRING": "source"}[media]
    key = {"IMAGE": "SaveImage", "AUDIO": "SaveAudio", "STRING": "PreviewAny"}[media]
    identifier = len(graph["nodes"]) + 1
    sink = {"id": identifier, "type": key, "pos": [1600 if concurrent else 1100, 40], "size": [350, 250],
            "flags": {}, "mode": 0, "order": identifier - 1,
            "inputs": [{"name": field, "type": "*" if media == "STRING" else media, "link": None}],
            "outputs": [] if media != "STRING" else [{"name": "STRING", "type": "STRING", "links": None}],
            "properties": {"Node name for S&R": key}, "widgets_values": [] if media == "STRING" else ["zhenzhen/" + name]}
    graph["nodes"].append(sink)
    connect(graph, source, 0, sink, field)
    save(name, graph)


def main():
    for mode in ("text", "reference", "group"):
        name = "zhenzhen-kling-v4-image-" + mode + "-lowprice"
        values = {"prompt": "An original blue ceramic teapot on a pale studio backdrop.", "size": "1:1"}
        if mode == "reference":
            values["prompt"] = "Preserve the teapot in @Image1 and change its background to pale yellow."
        if mode == "group":
            values.update(prompt="Two related product photos of the same original blue ceramic teapot, front view and side view.", sequential_image_generation="auto", max_images=2)
        graph, node = start(name, nodes.KEYS["kling"], values)
        if mode == "reference":
            load(graph, node, "image")
        finish(name, graph, node, "IMAGE")
    for model in nodes.images.MAI_MODELS:
        for mode in ("text", "edit", "concurrent"):
            name = "zhenzhen-" + model + "-" + mode + "-lowprice"
            key = nodes.KEYS["mai"]
            if mode == "concurrent":
                key = "ComflyConcurrent_" + key + "_Submit"
            values = {"model": model, "prompt": "An original blue ceramic teapot on a white table.", "background": "opaque"}
            if mode == "edit":
                values["prompt"] = "Preserve the composition and change the teapot to emerald green."
            graph, node = start(name, key, values)
            if mode == "edit":
                load(graph, node, "image")
            finish(name, graph, node, "IMAGE", concurrent=mode == "concurrent")
    for model, mode, values in (
        (nodes.speech.FLASH, "text", {"prompt": "你好，欢迎收听今天的节目。", "language_hint": "zh"}),
        (nodes.speech.PLUS, "text", {"prompt": "Thanks for listening. I hope you enjoy the show.", "language_hint": "en"}),
        (nodes.speech.NEXT, "text", {"prompt": "A short morning radio greeting with upbeat, friendly delivery."}),
        (nodes.speech.NEXT, "reference", {"prompt": "A short electronic chime in the style of @voice1, without speech."}),
    ):
        name = "zhenzhen-" + model + "-" + mode + "-lowprice"
        graph, node = start(name, nodes.KEYS["audio"], {"model": model, **values})
        if mode == "reference":
            load(graph, node, "audio")
        finish(name, graph, node, "AUDIO")
    for variant, vision in (("astra", False), ("sol", True)):
        name = "zhenzhen-g6.2-" + variant + ("-vision-stream" if vision else "-text") + "-lowprice"
        values = {"model_preset": "zhenzhen/g6.2-" + variant, "stream": vision,
                  "prompt": "Describe the image briefly." if vision else "Write one sentence about a quiet studio.", "max_tokens": 512}
        graph, node = start(name, "Comfly_LLm_API", values)
        if vision:
            source = native("LoadImage", 3, [30, 40])
            source["widgets_values"][0] = "select_llm_reference.png"
            graph["nodes"].append(source)
            connect(graph, source, 0, node, "ref_image")
        finish(name, graph, node, "STRING")
    print("Saved 15 blank-key November 19 workflows; old examples unchanged.")


if __name__ == "__main__":
    main()
