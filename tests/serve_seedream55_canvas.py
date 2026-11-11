"""Opt-in isolated ComfyUI server; completed-response replay only, no task creation."""

import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
COMFY = ROOT.parents[1]
sys.path.insert(0, str(COMFY))


def main():
    reference = Path(os.environ["ZHENZHEN_55_REFERENCE_DIR"]).resolve()
    state = json.loads((reference / "private_resume.json").read_text())
    diagnostics = json.loads((reference / "private_draft_diagnostics.json").read_text())
    state["domestic_draft"] = diagnostics["fresh-source"]
    state["domestic_enhance"] = diagnostics["fresh-node-default"]
    by_task = {value["task"]: value["final"] for value in state.values() if value.get("final")}
    cases = {}
    for region, image, video in (("domestic", "seedream-v5.5", "seedance-2.5-standard"), ("global", "dola-seedream-5.5", "seedance-2.5-global-standard")):
        cases.update({image+"-t2i":region+"_t2i",image+"-i2i":region+"_i2i",image+"-layer-decomposition":region+"_layers",
            video+"-t2v":region+"_draft",video+"-draft-to-video":region+"_enhance"})
    counts, failures, lock = {}, set(), threading.Lock()
    with tempfile.TemporaryDirectory(prefix="zhenzhen-seedream55-canvas-") as folder:
        base = Path(folder)
        for name in ("user", "input", "output", "temporary"):
            (base / name).mkdir()
        from PIL import Image
        Image.new("RGBA", (1024,1024), (30,150,70,120)).save(base/"input/select_seedream55_source.png")
        # Older examples also pass queue validation without requiring the user's files.
        for file in (ROOT/"workflow").glob("*seedance-2.5-*.json"):
            for node in json.loads(file.read_text(encoding="utf-8"))["nodes"]:
                if node["type"] == "LoadImage":
                    name = str(node["widgets_values"][0])
                    if Path(name).name == name:
                        Image.new("RGB", (640,360), "#347991").save(base/"input"/name)
        import cv2
        import numpy as np
        import wave
        video = cv2.VideoWriter(str(base/"input"/"选择参考视频.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 24, (640,360))
        for index in range(48):
            frame = np.zeros((360,640,3),dtype=np.uint8)
            frame[:,index*6:index*6+100,1] = 180
            video.write(frame)
        video.release()
        with wave.open(str(base/"input"/"选择参考音频.wav"),"wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(44100)
            audio.writeframes(bytes(44100*2*2))
        sys.argv = [str(COMFY/"main.py"),"--cpu","--listen","127.0.0.1","--port","8298","--disable-all-custom-nodes",
            "--disable-partner-nodes","--disable-auto-launch","--disable-assets","--user-directory",str(base/"user"),
            "--input-directory",str(base/"input"),"--output-directory",str(base/"output"),"--temp-directory",str(base/"temporary"),"--database-url","sqlite:///:memory:"]
        import main as comfy_main
        import nodes as comfy_nodes
        import execution
        from server import PromptServer
        from aiohttp import web
        original = comfy_nodes.init_extra_nodes

        async def initialize(*args, **kwargs):
            await original(*args, **kwargs)
            from nov08_fixture import module
            plugin, parallel, nodes = module("Comfly"), module("ComflyConcurrent"), module("seedream55_low_price_nodes")
            comfy_nodes.NODE_CLASS_MAPPINGS.update(plugin.NODE_CLASS_MAPPINGS)
            comfy_nodes.NODE_CLASS_MAPPINGS.update(parallel.CONCURRENT_NODE_CLASS_MAPPINGS)
            comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS.update(plugin.NODE_DISPLAY_NAME_MAPPINGS)
            comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS.update(parallel.CONCURRENT_NODE_DISPLAY_NAME_MAPPINGS)
            comfy_nodes.EXTENSION_WEB_DIRS["zhenzhen-seedream55"] = str(ROOT/"web")

            @PromptServer.instance.routes.post("/seedance55_fixture/validate")
            async def validate_only(request):
                payload = await request.json()
                result = await execution.validate_prompt(str(uuid.uuid4()), payload["prompt"], None)
                return web.json_response({"valid":result[0],"error":result[1],"node_errors":result[3]})

            @PromptServer.instance.routes.post("/seedance55_fixture/reuse")
            async def reuse(request):
                def submit(payload, config, **kwargs):
                    case = cases.get(payload.get("model"))
                    if case not in state or not state[case].get("final"):
                        raise RuntimeError("Fixture blocks every unrecorded generation request")
                    metadata = payload.get("metadata",{})
                    if case.endswith("_draft") and metadata.get("draft") is not True:
                        raise RuntimeError("Fixture source must explicitly request draft mode")
                    if case.endswith("_enhance") and metadata.get("draft_task_id") != state[case.replace("_enhance","_draft")]["task"]:
                        raise RuntimeError("Enhancement source must match its own region's completed draft")
                    with lock:
                        counts[case] = counts.get(case,0)+1
                        if case in failures:
                            failures.remove(case)
                            raise RuntimeError("Injected local acceptance failure")
                    return state[case]["task"]

                def poll(task, config, **kwargs):
                    if task not in by_task:
                        raise RuntimeError("Fixture blocks every unrecorded poll")
                    return by_task[task]

                nodes.submit_task, nodes.poll_task = submit, poll
                nodes.api.submit_task = lambda *args, **kwargs:(submit(*args,**kwargs),{})
                nodes.api.poll_task = poll
                nodes.api.upload_media = lambda *args, **kwargs:"https://example.test/fixture.png"
                return web.json_response({"ready":True})

            @PromptServer.instance.routes.get("/seedance55_fixture/counts")
            async def count(request):
                return web.json_response(dict(counts))

            @PromptServer.instance.routes.post("/seedance55_fixture/fail-once")
            async def fail_once(request):
                payload = await request.json()
                with lock:
                    failures.add(payload["case"])
                return web.json_response({"armed":True})

        comfy_nodes.init_extra_nodes = initialize
        loop, server, start = comfy_main.start_comfyui()
        try:
            loop.run_until_complete(start())
        except KeyboardInterrupt:
            pass
        finally:
            server.asset_manager.shutdown()


if __name__ == "__main__":
    main()
