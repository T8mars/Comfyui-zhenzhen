"""Paid end-to-end verification for the latest image and audio nodes.

Set SEEDANCE_API_KEY before running. The script prints only model names and
decoded media dimensions; task identifiers and result URLs are never printed
or written to the repository.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable

import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import latest_image_audio_low_price_nodes as latest


ALL_MODELS = [
    latest.ZHENZHEN_IMAGE_GK_V2_MODEL,
    latest.ZHENZHEN_IMAGE_GK_V2_EDIT_MODEL,
    *latest.WAN27_GLOBAL_IMAGE_MODELS,
    *latest.QWEN3_TTS_MODELS,
    *latest.MINIMAX_AUDIO_MODELS,
    *latest.MUREKA_BGM_MODELS,
]


def selected_models() -> list[str]:
    selection = os.environ.get("LATEST_IMAGE_AUDIO_LIVE_ONLY", "all").strip()
    if not selection or selection.lower() == "all":
        return list(ALL_MODELS)
    models = [value.strip() for value in selection.split(",") if value.strip()]
    unknown = [model for model in models if model not in ALL_MODELS]
    if unknown:
        raise SystemExit(
            "LATEST_IMAGE_AUDIO_LIVE_ONLY contains unsupported model names: "
            + ", ".join(unknown)
        )
    return models


def make_reference_image() -> torch.Tensor:
    axis = torch.linspace(0.0, 1.0, 512)
    horizontal = axis.view(1, 1, 512, 1).expand(1, 512, 512, 1)
    vertical = axis.view(1, 512, 1, 1).expand(1, 512, 512, 1)
    blue = torch.full_like(horizontal, 0.28)
    image = torch.cat((horizontal, vertical, blue), dim=-1)
    image[:, 148:364, 148:364, :] = torch.tensor([0.94, 0.72, 0.16])
    return image


def make_reference_audio(seconds: float = 12.0, sample_rate: int = 24000) -> Dict[str, Any]:
    sample_count = int(seconds * sample_rate)
    timeline = torch.arange(sample_count, dtype=torch.float32) / sample_rate
    waveform = (
        0.16 * torch.sin(2 * torch.pi * 180.0 * timeline)
        + 0.08 * torch.sin(2 * torch.pi * 260.0 * timeline)
    )
    envelope = torch.linspace(0.15, 1.0, sample_count).clamp(max=1.0)
    return {
        "waveform": (waveform * envelope).view(1, 1, -1),
        "sample_rate": sample_rate,
    }


def normalize_clone_reference(audio: Dict[str, Any]) -> Dict[str, Any]:
    waveform = audio["waveform"].detach().float()
    sample_rate = int(audio["sample_rate"])
    if waveform.ndim == 2:
        waveform = waveform.unsqueeze(0)
    target = sample_rate * 12
    if waveform.shape[-1] < target:
        repeats = (target + waveform.shape[-1] - 1) // waveform.shape[-1]
        waveform = waveform.repeat(1, 1, repeats)
    return {"waveform": waveform[..., :target], "sample_rate": sample_rate}


def validate_image(model: str, image: Any) -> None:
    if not torch.is_tensor(image) or image.ndim != 4:
        raise RuntimeError(f"{model} did not return a four-dimensional IMAGE")
    if image.shape[0] < 1 or image.shape[-1] != 3 or min(image.shape[1:3]) <= 0:
        raise RuntimeError(f"{model} returned an invalid IMAGE shape")
    if not torch.isfinite(image).all():
        raise RuntimeError(f"{model} returned non-finite IMAGE values")
    print(f"{model} SUCCESS image={tuple(image.shape)}", flush=True)


def validate_audio(model: str, audio: Any, require_signal: bool = True) -> None:
    if not isinstance(audio, dict):
        raise RuntimeError(f"{model} did not return a ComfyUI AUDIO object")
    waveform = audio.get("waveform")
    sample_rate = int(audio.get("sample_rate") or 0)
    if not torch.is_tensor(waveform) or waveform.ndim != 3:
        raise RuntimeError(f"{model} returned an invalid AUDIO waveform")
    if sample_rate <= 0 or waveform.shape[-1] <= 0 or not torch.isfinite(waveform).all():
        raise RuntimeError(f"{model} returned an invalid decoded AUDIO result")
    if require_signal and float(waveform.abs().max()) <= 0.0:
        raise RuntimeError(f"{model} returned only silence")
    duration = waveform.shape[-1] / sample_rate
    print(
        f"{model} SUCCESS audio={tuple(waveform.shape)} "
        f"sample_rate={sample_rate} duration={duration:.2f}s",
        flush=True,
    )


def run_image_model(model: str, config: Dict[str, Any], reference: torch.Tensor) -> None:
    if model == latest.ZHENZHEN_IMAGE_GK_V2_MODEL:
        result = latest.Comfly_zhenzhen_image_gk_v2_lowprice().generate(
            prompt="A cobalt glass cube on a clean white studio table, soft daylight",
            size="1:1",
            n=1,
            api_config=config,
            skip_error=False,
        )
    elif model == latest.ZHENZHEN_IMAGE_GK_V2_EDIT_MODEL:
        result = latest.Comfly_zhenzhen_image_gk_v2_edit_lowprice().generate(
            prompt=(
                "Keep the central golden square and transform the background "
                "into a clean blue watercolor poster"
            ),
            aspect_ratio="1:1",
            resolution="1k",
            n=1,
            nsfw_check=False,
            image1=reference,
            api_config=config,
            skip_error=False,
        )
    else:
        kwargs: Dict[str, Any] = {
            "model": model,
            "prompt": (
                "Keep the central object recognizable and replace the background "
                "with a clean pale gray studio set"
                if model in latest.WAN27_GLOBAL_I2I_MODELS
                else "A cobalt glass sculpture on a clean white studio table, soft daylight"
            ),
            "width": 1024,
            "height": 1024,
            "thinking_mode": True,
            "api_config": config,
            "skip_error": False,
        }
        if model in latest.WAN27_GLOBAL_I2I_MODELS:
            kwargs["image1"] = reference
        result = latest.Comfly_wan_2_7_global_image_lowprice().generate(**kwargs)
    validate_image(model, result[0])


def run_qwen_model(model: str, config: Dict[str, Any]) -> Dict[str, Any]:
    result = latest.Comfly_qwen3_tts_lowprice().generate(
        model=model,
        prompt=(
            "清晨的阳光穿过窗帘，房间里安静而温暖。今天我们一起测试自然清晰的语音合成效果。"
        ),
        voice="Cherry",
        language_type="Chinese",
        instructions="语气自然温暖，语速稍慢，发音清晰",
        optimize_instructions=True,
        api_config=config,
        skip_error=False,
    )
    validate_audio(model, result[0])
    return result[0]


def minimax_values(model: str) -> Dict[str, Any]:
    return {
        "model": model,
        "prompt": (
            "A short peaceful ambient piano theme with soft strings"
            if model == latest.MINIMAX_MUSIC_MODEL
            else "清晨的阳光穿过窗帘，房间里安静而温暖。"
        ),
        "lyrics": "",
        "is_instrumental": True,
        "lyrics_optimizer": False,
        "voice_id": "Wise_Woman",
        "speed": 1.0,
        "volume": 1.0,
        "pitch": 0,
        "language_boost": "Chinese",
        "output_format": "mp3",
        "sample_rate": "32000",
        "bitrate": "128000",
        "channel": "1",
        "custom_voice_id": f"CodexVoice{int(time.time())}",
        "clone_target_model": latest.MINIMAX_SPEECH_HD_MODEL,
        "need_noise_reduction": False,
        "need_volume_normalization": False,
    }


def run_minimax_model(
    model: str,
    config: Dict[str, Any],
    clone_reference: Dict[str, Any],
) -> Dict[str, Any]:
    result = latest.Comfly_minimax_audio_lowprice().generate(
        api_config=config,
        reference_audio=(
            clone_reference if model == latest.MINIMAX_VOICE_CLONE_MODEL else None
        ),
        skip_error=False,
        **minimax_values(model),
    )
    if model == latest.MINIMAX_VOICE_CLONE_MODEL and not result[2].strip():
        raise RuntimeError("minimax-voice-clone returned no voice identifier")
    validate_audio(model, result[0])
    return result[0]


def run_mureka_model(model: str, config: Dict[str, Any]) -> None:
    result = latest.Comfly_mureka_bgm_lowprice().generate(
        model=model,
        prompt="A short calm acoustic background theme with warm piano and light strings",
        instrumental_id="",
        n=1,
        api_config=config,
        skip_error=False,
    )
    audios = result[0]
    if not isinstance(audios, list) or len(audios) != 1:
        raise RuntimeError(f"{model} did not return the requested ordered audio list")
    validate_audio(model, audios[0])


def run_models(models: Iterable[str], config: Dict[str, Any]) -> None:
    reference_image = make_reference_image()
    clone_reference = make_reference_audio()
    for model in models:
        try:
            if model in {
                latest.ZHENZHEN_IMAGE_GK_V2_MODEL,
                latest.ZHENZHEN_IMAGE_GK_V2_EDIT_MODEL,
                *latest.WAN27_GLOBAL_IMAGE_MODELS,
            }:
                run_image_model(model, config, reference_image)
            elif model in latest.QWEN3_TTS_MODELS:
                qwen_audio = run_qwen_model(model, config)
                if model == latest.QWEN3_TTS_FLASH_MODEL:
                    clone_reference = normalize_clone_reference(qwen_audio)
            elif model in latest.MINIMAX_AUDIO_MODELS:
                minimax_audio = run_minimax_model(model, config, clone_reference)
                if model in latest.MINIMAX_SPEECH_MODELS:
                    clone_reference = normalize_clone_reference(minimax_audio)
            else:
                run_mureka_model(model, config)
        except Exception as error:
            print(f"{model} FAILED {type(error).__name__}", flush=True)
            raise RuntimeError(f"Live verification failed for {model}") from None


def main() -> None:
    api_key = os.environ.get("SEEDANCE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set SEEDANCE_API_KEY to run paid live verification")
    config = {
        "base_url": "https://api.seedance.nz",
        "api_key": api_key,
        "timeout": 90,
        "upload_timeout": 180,
        "poll_interval": 4,
        "max_poll_time": 2400,
    }
    models = selected_models()
    run_models(models, config)
    print(f"LIVE_CHECKS {len(models)}/{len(models)} SUCCESS", flush=True)


if __name__ == "__main__":
    main()
