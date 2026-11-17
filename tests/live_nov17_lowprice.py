"""Opt-in node acceptance with private, resumable no-replay task journals."""

import argparse
import concurrent.futures
import contextlib
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import threading
import time

from nov08_fixture import ROOT, module

api = module("seedance_low_price_nodes")
h3 = module("h3_comfy_low_price_nodes")
tts = module("doubao_tts_low_price_nodes")


def main(args):
    key = os.environ.get("ZHENZHEN_NOV17_KEY", "").strip()
    output = Path(args.output).resolve()
    if not args.confirm_live or not key or output.is_relative_to(ROOT):
        raise RuntimeError("Explicit confirmation, key and private output outside the repository are required")
    import av
    import folder_paths
    import numpy as np
    from PIL import Image, ImageDraw
    import torch
    output.mkdir(parents=True, exist_ok=True)
    folder_paths.set_output_directory(str(output))
    path = output / "private_resume.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"cases": {}, "uploads": {}}
    mutex, local = threading.RLock(), threading.local()
    config = {"base_url": "https://api.seedance.nz", "api_key": key, "max_poll_time": 1800}

    def persist():
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def log(value):
        with mutex:
            sys.__stdout__.write(json.dumps(value, ensure_ascii=False) + "\n")
            sys.__stdout__.flush()

    def safe(error):
        return re.sub(r"https?://[^\s\"']+|sk-[A-Za-z0-9]+|task_[A-Za-z0-9_-]+", "[REDACTED]", str(error).replace(key, "[KEY]"))[:900]

    def drawing(color, phase=0):
        image = Image.new("RGB", (640, 480), "#dde8e9")
        draw = ImageDraw.Draw(image)
        x = 320 + int(20 * math.sin(phase))
        draw.rectangle((0, 405, 640, 480), fill="#b7c9c6")
        draw.ellipse((x-65, 60, x+65, 195), fill="#f5c89b", outline="#273238", width=5)
        draw.ellipse((x-26, 115, x-14, 129), fill="#273238")
        draw.ellipse((x+14, 115, x+26, 129), fill="#273238")
        draw.arc((x-25, 140, x+25, 172), 0, 180, fill="#273238", width=4)
        draw.rounded_rectangle((x-65, 195, x+65, 350), radius=20, fill=color, outline="#273238", width=5)
        for side in (-1, 1):
            draw.line((x+side*35, 350, x+side*40, 405), fill="#273238", width=22)
            draw.line((x+side*60, 220, x+side*110, 260+int(20*math.sin(phase))), fill=color, width=25)
        return image

    image = torch.from_numpy(np.asarray(drawing("#148bb5"), dtype=np.float32) / 255).unsqueeze(0)
    last = torch.from_numpy(np.asarray(drawing("#148bb5", 1), dtype=np.float32) / 255).unsqueeze(0)
    audio = {"waveform": (torch.sin(torch.arange(48000) * (2 * math.pi * 440 / 24000)) * .04).reshape(1, 1, -1), "sample_rate": 24000}
    source = output / "source.mp4"
    if not source.exists():
        with av.open(str(source), "w") as container:
            stream = container.add_stream("libx264", rate=24)
            stream.width, stream.height, stream.pix_fmt = 640, 480, "yuv420p"
            sound = container.add_stream("aac", rate=24000)
            sound.layout = "mono"
            for index in range(120):
                for packet in stream.encode(av.VideoFrame.from_image(drawing("#b64050", index / 12))):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
            samples = (np.sin(np.arange(120000) * (2 * math.pi * 220 / 24000)) * .04).astype(np.float32).reshape(1, -1)
            frame = av.AudioFrame.from_ndarray(samples, format="fltp", layout="mono")
            frame.sample_rate, frame.pts = 24000, 0
            for packet in sound.encode(frame):
                container.mux(packet)
            for packet in sound.encode():
                container.mux(packet)

    originals = {"submit": api.submit_task, "audio_submit": api.submit_audio_task, "h3_submit": h3.submit_task,
                 "poll": api.poll_task, "audio_poll": api.poll_audio_task, "h3_poll": h3.poll_task, "upload": api.upload_media}

    def submit(original, pair):
        def wrapped(body, connection, **kwargs):
            with mutex:
                entry = state["cases"].setdefault(local.case, {})
                if entry.get("task"):
                    return (entry["task"], {}) if pair else entry["task"]
                if entry.get("started"):
                    raise RuntimeError("Uncertain previous submit: automatic replay is forbidden")
                if sum(bool(item.get("started")) for item in state["cases"].values()) >= 12:
                    raise RuntimeError("Twelve-request creation limit reached")
                entry.update(started=True, payload=body)
                persist()
            result = original(body, connection, **kwargs)
            with mutex:
                entry["task"] = result[0] if pair else result
                persist()
            log({"case": local.case, "submitted": True})
            return result
        return wrapped

    def poll(original):
        def wrapped(task, connection, **kwargs):
            with mutex:
                entry = state["cases"][local.case]
                if entry.get("final"):
                    return entry["final"]
            result = original(task, connection, **kwargs)
            with mutex:
                entry["final"] = result
                persist()
            return result
        return wrapped

    def upload(data, filename, mime, connection):
        digest = hashlib.sha256(data).hexdigest() + mime
        with mutex:
            if digest not in state["uploads"]:
                state["uploads"][digest] = originals["upload"](data, filename, mime, connection)
                persist()
            return state["uploads"][digest]

    api.submit_task, api.submit_audio_task, h3.submit_task = submit(originals["submit"], True), submit(originals["audio_submit"], True), submit(originals["h3_submit"], False)
    api.poll_task, api.poll_audio_task, h3.poll_task = poll(originals["poll"]), poll(originals["audio_poll"]), poll(originals["h3_poll"])
    api.upload_media = upload
    cases = []
    for kind, cls in h3.CLASSES.items():
        values = {"prompt": "<Picture 1> waves gently in a bright studio, preserve character identity.", "resolution": "480p", "seconds": "5" if kind in ("charswap", "wuxi") else "3", "image1": image}
        if kind in ("charswap", "wuxi"):
            values["video1"] = str(source)
        if kind != "charswap":
            values["audio1"] = audio
        cases.append((h3.contracts.PROFILES[kind]["model"], cls, values))
    for model in api.SEEDANCE25_FLASH_MODELS:
        values = {"model": model, "prompt": "A blue puppet waves gently in a bright studio. Keep the puppet appearance consistent.", "seconds": "4", "resolution": "480p", "ratio": "adaptive"}
        if model.endswith(("-i2v", "-multi")):
            values["image1"] = image
        if model.endswith("-i2v"):
            values["image2"] = last
        if model.endswith("-multi"):
            values.update(video1=str(source), audio1=audio)
        cases.append((model, api.Comfly_seedance25_standard_low_price, values))
    cases.extend((label, tts.T8ZhenzhenDoubaoSeedTTS20, values) for label, values in [
        ("doubao-tts-vivi", {"prompt": "你好，这是豆包语音合成的实际测试。", "context_texts": "请用温柔亲切的语气说。"}),
        ("doubao-tts-tim", {"prompt": "Every great journey begins with a single step.", "speaker": "en_male_tim_uranus_bigtts", "explicit_language": "en", "output_format": "wav"})])

    def run(case):
        label, cls, values = case
        local.case = label
        start = time.monotonic()
        try:
            log({"case": label, "starting": True})
            result = getattr(cls(), cls.FUNCTION)(api_config=config, **values)
            result = result["result"] if isinstance(result, dict) else result
            proof = {"case": label, "success": True}
            if label.startswith("doubao"):
                wave = result[0]["waveform"]
                if not torch.isfinite(wave).all() or float(wave.abs().max()) < .00001:
                    raise RuntimeError("Empty or silent decoded audio")
                proof.update(shape=list(wave.shape), sample_rate=result[0]["sample_rate"])
            else:
                video = result[0]
                media = video if isinstance(video, str) else video.get_stream_source()
                with av.open(media) as container:
                    stream = container.streams.video[0]
                    frames = sum(1 for _ in container.decode(video=0))
                    if frames < 1:
                        raise RuntimeError("Video has no decoded frames")
                    proof.update(width=stream.width, height=stream.height, frames=frames, audio_streams=len(container.streams.audio))
            proof["elapsed"] = round(time.monotonic() - start, 2)
        except Exception as error:
            proof = {"case": label, "success": False, "message": safe(error), "elapsed": round(time.monotonic() - start, 2)}
        with mutex:
            state["cases"].setdefault(label, {})["proof"] = proof
            persist()
        log(proof)
        return proof["success"]

    try:
        with contextlib.redirect_stdout(io.StringIO()), concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            outcomes = list(pool.map(run, cases))
        return 0 if all(outcomes) else 1
    finally:
        api.submit_task, api.submit_audio_task, h3.submit_task = originals["submit"], originals["audio_submit"], originals["h3_submit"]
        api.poll_task, api.poll_audio_task, h3.poll_task, api.upload_media = originals["poll"], originals["audio_poll"], originals["h3_poll"], originals["upload"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--output", required=True)
    raise SystemExit(main(parser.parse_args()))
