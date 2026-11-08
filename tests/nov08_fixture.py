"""Load this plugin without executing optional application startup helpers."""

import importlib
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
PACKAGE = "zhenzhen_nov08_probe"
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE] = package


def module(name):
    return importlib.import_module(f"{PACKAGE}.{name}")


api = module("seedance_low_price_nodes")
image = module("image_models_26_contracts")
nodes = module("nov05_low_price_nodes")
kling = module("kling_v4_low_price_nodes")
flash = module("flash_video_low_price_nodes")
