"""Three fresh representative tasks plus completed-response replay for the other profiles."""

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time

import numpy as np
from PIL import Image, ImageDraw
import torch

from nov08_fixture import ROOT, module

nodes = module("seedream55_low_price_nodes")


def source_image():
    image = Image.new("RGBA", (1024, 1024), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((120, 250, 400, 650), 35, fill=(200, 40, 30, 255))
    draw.rectangle((560, 520, 820, 780), fill=(30, 90, 200, 255))
    draw.ellipse((540, 120, 850, 350), fill=(30, 150, 70, 255))
    return torch.from_numpy(np.array(image, dtype=np.float32) / 255).unsqueeze(0)


def main(args):
    key = os.environ.get("ZHENZHEN_55_API_KEY", "").strip()
    if not args.confirm_live or not key:
        raise SystemExit("Requires --confirm-live and ZHENZHEN_55_API_KEY")
    directory, reference = Path(args.output).resolve(), Path(args.reference).resolve()
    if directory.is_relative_to(ROOT):
        raise SystemExit("Private live data must stay outside the repository")
    directory.mkdir(parents=True, exist_ok=True)
    import folder_paths
    import av
    folder_paths.set_output_directory(str(directory))
    state_path = directory / "private_resume.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    reference_state = json.loads((reference / "private_resume.json").read_text())
    diagnostics = json.loads((reference / "private_draft_diagnostics.json").read_text())
    draft = diagnostics["fresh-source"]["task"]
    config = {"base_url": "https://api.seedance.nz", "api_key": key}
    current, proof, replaying = "", [], False
    original_submit, original_poll, original_upload = nodes.submit_task, nodes.poll_task, nodes.api.upload_media

    def persist():
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def submit(payload, connection, image=False):
        if replaying:
            if current == "domestic_enhance":
                return diagnostics["fresh-node-default"]["task"]
            return reference_state[current]["task"]
        old = state.get(current, {})
        if old.get("task"):
            return old["task"]
        if old.get("uncertain") or len(state) >= 3:
            raise RuntimeError("No replay: three-creation limit or uncertain submission")
        state[current] = {"uncertain": True}
        persist()
        task = original_submit(payload, connection, image=image)
        state[current] = {"task": task}
        persist()
        return task

    def poll(task, connection, image=False, on_progress=None):
        if replaying:
            return diagnostics["fresh-node-default"]["final"] if current == "domestic_enhance" else reference_state[current]["final"]
        if state[current].get("final"):
            return state[current]["final"]
        final = original_poll(task, connection, image=image, on_progress=on_progress)
        state[current]["final"] = final
        persist()
        return final

    def upload(*args, **kwargs):
        return "https://example.test/replay-source.png" if replaying else original_upload(*args, **kwargs)

    nodes.submit_task, nodes.poll_task, nodes.api.upload_media = submit, poll, upload

    def run(label, cls, kind, **kwargs):
        nonlocal current
        current = label
        print("START " + label + (" (completed-response replay)" if replaying else " (fresh/resumed task)"), flush=True)
        start = time.monotonic()
        with contextlib.redirect_stdout(io.StringIO()):
            result = cls().execute(api_config=config, **kwargs)
        values = result["result"] if isinstance(result, dict) else result
        item = {"case": label, "fresh": not replaying, "success": True, "elapsed": round(time.monotonic()-start, 2)}
        if kind == "video":
            path = values[0].get_stream_source() if not isinstance(values[0], str) else values[0]
            with av.open(path) as container:
                stream = container.streams.video[0]
                frames = sum(1 for _ in container.decode(video=0))
                item.update(bytes=Path(path).stat().st_size, width=stream.width, height=stream.height, frames=frames,
                    suffix=Path(path).suffix, major_brand=container.metadata.get("major_brand", ""))
            if frames < 1 or min(item["width"], item["height"]) < 1080:
                raise RuntimeError("Enhanced video is empty or did not reach 1080p")
        elif kind == "layers":
            paths = json.loads(values[6])
            if values[3] < 2 or any(len(part) != values[3] for part in (values[0], values[1], paths)):
                raise RuntimeError("Decomposition did not preserve all images/masks/paths")
            item.update(images=values[3], shapes=[list(value.shape) for value in values[0]], bytes=[Path(path).stat().st_size for path in paths],
                has_metadata=bool(json.loads(values[7])))
        else:
            item.update(shape=list(values[0].shape), bytes=Path(values[5]).stat().st_size, transparent_pixels=int((values[4] > 0).sum()))
        proof.append(item)
        print(json.dumps(item), flush=True)
        (directory / "proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
        return values

    try:
        image = source_image()
        edited = run("fresh_i2i", nodes.T8ZhenzhenSeedream55Image, "image", model="seedream-v5.5-i2i", image1=image,
            prompt="Keep the three separate shapes. Change the blue square to yellow, add a plain white opaque background.", output_format="jpeg", background="opaque")
        run("fresh_layers", nodes.T8ZhenzhenSeedream55Layers, "layers", model="dola-seedream-5.5-layer-decomposition",
            image=edited[0], resolution="1k", max_images=2, text_recognition=True, output_format="png")
        response = nodes.api._get_session().get(config["base_url"] + "/v1/videos/" + draft, headers=nodes.api._headers(key), timeout=60)
        try:
            response.raise_for_status()
            source = response.json()
        finally:
            response.close()
        if source.get("status") != "completed":
            raise RuntimeError("The reused domestic source draft is not completed/accessible")
        run("fresh_enhance", nodes.T8ZhenzhenSeedance25DraftToVideo, "video", model=nodes.DRAFT_MODELS[0], draft_task_id=draft)
        replaying = True
        for global_ in (False, True):
            label, prefix = ("global", "dola-seedream-5.5") if global_ else ("domestic", "seedream-v5.5")
            run(label+"_t2i", nodes.T8ZhenzhenSeedream55Image, "image", model=prefix+"-t2i", prompt="Three separate colored shapes isolated on transparent background.", background="transparent")
            run(label+"_i2i", nodes.T8ZhenzhenSeedream55Image, "image", model=prefix+"-i2i", prompt="Change the blue object to yellow.", image1=image, output_format="jpeg", background="opaque")
            run(label+"_layers", nodes.T8ZhenzhenSeedream55Layers, "layers", model=prefix+"-layer-decomposition", image=image, max_images=2)
            source_task = reference_state["global_draft"]["task"] if global_ else draft
            run(label+"_enhance", nodes.T8ZhenzhenSeedance25DraftToVideo, "video", model=nodes.DRAFT_MODELS[int(global_)], draft_task_id=source_task,
                output_format="mov" if global_ else "mp4", return_last_frame=global_)
        return 0
    except Exception as error:
        message = str(error).replace(key, "[KEY]")
        message = re.sub(r"https?://[^\s\"']+|sk-[A-Za-z0-9]+|task_[A-Za-z0-9_-]+", "[REDACTED]", message)
        print(json.dumps({"case": current, "success": False, "error": type(error).__name__, "message": message[:1000]}), flush=True)
        return 1
    finally:
        nodes.submit_task, nodes.poll_task, nodes.api.upload_media = original_submit, original_poll, original_upload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--reference", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".live.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(descriptor)
    try:
        raise SystemExit(main(args))
    finally:
        lock.unlink(missing_ok=True)
