"""Opt-in three-creation Tripo chain; private resume state stays outside the repo."""

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

from nov08_fixture import module, ROOT

nodes = module("tripo_low_price_nodes")
artifacts = module("tripo_artifacts")


def main(args):
    key = os.environ.get("ZHENZHEN_TRIPO_API_KEY", "").strip()
    if not args.confirm_live or not key:
        raise SystemExit("Requires --confirm-live and ZHENZHEN_TRIPO_API_KEY")
    output = Path(args.output).resolve()
    if output.is_relative_to(ROOT):
        raise SystemExit("Live artifacts must stay outside the repository")
    output.mkdir(parents=True, exist_ok=True)
    import folder_paths
    folder_paths.set_output_directory(str(output))
    state_path = output / "private_resume.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    proof, current = [], ""
    original_submit, original_poll = nodes.submit_3d, nodes.poll_3d

    def save_state():
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def submit(payload, config):
        previous = state.get(current, {})
        if previous.get("task"):
            return previous["task"], {}
        if previous.get("uncertain") or sum(bool(value.get("task")) for value in state.values()) >= 3:
            raise RuntimeError("Three-creation limit reached or submission uncertain; no replay")
        state[current] = {"uncertain": True}
        save_state()
        task, body = original_submit(payload, config)
        state[current] = {"task": task}
        save_state()
        return task, body

    def poll(task, config):
        if state[current].get("final"):
            return state[current]["final"]
        final = original_poll(task, {**config, "poll_interval": 5, "max_poll_time": 1800})
        state[current]["final"] = final
        save_state()
        return final

    nodes.submit_3d, nodes.poll_3d = submit, poll
    generated = segmented = None
    try:
        for label, cls in (("generate", nodes.T8ZhenzhenTripoGenerate), ("segment", nodes.T8ZhenzhenTripoMesh), ("complete", nodes.T8ZhenzhenTripoMesh)):
            current = label
            if label == "generate":
                kwargs = {"model": "tripo-p-p1-text-to-3d", "prompt": "A simple low-poly toy robot with a square head, short torso, two separate arms and two legs, standing upright.",
                    "face_limit": 1000, "texture": "false", "pbr": "false"}
            elif label == "segment":
                kwargs = {"model": "tripo-mesh-segment-v1", "model_url": generated[1]}
            else:
                names = [name for name in json.loads(segmented[6]) if name.startswith("tripo_part_")]
                if not segmented[4] or not names:
                    raise RuntimeError("Segmentation returned no upstream ID/selectable part names")
                kwargs = {"model": "tripo-mesh-complete", "tripo_segment_task_id": segmented[4],
                    "completion_mode": "quick_cap", "part_names": json.dumps(names[:1])}
            print("START " + label, flush=True)
            start = time.monotonic()
            with contextlib.redirect_stdout(io.StringIO()):
                result = cls().execute(api_config={"base_url": "https://api.seedance.nz", "api_key": key}, **kwargs)["result"]
            document = artifacts.glb_document(result[2])
            if not document.get("meshes"):
                raise RuntimeError("Downloaded GLB contains no meshes")
            saved = output / {"generate": "generated.glb", "segment": "segmented.glb", "complete": "completed.glb"}[label]
            shutil.copy2(result[2], saved)
            item = {"case": label, "success": True, "seconds_elapsed": round(time.monotonic()-start, 2),
                "bytes": saved.stat().st_size, "meshes": len(document["meshes"]), "named_nodes": len(json.loads(result[6])),
                "files": len(json.loads(result[5])), "has_tripo_id": bool(result[4])}
            proof.append(item)
            print(json.dumps(item), flush=True)
            (output / "proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
            if label == "generate":
                generated = result
            elif label == "segment":
                segmented = result
        return 0
    except Exception as error:
        message = str(error).replace(key, "[KEY]")
        message = re.sub(r"https?://[^\s\"']+|sk-[A-Za-z0-9]+|task_[A-Za-z0-9_-]+", "[REDACTED]", message)
        message = re.sub(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", "[ID]", message)
        print(json.dumps({"case": current, "success": False, "error": type(error).__name__, "message": message[:1000]}), flush=True)
        return 1
    finally:
        nodes.submit_3d, nodes.poll_3d = original_submit, original_poll


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--output", required=True)
    raise SystemExit(main(parser.parse_args()))
