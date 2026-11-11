"""Credential-free workflows for the three independent H3/Turbo nodes."""

from generate_nov08_workflows import native, generated, document, connect, save, module
from generate_gpt_image_26_workshop_workflows import saver

nodes = module("h3_turbo_low_price_nodes")


def start(kind, mode):
    name = "zhenzhen-" + nodes.contracts.PROFILES[kind]["model"] + "-" + mode + "-lowprice"
    graph = document(name)
    config = native("T8Zhenzhen_API_Settings", 1, [30, 750])
    config["widgets_values"] = ["seedance_low_price", "", "", False]
    values = {"prompt": "A blue ceramic teapot on a white studio table, soft light, clean product photograph, no text."}
    if kind == "video":
        values.update(prompt="A blue ceramic teapot rotates gently on a white studio table, locked camera, soft light.", seconds="3")
    else:
        values["resolution"] = "720p" if kind == "qwen" and mode == "edit" else "1k"
        if mode == "edit":
            values["prompt"] = "Place the cup from image 1 beside the teapot from image 2, preserve both shapes and colors."
    node = generated(nodes.KEYS[kind], 2, values)
    graph["nodes"] = [config, node]
    connect(graph, config, 1, node, "api_config")
    return name, graph, node


def image(graph, node, index):
    source = native("LoadImage", len(graph["nodes"]) + 1, [30, 40 + (index - 1)*330])
    source["widgets_values"][0] = f"select_h3_turbo_{index}.png"
    graph["nodes"].append(source)
    connect(graph, source, 0, node, f"image{index}")


def main():
    for kind in ("minimax_image", "qwen"):
        for mode in ("text", "edit"):
            name, graph, node = start(kind, mode)
            if mode == "edit":
                image(graph, node, 1)
                image(graph, node, 2)
            sink = saver(len(graph["nodes"])+1, name)
            graph["nodes"].append(sink)
            connect(graph, node, 0, sink, "images")
            save(name, graph)
    for mode in ("text", "image", "audio", "mixed"):
        name, graph, node = start("video", mode)
        if mode in ("image", "mixed"):
            image(graph, node, 1)
        if mode in ("audio", "mixed"):
            audio = {"id": len(graph["nodes"])+1, "type": "LoadAudio", "pos": [30, 400 if mode == "mixed" else 40],
                     "size": [300, 150], "flags": {}, "mode": 0, "order": len(graph["nodes"]), "inputs": [],
                     "outputs": [{"name": "AUDIO", "type": "AUDIO", "links": None}],
                     "properties": {"Node name for S&R": "LoadAudio"}, "widgets_values": ["select_h3_turbo_audio.wav", None, ""]}
            graph["nodes"].append(audio)
            connect(graph, audio, 0, node, "audio1")
        sink = native("SaveVideo", len(graph["nodes"])+1, [1100,40])
        sink["widgets_values"] = ["zhenzhen/"+name, "auto", "auto"]
        graph["nodes"].append(sink)
        connect(graph, node, 0, sink, "video")
        save(name, graph)
    print("Saved eight blank-key H3/Turbo workflows; existing examples unchanged.")


if __name__ == "__main__":
    main()
