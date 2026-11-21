"""Generate the November 21 examples without rewriting earlier workflows."""

from generate_nov08_workflows import native, connect, save, module
from generate_nov19_workflows import start, finish as finish_media
from generate_nov17_workflows import load, finish as finish_video
from generate_tripo_workflows import outputs as finish_3d

nodes = module("nov21_low_price_nodes")
llm = module("llm_low_price_presets")


def add_inputs(graph, target, inputs):
    for index, (family, field) in enumerate(inputs):
        if field == family + "1":
            load(graph, target, family)
        else:
            add_input(graph, target, family, field)
        graph["nodes"][-1]["pos"] = [30, 30 + index * 340]
    graph["nodes"][0]["pos"] = [30, 30 + len(inputs) * 340]


def add_input(graph, target, family, field):
    identifier = len(graph["nodes"]) + 1
    if family == "audio":
        source = {"id": identifier, "type": "LoadAudio", "size": [300, 150], "pos": [30, 30],
                  "flags": {}, "mode": 0, "order": identifier - 1, "inputs": [],
                  "outputs": [{"name": "AUDIO", "type": "AUDIO", "links": None}],
                  "properties": {"Node name for S&R": "LoadAudio"}, "widgets_values": ["select_speech.wav", None, ""]}
    else:
        source = native("LoadImage", identifier, [30, 30])
        source["widgets_values"][0] = f"select_{field}.png"
    graph["nodes"].append(source)
    connect(graph, source, 0, target, field)


def make(label, kind, values, media, inputs=(), concurrent=False):
    name = label + "-lowprice"
    key = "Comfly_LLm_API" if kind == "llm" else nodes.KEYS[kind]
    if concurrent:
        key = "ComflyConcurrent_" + key + "_Submit"
    graph, node = start(name, key, values)
    add_inputs(graph, node, inputs)
    if media == "VIDEO":
        finish_video(name, graph, node, concurrent=concurrent)
    elif media == "3D":
        finish_3d(graph, node)
        graph["nodes"][-1]["widgets_values"] = ["3d/miora"]
        save(name, graph)
    else:
        finish_media(name, graph, node, media, concurrent=concurrent)


def main():
    make("kling-v4-long-image-ecommerce", "long", {"prompt": "A short product page for the ceramic teapot in @Image1.", "length": "short"},
         "IMAGE", [("image", "image1")])
    make("kling-v4-long-image-webpage", "long", {"prompt": "A pottery studio landing page styled like @Image1, with @Image2 as the featured product.", "skill": "webpage"},
         "IMAGE", [("image", "style_image"), ("image", "subject_image")])
    make("kling-v4-long-image-webpage-concurrent", "long", {"prompt": "A compact landing page for a pottery studio.", "skill": "webpage"},
         "IMAGE", concurrent=True)

    for model in nodes.spec.GEMINI_TTS:
        make(model.replace("zhenzhen/", "zhenzhen-"), "tts",
             {"model": model, "prompt": "Hello. Thanks for listening.", "instructions": "Read warmly."}, "AUDIO")

    for index, model in enumerate(llm.MODELS[2:]):
        vision = index >= 2
        make(model.replace("zhenzhen/", "zhenzhen-"), "llm",
             {"model_preset": model, "prompt": "Describe the attached image briefly." if vision else "Write one short greeting.",
              "stream": index == 2, "max_tokens": 512}, "STRING", [("image", "ref_image")] if vision else [])

    for kind, (model, _, _, _, _) in nodes.h3.PROFILES.items():
        inputs = [("image", "image1")]
        values = {"prompt": "<Picture 1> gestures gently in a bright studio."}
        if kind in ("jy", "charswap"):
            inputs.append(("video", "video1"))
            if kind == "charswap":
                values["prompt"] = "Replace the source character with <Picture 1>, keeping the motion and camera."
        if kind in ("wf", "digital"):
            inputs.append(("audio", "audio1"))
            values["prompt"] = "<Picture 1> speaks calmly, following <Audio 1>."
        make(model, kind, values, "VIDEO", inputs)
        make(model + "-concurrent", kind, values, "VIDEO", inputs, concurrent=True)
        if kind == "charswap":
            make(model + "-frames", kind, {**values, "duration_mode": "frames", "frames": 124}, "VIDEO", inputs)

    for model in nodes.spec.HEYGEN:
        make(model + "-text", "heygen", {"model": model, "prompt": "Hello. Welcome to our studio."}, "VIDEO")
        make(model + "-audio", "heygen", {"model": model}, "VIDEO", [("audio", "audio")])
    make("heygen-avatar-6-turbo-concurrent", "heygen", {"prompt": "Hello. Welcome to our studio."}, "VIDEO", concurrent=True)
    make("miora-3d-text", "miora", {"prompt": "A simple round clay teapot with a handle and lid."}, "3D")
    make("miora-3d-single-view", "miora", {"generate_type": "geometry"}, "3D", [("image", "image1")])
    make("miora-3d-multi-view", "miora", {}, "3D", [("image", "image1"), ("image", "image2")])


if __name__ == "__main__":
    main()
