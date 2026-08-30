import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch


PRIMARY_KEY = "T8Zhenzhen_API_Settings"
INTERMEDIATE_KEY = "Zhenzhen_api_set"
LEGACY_KEY = "Comfly_api_set"
ZHENZHEN_CHOICES = ["zhenzhen", "seedance_low_price", "ip"]
COMFLY_CHOICES = ["comfly", "ip", "hk", "us"]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--comfyui", required=True, type=Path)
    parser.add_argument("--zhenzhen", required=True, type=Path)
    parser.add_argument("--comfly", required=True, type=Path)
    parser.add_argument(
        "--order",
        required=True,
        choices=("zhenzhen-first", "comfly-first"),
    )
    return parser.parse_args()


def choices(node_class):
    return list(node_class.INPUT_TYPES()["required"]["api_base"][0])


async def run(args):
    sys.path.insert(0, str(args.comfyui.resolve()))
    import nodes

    sequence = (
        (args.zhenzhen, args.comfly)
        if args.order == "zhenzhen-first"
        else (args.comfly, args.zhenzhen)
    )
    with patch.object(
        subprocess,
        "run",
        return_value=subprocess.CompletedProcess([], 0),
    ):
        for plugin_path in sequence:
            loaded = await nodes.load_custom_node(
                str(plugin_path.resolve()),
                module_parent="custom_nodes",
            )
            if not loaded:
                raise RuntimeError(f"Failed to load {plugin_path}")

    for key in (PRIMARY_KEY, INTERMEDIATE_KEY, LEGACY_KEY):
        if key not in nodes.NODE_CLASS_MAPPINGS:
            raise AssertionError(f"Missing settings registration: {key}")

    primary_class = nodes.NODE_CLASS_MAPPINGS[PRIMARY_KEY]
    intermediate_class = nodes.NODE_CLASS_MAPPINGS[INTERMEDIATE_KEY]
    external_class = nodes.NODE_CLASS_MAPPINGS[LEGACY_KEY]

    if choices(primary_class) != ZHENZHEN_CHOICES:
        raise AssertionError("Canonical Zhenzhen settings node was replaced")
    if choices(intermediate_class) != ZHENZHEN_CHOICES:
        raise AssertionError("Intermediate Zhenzhen compatibility alias was replaced")
    if choices(external_class) != COMFLY_CHOICES:
        raise AssertionError(
            "Comfyui_Comfly did not retain its own legacy registration: "
            f"{choices(external_class)}"
        )

    expected_outputs = ("STRING", "ZHENZHEN_SEEDANCE2_CONFIG")
    if primary_class.RETURN_TYPES != expected_outputs:
        raise AssertionError("Canonical settings output contract changed")
    if intermediate_class.RETURN_TYPES != expected_outputs:
        raise AssertionError("Intermediate settings output contract changed")
    if external_class.RETURN_TYPES != ("STRING",):
        raise AssertionError("External Comfyui_Comfly output contract changed")

    for node_class in (primary_class, intermediate_class):
        result = node_class().set_api_base("seedance_low_price", apikey="")
        if result[0] != "" or result[1]["base_url"] != "https://api.seedance.nz":
            raise AssertionError("Zhenzhen settings execution contract is invalid")

    print(
        json.dumps(
            {
                "order": args.order,
                "primary_class": primary_class.__module__,
                "intermediate_class": intermediate_class.__module__,
                "legacy_owner": external_class.__module__,
                "legacy_choices": choices(external_class),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
