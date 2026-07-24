# Comfyui-zhenzhen local skill

- Never write API keys, task IDs, signed result URLs, or runtime outputs into committed files or example workflows.
- Example workflows must keep API key fields empty and must not preserve generated results.
- Verify current model contracts against `https://api.seedance.nz/docs/llms.txt` before implementation.
- When a test API key is provided, run real minimal API tests and record only non-secret outcomes.
- Keep low-price additions independent from existing overseas and Seedream request paths unless compatibility requires a shared helper.

## Zhenzhen Image G-2

- Node: `zhenzhen-image-g2-lowprice` / `Comfly_zhenzhen_image_g2_lowprice`.
- Endpoint: `POST /v1/image/generations`; poll with `GET /v1/image/generations/{task_id}`.
- Models: `zhenzhen-image-g2-t2i` and `zhenzhen-image-g2-i2i`.
- `prompt` is required at runtime and supports up to 20000 characters.
- `resolution` supports `1k` only.
- Optional `ratio` is sent as `metadata.ratio`; omit it when set to `adaptive`.
- i2i requires 1-10 uploaded reference image URLs in `images`.
- Do not send `output_format`, `width`, or `height` for G-2.
- Real test on 2026-07-21: both models submitted, reached success, downloaded, and returned ComfyUI `IMAGE` tensors.

## APIMart domestic low-price models

- All nodes in this section use `ZHENZHEN_SEEDANCE2_CONFIG`, base URL `https://api.seedance.nz`, and the domestic signup link.
- Image tasks use `POST /v1/image/generations` and `GET /v1/image/generations/{task_id}`.
- Video tasks use `POST /v1/videos` and `GET /v1/videos/{task_id}`.
- `zhenzhen-image-g-v2-lowprice` supports `resolution=1k|2k|4k`, `n=1..10`, ratio or `WxH` size, and up to 16 optional images.
- `zhenzhen-image-gk-v15` is text-to-image; `zhenzhen-image-gk-v15-edit` requires one image. Both support `n=1..10` and sizes `1:1|16:9|9:16|3:2|2:3`.
- `zhenzhen-video-g-omni-flash` uses fixed `720p`, sends no duration, supports up to 16 images, and accepts either one video URL/input video or `extend_from_task_id`.
- `zhenzhen-video-gk-v15` supports 6-30 seconds, `480p|720p`, ratios `16:9|9:16|1:1|3:2|2:3`, and up to 7 images.
- V3.1 Fast and Quality use fixed 8 seconds, `720p|1080p|4k`, and `16:9|9:16`. Fast accepts up to 3 images; Quality must reject 3-image reference mode.
- `whisper-1` uses synchronous multipart `POST /v1/audio/transcriptions`, not the asynchronous audio generation endpoint. Convert ComfyUI AUDIO to WAV and support `json|verbose_json|srt|text|vtt`.
- Never add APIMart-only parameters to the existing overseas, Seedream, or G-2 payload builders.
