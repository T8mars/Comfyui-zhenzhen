"""Opt-in paid live verification for all domestic Midjourney actions."""

import os
import sys
import tempfile
from pathlib import Path

import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import midjourney_low_price_nodes as nodes


def input_defaults():
    values = {
        name: spec[1].get("default")
        for name, spec in nodes.Comfly_midjourney_lowprice.INPUT_TYPES()[
            "required"
        ].items()
    }
    values.pop("operation")
    values.pop("prompt")
    return values


def synthetic_image(red, green, blue):
    image = torch.zeros((1, 512, 512, 3), dtype=torch.float32)
    image[..., 0] = red
    image[..., 1] = green
    image[..., 2] = blue
    ramp = torch.linspace(0.0, 0.25, 512).view(1, 1, 512)
    image[..., 0] = torch.clamp(image[..., 0] + ramp, 0.0, 1.0)
    return image


def main():
    if os.environ.get("RUN_MIDJOURNEY_LIVE") != "1":
        raise SystemExit("Set RUN_MIDJOURNEY_LIVE=1 to run paid tests")
    api_key = os.environ.get("SEEDANCE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("SEEDANCE_API_KEY is required")

    node = nodes.Comfly_midjourney_lowprice()
    config = {
        "base_url": "https://api.seedance.nz",
        "api_key": api_key,
    }
    defaults = input_defaults()
    first_image = synthetic_image(0.72, 0.14, 0.10)
    second_image = synthetic_image(0.08, 0.28, 0.72)
    completed = []

    def run(operation, prompt="", **overrides):
        values = dict(defaults)
        values.update(overrides)
        result = node.execute(
            operation=operation,
            prompt=prompt,
            api_config=config,
            skip_error=False,
            **values,
        )["result"]
        family = nodes.MIDJOURNEY_ACTION_SPECS[operation]["result_family"]
        if family == "image" and not any(
            item is not None for item in result[:5]
        ):
            raise RuntimeError(f"{operation} returned no IMAGE output")
        if family == "video" and result[5] is None:
            raise RuntimeError(f"{operation} returned no VIDEO output")
        if family == "text" and not result[9]:
            raise RuntimeError(f"{operation} returned no text")
        completed.append(operation)
        print(f"LIVE_OK {operation} family={family}", flush=True)
        return result

    with tempfile.TemporaryDirectory(prefix="zhenzhen_midjourney_live_") as output:
        os.environ["SEEDANCE_OUTPUT_DIR"] = output
        os.environ["SEEDANCE_POLL_INTERVAL"] = "3"
        os.environ["SEEDANCE_MAX_POLL_TIME"] = "1800"

        imagine = run(
            "midjourney-imagine",
            "a small red paper boat on a quiet lake, simple studio lighting",
            version="8.1",
            speed="relax",
            size="1:1",
        )
        imagine_task = imagine[14]

        run(
            "midjourney-blend",
            image1=first_image,
            image2=second_image,
            dimensions="SQUARE",
            speed="relax",
        )
        run(
            "midjourney-describe",
            image1=first_image,
            speed="relax",
        )
        run(
            "midjourney-edits",
            "turn the red paper boat blue while keeping a simple background",
            image1=first_image,
            version="8.1",
            speed="relax",
            size="1:1",
        )

        upscale = run(
            "midjourney-upscale",
            task_id=imagine_task,
            index=1,
            speed="relax",
        )
        upscale_task = upscale[14]
        run(
            "midjourney-variation",
            task_id=imagine_task,
            index=1,
            speed="relax",
        )
        run(
            "midjourney-high-variation",
            task_id=upscale_task,
            index=1,
            speed="relax",
        )
        run(
            "midjourney-low-variation",
            task_id=upscale_task,
            index=1,
            speed="relax",
        )
        run(
            "midjourney-reroll",
            task_id=imagine_task,
            index=-1,
            speed="relax",
        )
        run(
            "midjourney-zoom",
            task_id=upscale_task,
            index=-1,
            zoom_ratio=1.5,
            speed="relax",
        )
        run(
            "midjourney-pan",
            task_id=upscale_task,
            index=-1,
            direction="right",
            speed="relax",
        )
        inpaint = run(
            "midjourney-inpaint",
            task_id=upscale_task,
            index=-1,
            speed="relax",
        )
        modal_task = inpaint[14]
        mask = torch.zeros((1, 512, 512), dtype=torch.float32)
        mask[:, 160:352, 160:352] = 1.0
        run(
            "midjourney-modal",
            "replace the selected area with a small blue paper sail",
            task_id=modal_task,
            index=-1,
            modal_mode="region",
            mask=mask,
            speed="relax",
        )
        run(
            "midjourney-video",
            "the paper boat gently rocks as the camera slowly moves forward",
            image1=first_image,
            task_id="",
            index=-1,
            video_type="vid_1.1_i2v_480",
            batch_size=1,
        )
        run(
            "midjourney-remix-strong",
            "a blue origami sailboat on a quiet lake",
            task_id=imagine_task,
            index=1,
            speed="relax",
        )
        run(
            "midjourney-remix-subtle",
            "a red paper boat at golden hour",
            task_id=imagine_task,
            index=1,
            speed="relax",
        )

    expected = set(nodes.MIDJOURNEY_OPERATIONS)
    if set(completed) != expected or len(completed) != 16:
        missing = sorted(expected - set(completed))
        raise RuntimeError(f"Live operation coverage incomplete: {missing}")
    print("LIVE_SUMMARY operations=16 status=passed", flush=True)


if __name__ == "__main__":
    main()
