"""Paid end-to-end verification for all documented Flow Music actions.

Set SEEDANCE_API_KEY before running. The script never prints or writes API
keys, task identifiers, clip identifiers, or result URLs.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import latest_image_audio_low_price_nodes as latest


def make_reference_audio(seconds: float = 20.0, sample_rate: int = 24000):
    sample_count = int(seconds * sample_rate)
    timeline = torch.arange(sample_count, dtype=torch.float32) / sample_rate
    waveform = (
        0.14 * torch.sin(2 * torch.pi * 220.0 * timeline)
        + 0.06 * torch.sin(2 * torch.pi * 330.0 * timeline)
    )
    envelope = torch.sin(torch.linspace(0.0, torch.pi, sample_count)).clamp_min(0.0)
    return {
        "waveform": (waveform * envelope).view(1, 1, -1),
        "sample_rate": sample_rate,
    }


def common_values() -> Dict[str, Any]:
    return {
        "version": "default",
        "sound_prompt": "short warm ambient piano with soft strings",
        "lyrics": "",
        "prompt": "a short hopeful song about light after rain",
        "title": "",
        "bpm": 96,
        "length": 8,
        "clip_id": "",
        "extend_from_s": 0.0,
        "extend_s": 15,
        "instruction": "continue naturally with gentle piano",
        "start_s": 1.0,
        "end_s": 3.0,
        "strength": 0.25,
        "format": "mp3",
        "preset": "simple",
        "seed": 7,
    }


def run_action(
    operation: str,
    config: Dict[str, Any],
    *,
    clip_id: str = "",
    audio: Any = None,
    version: str = "default",
):
    values = common_values()
    values["clip_id"] = clip_id
    values["version"] = version
    result = latest.Comfly_flowmusic_lowprice().execute(
        operation=operation,
        audio=audio,
        api_config=config,
        skip_error=False,
        **values,
    )["result"]

    response = json.loads(result[10])
    data = response.get("data") if isinstance(response, dict) else None
    status = str(data.get("status") or "") if isinstance(data, dict) else ""
    if status.lower() not in {"completed", "complete", "success", "succeeded"}:
        raise RuntimeError(f"{operation} did not return a completed task")
    if operation == "flowmusic-lyrics" and not str(result[3]).strip():
        raise RuntimeError("flowmusic-lyrics returned no text")
    if operation == "flowmusic-stems":
        path = Path(result[7])
        if path.suffix.lower() != ".zip" or not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError("flowmusic-stems did not download a ZIP result")
    if operation == "flowmusic-video-clip":
        path = Path(result[7])
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError("flowmusic-video-clip did not download an MP4 result")
    if operation in {
        "flowmusic-generation",
        "flowmusic-upload-audio",
        "flowmusic-extend",
        "flowmusic-replace",
        "flowmusic-cover",
        "flowmusic-download-audio",
    }:
        audio_result = result[0]
        waveform = audio_result.get("waveform") if isinstance(audio_result, dict) else None
        if not torch.is_tensor(waveform) or waveform.numel() == 0:
            raise RuntimeError(f"{operation} did not return decoded audio")
    print(f"{operation} SUCCESS", flush=True)
    return result


def main() -> None:
    api_key = os.environ.get("SEEDANCE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set SEEDANCE_API_KEY to run paid live verification")
    config = {
        "base_url": "https://api.seedance.nz",
        "api_key": api_key,
        "timeout": 120,
        "upload_timeout": 180,
        "poll_interval": 4,
        "max_poll_time": 2400,
    }
    requested_text = os.environ.get("FLOWMUSIC_LIVE_ONLY", "").strip()
    requested = {
        item.strip()
        for item in requested_text.split(",")
        if item.strip()
    }
    all_actions = set(latest.FLOWMUSIC_OPERATIONS)
    if not requested:
        requested = all_actions
    unknown = requested - all_actions
    if unknown:
        raise SystemExit(f"Unknown FLOWMUSIC_LIVE_ONLY actions: {sorted(unknown)}")

    clip_actions = {
        "flowmusic-extend",
        "flowmusic-replace",
        "flowmusic-cover",
        "flowmusic-stems",
        "flowmusic-download-audio",
        "flowmusic-video-clip",
    }
    clip_source = os.environ.get("FLOWMUSIC_CLIP_SOURCE", "generation").strip().lower()
    if clip_source not in {"upload", "generation"}:
        raise SystemExit("FLOWMUSIC_CLIP_SOURCE must be upload or generation")

    with tempfile.TemporaryDirectory(prefix="flowmusic_live_") as output_dir:
        previous_output = os.environ.get("SEEDANCE_OUTPUT_DIR")
        os.environ["SEEDANCE_OUTPUT_DIR"] = output_dir
        try:
            completed = 0
            generated = None
            if "flowmusic-generation" in requested:
                generated = run_action("flowmusic-generation", config)
                completed += 1
            if "flowmusic-lyrics" in requested:
                run_action("flowmusic-lyrics", config)
                completed += 1

            clip_id = ""
            needs_clip = bool(requested & clip_actions)
            if needs_clip and clip_source == "generation":
                if generated is None:
                    generated = run_action("flowmusic-generation", config)
                clip_id = str(generated[4]).strip()

            if (
                "flowmusic-upload-audio" in requested
                or needs_clip and clip_source == "upload"
            ):
                uploaded = run_action(
                    "flowmusic-upload-audio",
                    config,
                    audio=make_reference_audio(),
                )
                uploaded_clip_id = str(uploaded[4]).strip()
                if not uploaded_clip_id:
                    raise RuntimeError("flowmusic-upload-audio returned no clip_id")
                if needs_clip and clip_source == "upload":
                    clip_id = uploaded_clip_id
                if "flowmusic-upload-audio" in requested:
                    completed += 1

            if needs_clip and not clip_id:
                raise RuntimeError(f"flowmusic-{clip_source} returned no clip_id")

            for operation in (
                "flowmusic-extend",
                "flowmusic-replace",
                "flowmusic-cover",
                "flowmusic-stems",
                "flowmusic-download-audio",
                "flowmusic-video-clip",
            ):
                if operation not in requested:
                    continue
                run_action(
                    operation,
                    config,
                    clip_id=clip_id,
                    version="lyria-3.5" if operation == "flowmusic-replace" else "default",
                )
                completed += 1
        finally:
            if previous_output is None:
                os.environ.pop("SEEDANCE_OUTPUT_DIR", None)
            else:
                os.environ["SEEDANCE_OUTPUT_DIR"] = previous_output
    print(f"LIVE_CHECKS {completed}/{len(requested)} SUCCESS", flush=True)


if __name__ == "__main__":
    main()
