"""Verify new nodes against the Low Price API; reuse already submitted media jobs."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import json
import os
import re
import threading

import av
import numpy as np
from PIL import Image
import torch

from nov08_fixture import module

nodes = module("nov21_low_price_nodes")
api, spec, h3 = nodes.api, nodes.spec, nodes.h3
llm = module("llm_low_price_presets")


def main(reference, output):
    import folder_paths

    key = os.environ["SEEDANCE_NOV21_TEST_KEY"]
    config = {"base_url": api.DEFAULT_BASE_URL, "api_key": key}
    output.mkdir(parents=True, exist_ok=True)
    folder_paths.set_output_directory(str(output))
    existing = json.loads((reference / "private_resume.json").read_text(encoding="utf-8"))
    followup = reference.with_name("seedance_nov21_miora_followup")
    existing.update(json.loads((followup / "private_resume.json").read_text(encoding="utf-8")))
    # Use a new proof directory for an explicitly authorized new paid run.
    with (output / "run.started").open("x", encoding="utf-8"):
        pass
    lock = threading.Lock()
    current = threading.local()

    def emit(**record):
        with lock:
            print(json.dumps(record, ensure_ascii=True), flush=True)

    def image(name):
        with Image.open(reference / (name + ".png")) as value:
            return torch.from_numpy(np.array(value.convert("RGB"), dtype=np.float32) / 255).unsqueeze(0)

    def safe_message(error):
        return re.sub(r"https?://[^\s\"']+|sk-[\w-]+|task_[\w-]+", "[REDACTED]", str(error).replace(key, "[REDACTED]"))[:400]

    with api._get_session().get(api.DEFAULT_BASE_URL + "/v1/models", headers=api._headers(key), timeout=(8, 30)) as response:
        response.raise_for_status()
        available = {row["id"] for row in response.json()["data"]}

    def submitted(original):
        def submit(body, connection, **options):
            if current.name in existing:
                return existing[current.name]["task"], {}
            return original(body, connection, **options)
        return submit

    def uploaded(original):
        def upload(data, name, mime, connection):
            if current.name in existing:
                return "https://example.invalid/already-submitted/" + name
            return original(data, name, mime, connection)
        return upload

    product, subject = image("reference"), image("character")
    speech_path = reference / existing["tts-flash"]["audio_path"]
    speech = api.audio_bytes_to_comfy(speech_path.read_bytes(), "wav", 24000)
    cases = {
        "long-ecommerce": ("long", {"image1": product, "length": "short", "prompt": "A short product page for @Image1."}),
        "long-webpage": ("long", {"style_image": product, "skill": "webpage", "prompt": "Pottery studio landing page styled like @Image1."}),
        "tts-pro": ("tts", {"model": spec.GEMINI_TTS[0], "prompt": "This is a short audio check."}),
        "tts-flash-fresh": ("tts", {"model": spec.GEMINI_TTS[1], "prompt": "Hello. Thanks for listening.", "voice": "Puck"}),
        "h3-wf": ("wf", {"image1": subject, "prompt": "<Picture 1> waves once."}),
        "h3-jy": ("jy", {"image1": subject, "prompt": "<Picture 1> gently nods."}),
        "h3-charswap": ("charswap", {"image1": subject, "video1": str(reference / "h3-wf.mp4"), "prompt": "Replace the subject with <Picture 1>."}),
        "h3-digital": ("digital", {"image1": subject, "audio1": speech, "prompt": "<Picture 1> speaks calmly."}),
        "heygen-turbo": ("heygen", {"model": spec.HEYGEN[0], "prompt": "Hello. Welcome to our studio."}),
        "heygen-audio": ("heygen", {"model": spec.HEYGEN[1], "audio": speech}),
        "miora-image": ("miora", {"image1": product, "generate_type": "geometry", "face_count": 3000}),
        "miora-text-normal": ("miora", {"prompt": "A round clay teapot with a lid.", "generate_type": "normal"}),
    }

    def check(name):
        current.name = name
        try:
            if name in llm.MODELS:
                index = llm.MODELS.index(name)
                text = llm.call_g62(name, "What color is the teapot? Answer in one word." if index >= 4 else "Reply with exactly OK.",
                                   "", api_config=config, image=product if index >= 4 else None, stream=index in (3, 4), max_tokens=512)
                return {"status": "ok", "listed": llm.API_MODEL_IDS.get(name, name) in available, "text": text.strip()[:60]}
            kind, values = cases[name]
            cls = nodes.CLASSES[kind]
            result = cls().execute(api_config=config, **values)["result"]
            if kind == "long":
                details = {"shape": list(result[0].shape)}
                assert result[0].shape[2] == 1024 and result[0].shape[1] > 1024
            elif kind == "tts":
                audio = result[0]
                details = {"hz": audio["sample_rate"], "shape": list(audio["waveform"].shape)}
                assert audio["sample_rate"] == 24000 and audio["waveform"].shape[1] == 1 and audio["waveform"].abs().max() > 0
            elif kind == "miora":
                files = json.loads(result[4])
                details = {"model_bytes": Path(result[2]).stat().st_size, "files": len(files)}
                assert all(Path(entry["local_path"]).is_file() for entry in files), "Not every artifact was saved"
                assert nodes.prepare_model(result[2])[1] == "glb"
            else:
                with av.open(result[0].get_stream_source()) as container:
                    frame = next(container.decode(video=0))
                    details = {"width": frame.width, "height": frame.height, "has_audio": bool(container.streams.audio)}
            return {"status": "ok", "path": "existing task" if name in existing else "new request", **details}
        except Exception as error:
            return {"status": "failed", "reason": safe_message(error)}

    def worker(name):
        result = check(name)
        emit(case=name, **result)
        return name, result

    with (
        patch.object(api, "submit_image_task", submitted(api.submit_image_task)),
        patch.object(api, "submit_audio_task", submitted(api.submit_audio_task)),
        patch.object(nodes, "submit_kling_task", submitted(nodes.submit_kling_task)),
        patch.object(nodes, "submit_3d", submitted(nodes.submit_3d)),
        patch.object(api, "upload_media", uploaded(api.upload_media)),
        ThreadPoolExecutor(max_workers=8) as pool,
    ):
        names = ["tts-flash-fresh", *llm.MODELS[2:], *(name for name in cases if name != "tts-flash-fresh")]
        results = dict(pool.map(worker, names))
    (output / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return all(item["status"] == "ok" for item in results.values())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("output", type=Path)
    params = parser.parse_args()
    raise SystemExit(0 if main(params.reference, params.output) else 1)
