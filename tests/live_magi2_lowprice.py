"""Opt-in Magi 2 live check: one new domestic frame task and two existing tasks."""

import argparse
import json
import os
from pathlib import Path
import re
from unittest.mock import patch

import av

from nov08_fixture import ROOT, module

nodes = module("magi2_low_price_nodes")
video_node = module("nov21_low_price_nodes")


def decode(video, output):
    from io import BytesIO

    data, extension = nodes.api.video_to_upload_bytes(video)
    with av.open(BytesIO(data)) as container:
        stream = container.streams.video[0]
        has_audio = bool(container.streams.audio)
        frames = sum(1 for _ in container.decode(stream))
        if extension != "mp4" or "mp4" not in container.format.name or not frames:
            raise RuntimeError("The API did not return a decodable MP4")
        evidence = {"width": stream.width, "height": stream.height, "frames": frames, "audio": has_audio}
    output.write_bytes(data)
    return evidence


def check(output, reference):
    import folder_paths

    key = os.environ["SEEDANCE_API_KEY"]
    if output.is_relative_to(ROOT):
        raise ValueError("Save live proof outside the workspace")
    output.mkdir(parents=True, exist_ok=False)
    folder_paths.set_output_directory(str(output))
    settings = {"base_url": nodes.api.DEFAULT_BASE_URL, "api_key": key}
    config = video_node.get_config(settings)

    def redact(error):
        return re.sub(r"https?://\S+|task_[A-Za-z0-9_-]+", "[REDACTED]", str(error).replace(key, "[REDACTED]"))[:450]

    proof = {}
    for model in nodes.MODELS:
        try:
            task = (reference / (model + ".task.txt")).read_text(encoding="utf-8").strip()
            final = video_node.poll_kling_task(task, config, label=model)
            url = nodes.api.extract_legacy_video_url(final)
            video = nodes.api.download_video(url)
            proof[model] = decode(video, output / (model + ".mp4"))
        except Exception as error:
            proof[model] = {"error": redact(error)}
        print(model, proof[model], flush=True)

    original_submit = video_node.submit_kling_task

    def journal_submit(body, config, **kwargs):
        task, data = original_submit(body, config, **kwargs)
        (output / "magi-2-frame.task.txt").write_text(task, encoding="utf-8")
        print("magi-2 frame accepted; checking actual output", flush=True)
        return task, data

    start = nodes.api.torch.full((1, 432, 768, 3), .92)
    end = start.clone()
    start[:, 166:266, 280:380] = nodes.api.torch.tensor([.07, .32, .78])
    end[:, 166:266, 402:502] = nodes.api.torch.tensor([.07, .32, .78])
    try:
        with patch.object(video_node, "submit_kling_task", side_effect=journal_submit):
            output_video = nodes.T8ZhenzhenMagi2Video().execute(api_config=settings, model="magi-2",
                generation_type="frame", prompt="Move the blue square steadily from its first position to its last position. Locked camera.",
                image1=start, image2=end, seconds=4, seed=0, generate_audio=False)["result"][0]
        proof["magi-2-frame"] = decode(output_video, output / "magi-2-frame.mp4")
    except Exception as error:
        proof["magi-2-frame"] = {"error": redact(error)}
    print("magi-2-frame", proof["magi-2-frame"], flush=True)
    (output / "summary.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    return not any("error" in case for case in proof.values())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("reference", type=Path, help="Directory containing task-ID files from verified Magi 2 runs")
    args = parser.parse_args()
    raise SystemExit(not check(args.output.resolve(), args.reference.resolve()))
