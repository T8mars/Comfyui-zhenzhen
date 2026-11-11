"""Explicit opt-in, CPU-only canvas and local GLB acceptance server."""

import os
from pathlib import Path
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
COMFY = ROOT.parents[1]
sys.path.insert(0, str(COMFY))


def main():
    proof = Path(os.environ["ZHENZHEN_TRIPO_PROOF_DIR"]).resolve()
    if proof.is_relative_to(ROOT):
        raise RuntimeError("Live proof must stay outside the repository")
    with tempfile.TemporaryDirectory(prefix="zhenzhen-tripo-canvas-") as folder:
        base = Path(folder)
        for name in ("user", "input", "output", "temporary"):
            (base / name).mkdir()
        from PIL import Image
        for view in ("front", "left", "back", "right"):
            Image.new("RGB", (256, 256), "#347991").save(base / "input" / f"select_tripo_{view}.png")
        sys.argv = [str(COMFY / "main.py"), "--cpu", "--listen", "127.0.0.1", "--port", "8298",
            "--disable-all-custom-nodes", "--disable-partner-nodes", "--disable-auto-launch", "--disable-assets",
            "--user-directory", str(base / "user"), "--input-directory", str(base / "input"),
            "--output-directory", str(base / "output"), "--temp-directory", str(base / "temporary"), "--database-url", "sqlite:///:memory:"]
        import main as comfy_main
        import nodes as comfy_nodes
        from aiohttp import web
        import execution
        from server import PromptServer
        from comfy_api.latest import Types
        original = comfy_nodes.init_extra_nodes

        async def initialize(*args, **kwargs):
            await original(*args, **kwargs)
            from nov08_fixture import module
            plugin, parallel = module("Comfly"), module("ComflyConcurrent")
            comfy_nodes.NODE_CLASS_MAPPINGS.update(plugin.NODE_CLASS_MAPPINGS)
            comfy_nodes.NODE_CLASS_MAPPINGS.update(parallel.CONCURRENT_NODE_CLASS_MAPPINGS)
            comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS.update(plugin.NODE_DISPLAY_NAME_MAPPINGS)
            comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS.update(parallel.CONCURRENT_NODE_DISPLAY_NAME_MAPPINGS)
            comfy_nodes.EXTENSION_WEB_DIRS["zhenzhen-tripo"] = str(ROOT / "web")

            class LocalTripoGLB:
                CATEGORY = "Zhenzhen Test"
                FUNCTION = "execute"
                RETURN_TYPES = ("FILE_3D",)

                @classmethod
                def INPUT_TYPES(cls):
                    return {"required": {"model_file": (["generated.glb", "segmented.glb", "completed.glb"],)}}

                def execute(self, model_file):
                    source = (proof / model_file).resolve()
                    if source.parent != proof or source.name not in self.INPUT_TYPES()["required"]["model_file"][0] or not source.is_file():
                        raise ValueError("Only verified local GLB fixtures are allowed")
                    return (Types.File3D(str(source), file_format="glb"),)

            comfy_nodes.NODE_CLASS_MAPPINGS["T8ZhenzhenTripoLocalFixture"] = LocalTripoGLB

            @PromptServer.instance.routes.post("/zhenzhen_tripo_fixture/validate")
            async def validate_only(request):
                payload = await request.json()
                result = await execution.validate_prompt(str(uuid.uuid4()), payload["prompt"], None)
                return web.json_response({"valid": result[0], "error": result[1], "node_errors": result[3]})

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
