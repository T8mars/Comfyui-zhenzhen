"""Owned CPU-only ComfyUI canvas server, with only this plugin enabled."""

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
COMFY = ROOT.parents[1]
sys.path.insert(0, str(COMFY))


def main():
    with tempfile.TemporaryDirectory(prefix="zhenzhen-nov08-canvas-") as folder:
        base = Path(folder)
        for name in ("user", "input", "output", "temporary"):
            (base / name).mkdir()
        sys.argv = [str(COMFY / "main.py"), "--cpu", "--listen", "127.0.0.1", "--port", "8298",
            "--disable-all-custom-nodes", "--disable-partner-nodes", "--disable-auto-launch", "--disable-assets",
            "--user-directory", str(base / "user"), "--input-directory", str(base / "input"),
            "--output-directory", str(base / "output"), "--temp-directory", str(base / "temporary"),
            "--database-url", "sqlite:///:memory:"]
        import main as comfy_main
        import nodes as comfy_nodes
        original = comfy_nodes.init_extra_nodes

        async def initialize(*args, **kwargs):
            await original(*args, **kwargs)
            from nov08_fixture import module
            plugin, parallel = module("Comfly"), module("ComflyConcurrent")
            comfy_nodes.NODE_CLASS_MAPPINGS.update(plugin.NODE_CLASS_MAPPINGS)
            comfy_nodes.NODE_CLASS_MAPPINGS.update(parallel.CONCURRENT_NODE_CLASS_MAPPINGS)
            comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS.update(plugin.NODE_DISPLAY_NAME_MAPPINGS)
            comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS.update(parallel.CONCURRENT_NODE_DISPLAY_NAME_MAPPINGS)
            comfy_nodes.EXTENSION_WEB_DIRS["zhenzhen-nov08"] = str(ROOT / "web")

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
