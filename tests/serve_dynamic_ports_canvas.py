"""Isolated, credential-free canvas fixture. No generation requests are needed."""

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
COMFY = ROOT.parents[1]
sys.path.insert(0, str(COMFY))


def main():
    with tempfile.TemporaryDirectory(prefix="zhenzhen-dynamic-ports-") as folder:
        base = Path(folder)
        for name in ("input", "output", "user", "temporary"):
            (base / name).mkdir()
        from PIL import Image
        Image.new("RGB", (64, 64), "#397a8b").save(base / "input/reference.png")
        sys.argv = [str(COMFY / "main.py"), "--cpu", "--listen", "127.0.0.1", "--port", "8298",
            "--disable-all-custom-nodes", "--disable-partner-nodes", "--disable-auto-launch", "--disable-assets",
            "--input-directory", str(base / "input"), "--output-directory", str(base / "output"),
            "--user-directory", str(base / "user"), "--temp-directory", str(base / "temporary"), "--database-url", "sqlite:///:memory:"]
        import main as comfy_main
        import nodes as comfy_nodes
        import execution
        import uuid
        from server import PromptServer
        from aiohttp import web
        original = comfy_nodes.init_extra_nodes

        async def initialize(*args, **kwargs):
            await original(*args, **kwargs)
            from nov08_fixture import module
            plugin, parallel = module("Comfly"), module("ComflyConcurrent")
            comfy_nodes.NODE_CLASS_MAPPINGS.update(plugin.NODE_CLASS_MAPPINGS)
            comfy_nodes.NODE_CLASS_MAPPINGS.update(parallel.CONCURRENT_NODE_CLASS_MAPPINGS)
            comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS.update(plugin.NODE_DISPLAY_NAME_MAPPINGS)
            comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS.update(parallel.CONCURRENT_NODE_DISPLAY_NAME_MAPPINGS)
            comfy_nodes.EXTENSION_WEB_DIRS["zhenzhen-dynamic-ports"] = str(ROOT / "web")

            @PromptServer.instance.routes.post("/dynamic_ports_fixture/validate")
            async def validate(request):
                data = await request.json()
                result = await execution.validate_prompt(str(uuid.uuid4()), data["prompt"], None)
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
