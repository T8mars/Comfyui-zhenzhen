"""Blank-key Flash, H3 ComfyUI and voice-library examples; old files stay unchanged."""

from generate_nov08_workflows import native, generated, document, connect, save, module

h3 = module("h3_comfy_low_price_nodes")
tts = module("doubao_tts_low_price_nodes")
api = module("seedance_low_price_nodes")
FLASH_KEY = "Comfly_seedance25_standard_low_price"


def start(name, key, values):
    graph = document(name)
    settings = native("T8Zhenzhen_API_Settings", 1, [30, 1000])
    settings["widgets_values"] = ["seedance_low_price", "", "", False]
    node = generated(key, 2, values)
    graph["nodes"] = [settings, node]
    connect(graph, settings, 1, node, "api_config")
    return graph, node


def load(graph, node, family, index=1):
    identifier = len(graph["nodes"]) + 1
    if family == "audio":
        source = {"id": identifier, "type": "LoadAudio", "pos": [30, 400], "size": [300, 150],
                  "flags": {}, "mode": 0, "order": identifier - 1, "inputs": [],
                  "outputs": [{"name": "AUDIO", "type": "AUDIO", "links": None}],
                  "properties": {"Node name for S&R": "LoadAudio"}, "widgets_values": ["select_reference.wav", None, ""]}
    else:
        source = native("LoadImage" if family == "image" else "LoadVideo", identifier, [30, 40 + (index - 1) * 330])
        source["widgets_values"][0] = f"select_{family}_{index}." + ("png" if family == "image" else "mp4")
    graph["nodes"].append(source)
    connect(graph, source, 0, node, f"{family}{index}")


def finish(name, graph, node, concurrent=False, audio=False):
    if concurrent:
        collector = generated("ComflyConcurrent_Video_Await", len(graph["nodes"]) + 1, {})
        collector["pos"] = [1100, 40]
        graph["nodes"].append(collector)
        connect(graph, node, 0, collector, "task_1")
        node = collector
    if audio:
        sink = {"id": len(graph["nodes"]) + 1, "type": "SaveAudio", "pos": [1100, 40], "size": [300, 150],
                "flags": {}, "mode": 0, "order": len(graph["nodes"]), "inputs": [{"name": "audio", "type": "AUDIO", "link": None}],
                "outputs": [], "properties": {"Node name for S&R": "SaveAudio"}, "widgets_values": ["zhenzhen/" + name]}
    else:
        sink = native("SaveVideo", len(graph["nodes"]) + 1, [1600 if concurrent else 1100, 40])
        sink["widgets_values"] = ["zhenzhen/" + name, "auto", "auto"]
    graph["nodes"].append(sink)
    connect(graph, node, 0, sink, "audio" if audio else "video")
    save(name, graph)


def main():
    for model in api.SEEDANCE25_FLASH_MODELS:
        for mode in (["first", "first-last"] if model.endswith("-i2v") else ["mixed" if model.endswith("-multi") else "text"]):
            name = "zhenzhen-" + model + "-" + mode + "-lowprice"
            graph, node = start(name, FLASH_KEY, {"model": model, "prompt": "A blue puppet waves gently in a bright studio, locked camera.", "seconds": "4", "resolution": "480p", "ratio": "adaptive"})
            if mode != "text":
                load(graph, node, "image")
            if mode == "first-last":
                load(graph, node, "image", 2)
            if mode == "mixed":
                load(graph, node, "video")
                load(graph, node, "audio")
            finish(name, graph, node)
    for kind, modes in {"charswap": ["seconds", "frames"], "wuxi": ["text", "mixed", "url-video"], "wf": ["text", "mixed"], "selflift": ["text", "mixed"]}.items():
        for mode in modes:
            name = "zhenzhen-" + h3.contracts.PROFILES[kind]["model"] + "-" + mode + "-lowprice"
            values = {"prompt": "A blue puppet waves gently in a bright studio, locked camera.", "resolution": "480p", "seconds": "3" if kind in ("wf", "selflift") else "5"}
            if mode != "text":
                values["prompt"] = "<Picture 1> is the main character, preserve its identity, animate a gentle wave."
            if mode == "frames":
                values.update(duration_mode="frames", frames=124)
            if mode == "url-video":
                values["video_urls"] = "https://example.com/your-reference.mp4"
            graph, node = start(name, h3.KEYS[kind], values)
            if mode != "text":
                load(graph, node, "image")
            if kind == "charswap" or kind == "wuxi" and mode == "mixed":
                load(graph, node, "video")
            if mode == "mixed":
                load(graph, node, "audio")
            finish(name, graph, node)
        name = "zhenzhen-" + h3.contracts.PROFILES[kind]["model"] + "-concurrent-lowprice"
        values = {"prompt": "<Picture 1> waves gently in a bright studio.", "seconds": "5", "resolution": "480p"}
        graph, node = start(name, "ComflyConcurrent_" + h3.KEYS[kind] + "_Submit", values)
        load(graph, node, "image")
        if kind == "charswap":
            load(graph, node, "video")
        finish(name, graph, node, concurrent=True)
    name = "zhenzhen-seedance-2.5-flash-concurrent-lowprice"
    graph, node = start(name, "ComflyConcurrent_" + FLASH_KEY + "_Submit", {"model": "seedance-2.5-flash-t2v", "prompt": "A blue puppet waves gently in a bright studio."})
    finish(name, graph, node, concurrent=True)
    for mode, values in {
        "vivi": {"prompt": "你好，欢迎来到贞贞的平价小屋。", "context_texts": "请用温柔亲切的语气说。"},
        "english": {"prompt": "Every great journey begins with a single step.", "speaker": "en_male_tim_uranus_bigtts", "explicit_language": "en"},
        "dialect": {"prompt": "你好，今天我们一起聊聊天。", "advanced_mode": True, "explicit_dialect": "sichuan"},
        "custom-voice": {"prompt": "你好，这是我的复刻音色。", "speaker": "your_trained_speaker_id", "advanced_mode": True, "voice_model": "seed-tts-2.0-standard"},
    }.items():
        name = "zhenzhen-doubao-seed-tts-2.0-" + mode + "-lowprice"
        graph, node = start(name, tts.KEY, values)
        finish(name, graph, node, audio=True)
    print("Saved 26 blank-key workflows; no existing workflow was changed.")


if __name__ == "__main__":
    main()
