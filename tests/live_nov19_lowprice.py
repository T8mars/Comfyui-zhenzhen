"""Opt-in live acceptance; one attempt per case, with resumable accepted task IDs."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
import os
from pathlib import Path
import re
import sys
import threading

import torch
from PIL import Image, ImageDraw
import numpy as np

from nov08_fixture import ROOT, module

nodes = module("nov19_low_price_nodes")
api = nodes.api
image_nov19, qwen_audio31 = nodes.images, nodes.speech
plugin = module("Comfly")


def test_live(output, key):
    import folder_paths

    folder_paths.set_output_directory(str(output))
    config = {"base_url": "https://api.seedance.nz", "api_key": key}
    journal = output / "private_resume.json"
    state = json.loads(journal.read_text(encoding="utf-8")) if journal.exists() else {}
    guard, current = threading.RLock(), threading.local()

    def persist():
        path = journal.with_suffix(".tmp")
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        path.replace(journal)

    def emit(**row):
        with guard:
            print(json.dumps(row, ensure_ascii=False), file=sys.__stdout__, flush=True)

    def redact(error):
        return re.sub(r"https?://[^\s\"']+|sk-[A-Za-z0-9_-]{10,}|task_[A-Za-z0-9_-]+",
                      "[REDACTED]", str(error).replace(key, "[REDACTED]"))[:550]

    with api._get_session().get(config["base_url"] + "/v1/models", headers=api._headers(key),
                        timeout=(8, 30), allow_redirects=False) as response:
        response.raise_for_status()
        available = {row["id"] for row in response.json()["data"]}

    source = Image.new("RGB", (384, 384), "#e8f1ef")
    draw = ImageDraw.Draw(source)
    draw.ellipse((70, 112, 314, 298), fill="#2185b5")
    draw.rectangle((137, 102, 246, 145), fill="#153c62")
    draw.ellipse((163, 73, 220, 115), fill="#efae4b")
    source.save(output / "reference.png")
    image = torch.from_numpy(np.asarray(source, dtype=np.float32) / 255).unsqueeze(0)
    tone = .08 * torch.sin(torch.arange(48000) * (2 * torch.pi * 330 / 24000))
    reference_audio = {"waveform": tone.reshape(1, 1, -1), "sample_rate": 24000}

    kling, mai = image_nov19.KLING_MODEL, image_nov19.MAI_MODELS
    flash, next_model, plus = qwen_audio31.MODELS
    cases = {
        "kling-reference": (kling, nodes.T8ZhenzhenKlingV4Image, {"prompt": "Keep the abstract blue teapot in @Image1 and put it on a pale yellow studio background.", "image1": image, "size": "1:1"}),
        "kling-group": (kling, nodes.T8ZhenzhenKlingV4Image, {"prompt": "Two related product photos of the same original blue ceramic teapot, one front view and one side view.", "size": "1:1", "sequential_image_generation": "auto", "max_images": 2}),
        "mai-standard": (mai[0], nodes.T8ZhenzhenMAIImage27, {"model": mai[0], "prompt": "A small blue ceramic teapot on a plain pale table.", "background": "opaque"}),
        "mai-flash": (mai[1], nodes.T8ZhenzhenMAIImage27, {"model": mai[1], "prompt": "Make the blue teapot emerald green and keep the composition.", "image1": image}),
        "tts-flash": (flash, nodes.T8ZhenzhenQwenAudio31, {"model": flash, "prompt": "\u4f60\u597d\uff0c\u6d4b\u8bd5\u5b8c\u6210\u3002", "language_hint": "zh", "voice": qwen_audio31.VOICES[flash][0], "seed": 0}),
        "tts-plus": (plus, nodes.T8ZhenzhenQwenAudio31, {"model": plus, "prompt": "Hello, the test is complete.", "language_hint": "en", "voice": qwen_audio31.VOICES[plus][0], "seed": 0}),
        "tts-next": (next_model, nodes.T8ZhenzhenQwenAudio31, {"model": next_model, "prompt": "Create a short, gentle two-note electronic chime inspired by @voice1, without speech.", "audio1": reference_audio, "sample_rate": "24000", "seed": 42}),
        "llm-astra": ("zhenzhen/g6.2-astra", plugin.Comfly_LLm_API, {"model": "zhenzhen/g6.2-astra", "prompt": "Reply with exactly OK.", "max_tokens": 256, "timeout": 180}),
        "llm-sol": ("zhenzhen/g6.2-sol", plugin.Comfly_LLm_API, {"model": "zhenzhen/g6.2-sol", "prompt": "Give the color of the teapot in exactly one word.", "image1": image, "stream": True, "max_tokens": 256, "timeout": 180}),
    }
    emit(available=sorted({case[0] for case in cases.values()} & available))

    def submitted(original):
        def wrapped(body, connection, **kwargs):
            with guard:
                entry = state.setdefault(current.case, {})
                if entry.get("task"):
                    return entry["task"], {}
                if entry.get("started"):
                    raise RuntimeError("Prior submission may have been sent; no replay")
                entry["started"] = True
                persist()
            task, response = original(body, connection, **kwargs)
            with guard:
                entry["task"] = task
                persist()
            emit(case=current.case, accepted=True)
            return task, response
        return wrapped

    def polled(original):
        def wrapped(task, connection, **kwargs):
            with guard:
                entry = state[current.case]
                if entry.get("final"):
                    return entry["final"]
            final = original(task, connection, **kwargs)
            with guard:
                entry["final"] = final
                persist()
            return final
        return wrapped

    replacements = {"submit_image_task": submitted, "submit_audio_task": submitted,
                    "poll_image_task": polled, "poll_audio_task": polled}
    originals = {name: getattr(api, name) for name in replacements}

    def run(item):
        case, (model, cls, kwargs) = item
        current.case = case
        if model not in available:
            emit(case=case, model=model, success=False, error="Not in /v1/models for supplied key")
            return False
        with guard:
            entry = state.setdefault(case, {})
            if entry.get("proof"):
                emit(**entry["proof"])
                return True
        emit(case=case, model=model, started=True)
        try:
            if cls is plugin.Comfly_LLm_API:
                with guard:
                    if entry.get("started"):
                        raise RuntimeError("Prior chat submission may have been sent; no replay")
                    entry["started"] = True
                    persist()
            if cls is plugin.Comfly_LLm_API:
                result = cls().Zhenzhen_run_llmapi("", "", "", "Answer concisely.", kwargs["prompt"], .6, 100,
                    model_preset=model, api_config=config, ref_image=kwargs.get("image1"),
                    stream=kwargs.get("stream", False), max_tokens=512)
            else:
                result = cls().execute(api_config=config, **kwargs)["result"]
            proof = {"case": case, "model": model, "success": True}
            if cls is plugin.Comfly_LLm_API:
                assert result[0].strip()
                proof.update(text_chars=len(result[0]), streamed=bool(kwargs.get("stream")))
                if case == "llm-sol":
                    assert "blue" in result[0].lower()
            elif cls is nodes.T8ZhenzhenQwenAudio31:
                wave = result[0]["waveform"]
                assert wave.shape[-1] > 0 and torch.isfinite(wave).all() and wave.abs().max() > .001
                proof.update(sample_rate=result[0]["sample_rate"], channels=wave.shape[1],
                             samples=wave.shape[-1])
            else:
                images = result[0] if cls is nodes.T8ZhenzhenKlingV4Image else [result[0]]
                assert len(images) >= (2 if case == "kling-group" else 1)
                for tensor in images:
                    assert torch.isfinite(tensor).all() and tensor.std() > .01
                proof["image_sizes"] = [[int(t.shape[2]), int(t.shape[1])] for t in images]
            with guard:
                entry["proof"] = proof
                persist()
            emit(**proof)
            return True
        except Exception as error:
            message = redact(error)
            with guard:
                entry["error"] = message
                persist()
            emit(case=case, model=model, success=False, error=message)
            return False

    try:
        for name, factory in replacements.items():
            setattr(api, name, factory(originals[name]))
        with contextlib.redirect_stdout(io.StringIO()), ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(run, cases.items()))
        proof = [entry["proof"] for entry in state.values() if "proof" in entry]
        (output / "proof.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if all(results) else 1
    finally:
        for name, original in originals.items():
            setattr(api, name, original)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    key = os.environ.pop("ZHENZHEN_NOV19_KEY", "")
    if not key:
        raise SystemExit("ZHENZHEN_NOV19_KEY is required")
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        raise SystemExit("Private test artifacts must stay outside the repository")
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".live.lock"
    try:
        with lock.open("x"):
            pass
    except FileExistsError:
        raise SystemExit("The live test directory is already locked; no requests sent")
    try:
        sys.exit(test_live(output, key))
    finally:
        lock.unlink()
