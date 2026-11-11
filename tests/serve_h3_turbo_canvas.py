"""Opt-in isolated ComfyUI acceptance using completed responses only."""

import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import uuid

ROOT=Path(__file__).resolve().parents[1]
COMFY=ROOT.parents[1]
sys.path.insert(0,str(COMFY))


def main():
    state=json.loads((Path(os.environ["H3_TURBO_REFERENCE"])/"private_resume.json").read_text())
    fresh=Path(os.environ["H3_TURBO_FRESH"])/"private_resume.json"
    if fresh.exists():
        data=json.loads(fresh.read_text())
        for target,source in (("minimax_edit","fresh_minimax_edit"),("qwen_edit","fresh_qwen_edit"),("video_mixed","fresh_video_mixed")):
            if data.get(source,{}).get("final"):
                state[target]=data[source]
    finals={entry["task"]:entry["final"] for entry in state.values() if entry.get("final")}
    counts,failures,lock={},set(),threading.Lock()
    with tempfile.TemporaryDirectory(prefix="zhenzhen-h3-turbo-canvas-") as folder:
        base=Path(folder)
        for name in ("input","output","user","temporary"):
            (base/name).mkdir()
        from PIL import Image
        import wave
        for index in (1,2):
            Image.new("RGB",(512,512),"#cc2222" if index==1 else "#2244bb").save(base/"input"/f"select_h3_turbo_{index}.png")
        with wave.open(str(base/"input/select_h3_turbo_audio.wav"),"wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(bytes(8000*2*3))
        sys.argv=[str(COMFY/"main.py"),"--cpu","--listen","127.0.0.1","--port","8298","--disable-all-custom-nodes",
            "--disable-partner-nodes","--disable-auto-launch","--disable-assets","--user-directory",str(base/"user"),
            "--input-directory",str(base/"input"),"--output-directory",str(base/"output"),"--temp-directory",str(base/"temporary"),"--database-url","sqlite:///:memory:"]
        import main as comfy_main
        import nodes as comfy_nodes
        import execution
        from server import PromptServer
        from aiohttp import web
        original=comfy_nodes.init_extra_nodes

        async def initialize(*args,**kwargs):
            await original(*args,**kwargs)
            from nov08_fixture import module
            plugin,parallel,nodes=module("Comfly"),module("ComflyConcurrent"),module("h3_turbo_low_price_nodes")
            comfy_nodes.NODE_CLASS_MAPPINGS.update(plugin.NODE_CLASS_MAPPINGS)
            comfy_nodes.NODE_CLASS_MAPPINGS.update(parallel.CONCURRENT_NODE_CLASS_MAPPINGS)
            comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS.update(plugin.NODE_DISPLAY_NAME_MAPPINGS)
            comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS.update(parallel.CONCURRENT_NODE_DISPLAY_NAME_MAPPINGS)
            comfy_nodes.EXTENSION_WEB_DIRS["zhenzhen-h3-turbo"]=str(ROOT/"web")

            @PromptServer.instance.routes.post("/h3_turbo_fixture/validate")
            async def validate(request):
                payload=await request.json()
                result=await execution.validate_prompt(str(uuid.uuid4()),payload["prompt"],None)
                return web.json_response({"valid":result[0],"error":result[1],"node_errors":result[3]})

            @PromptServer.instance.routes.post("/h3_turbo_fixture/reuse")
            async def reuse(request):
                def submit(body,config,video=False):
                    kind={"minimax-h3-image":"minimax","qwen-image-2.1-turbo":"qwen","minimax-h3-comfyui-max":"video"}.get(body.get("model"))
                    if kind is None:
                        raise RuntimeError("Fixture blocks all unrecorded creation requests")
                    edit=bool(body.get("images") or body.get("metadata",{}).get("audio_urls"))
                    case=kind+("_mixed" if kind=="video" and edit else "_edit" if edit else "_text")
                    if not state.get(case,{}).get("final"):
                        raise RuntimeError("Missing completed fixture response")
                    with lock:
                        counts[case]=counts.get(case,0)+1
                        if case in failures:
                            failures.remove(case)
                            raise RuntimeError("Injected local fixture failure")
                    return state[case]["task"]

                nodes.submit_task=submit
                nodes.poll_task=lambda task,*args,**kwargs:finals[task]
                nodes.api.upload_media=lambda *args,**kwargs:"https://example.test/fixture"
                return web.json_response({"ready":True,"recorded":len(finals)})

            @PromptServer.instance.routes.get("/h3_turbo_fixture/counts")
            async def count(request):
                return web.json_response(dict(counts))

            @PromptServer.instance.routes.post("/h3_turbo_fixture/fail-once")
            async def fail_once(request):
                payload=await request.json()
                with lock:
                    failures.add(payload["case"])
                return web.json_response({"armed":True})

        comfy_nodes.init_extra_nodes=initialize
        loop,server,start=comfy_main.start_comfyui()
        try:
            loop.run_until_complete(start())
        except KeyboardInterrupt:
            pass
        finally:
            server.asset_manager.shutdown()


if __name__=="__main__":
    main()
