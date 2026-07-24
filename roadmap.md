# Comfyui-zhenzhen Roadmap

## 2026-07-21 Zhenzhen Image G-2 low-price node

Status: implemented_verified

### Scope

- Add one independent `zhenzhen-image-g2-lowprice` node.
- Support `zhenzhen-image-g2-t2i` text-to-image and `zhenzhen-image-g2-i2i` image editing.
- Reuse `ZHENZHEN_SEEDANCE2_CONFIG` and the existing `https://api.seedance.nz` low-price API path.
- Keep the existing Seedream low-price node and its payload unchanged.
- Add the domestic API key signup button used by other low-price nodes.
- Save one text-to-image workflow and one image-editing workflow with an empty API key.

### API contract

- Submit with `POST /v1/image/generations`; poll with `GET /v1/image/generations/{task_id}`.
- Send `model`, required `prompt`, and `metadata.resolution=1k`.
- Send `metadata.ratio` only when ratio is not `adaptive`.
- For i2i, upload and send 1-10 reference image URLs in `images`.
- Do not send `output_format`, `width`, or `height` for G-2.

### Verification

- Unit-test validation, payloads, image upload, task polling, download outputs, and registration.
- Validate both workflow JSON files, node slots, links, empty API key, and current node defaults.
- Run real minimal t2i and i2i tasks with the user-provided test key and record only non-secret outcomes.
- Run Python compilation, focused tests, frontend link checks, and ComfyUI custom-node loading.

### Result

- Added `Comfly_zhenzhen_image_g2_lowprice` without modifying the existing Seedream node.
- Added text-to-image and image-editing workflows under `workflow/`.
- Unit and workflow tests passed; the paid live test remains opt-in and is skipped by default.
- On 2026-07-21, both G-2 models reached success and downloaded into ComfyUI `IMAGE` tensors in one sequential live test.
- Python compilation, frontend JavaScript syntax, ComfyUI node loading, and global node registration passed.

## 2026-07-25 APIMart low-price image, video, and Whisper nodes

Status: implemented_local_verified

### Scope

- Add six independent domestic low-price nodes using `ZHENZHEN_SEEDANCE2_CONFIG` and `https://api.seedance.nz`.
- Add `zhenzhen-image-g-v2-lowprice` with text-to-image and image-to-image support.
- Add `zhenzhen-video-g-omni-flash` with text/image/video conditioned generation and task continuation.
- Add `zhenzhen-video-gk-v15` with text-to-video and image-to-video support.
- Add one V3.1 node containing `zhenzhen-video-v31-fast` and `zhenzhen-video-v31-quality`.
- Add `whisper-1` synchronous audio transcription.
- Add one GK image node containing `zhenzhen-image-gk-v15` and `zhenzhen-image-gk-v15-edit`.
- Keep existing overseas API, Seedream, G-2, and other low-price payloads unchanged.
- Add the domestic API key signup button to all six nodes.
- Save workflows for every supported text, image, edit, video, continuation, and transcription mode with empty API keys.

### API contract

- Image tasks submit with `POST /v1/image/generations` and poll with `GET /v1/image/generations/{task_id}`.
- `zhenzhen-image-g-v2-lowprice` sends top-level `model`, `prompt`, `n`, and `size`, sends `metadata.resolution` as `1k`, `2k`, or `4k`, and accepts up to 16 uploaded images.
- `zhenzhen-image-gk-v15` and `zhenzhen-image-gk-v15-edit` send top-level `size` and `n`; sizes are `1:1`, `16:9`, `9:16`, `3:2`, or `2:3`; edit requires one image and sends only that image.
- Video tasks submit with `POST /v1/videos` and poll with `GET /v1/videos/{task_id}`.
- `zhenzhen-video-g-omni-flash` accepts prompt and/or up to 16 images, one uploaded/input video URL, or `extend_from_task_id`; video input and task continuation are mutually exclusive; resolution is fixed at `720p`; no duration is sent.
- `zhenzhen-video-gk-v15` accepts up to 7 images, durations from 6 through 30 seconds, `480p` or `720p`, and ratios `16:9`, `9:16`, `1:1`, `3:2`, or `2:3`.
- Both V3.1 models use a fixed 8-second duration, `720p`, `1080p`, or `4k`, and ratios `16:9` or `9:16`; Fast accepts up to 3 images while Quality rejects the 3-image reference mode.
- Whisper sends multipart audio to synchronous `POST /v1/audio/transcriptions` with model `whisper-1` and supports `json`, `verbose_json`, `srt`, `text`, and `vtt` response formats.

### Verification

- Unit-test exact payload construction, parameter rejection, uploads, polling, downloads, multipart transcription, and `skip_error`.
- Validate node registration, display names, domestic API key buttons, and all workflow JSON links and slots.
- Run Python compilation, focused tests, existing G-2 regression tests, frontend JavaScript syntax checks, and ComfyUI custom-node loading.
- Do not store API keys, task IDs, signed URLs, or runtime outputs in source or workflows.

### Result

- Added all six domestic low-price nodes with model-specific validation and payloads matching the 2026-07-25 API document.
- Added synchronous multipart Whisper transcription without introducing a new dependency.
- Added the domestic API key button to all six nodes and kept the existing G-2 behavior.
- Added 16 example workflows covering text/image generation, image editing, video editing, continuation, V3.1 Fast reference mode, and audio transcription.
- Python compilation, frontend JavaScript syntax, 19 unit/workflow tests, existing G-2 regression tests, and ComfyUI normal-entry custom-node loading passed.
- One additional opt-in paid G-2 live test remains skipped by default. No new paid APIMart task was submitted because this request did not provide a current test key.
