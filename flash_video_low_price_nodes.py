"""Separate Flash protocols for Kling 4 and G Omni 1.2."""

try:
    from . import seedance_low_price_nodes as api
    from . import kling_v4_low_price_nodes as kling
    from .preview_muse_flux_low_price_nodes import references, encode_references
except ImportError:
    import seedance_low_price_nodes as api
    import kling_v4_low_price_nodes as kling
    from preview_muse_flux_low_price_nodes import references, encode_references


KLING_MODEL = "zhenzhen-video-kling-v4-flash"
OMNI_MODEL = "zhenzhen-video-g-omni-1.2-flash-lowprice"
PROFILES = {
    KLING_MODEL: {"seconds": 20, "videos": 5, "resolutions": ["720p"], "ratios": ["16:9", "9:16", "1:1", "21:9"]},
    OMNI_MODEL: {"seconds": 15, "videos": 1, "resolutions": ["360p", "720p", "1080p", "4k"], "ratios": ["16:9", "9:16"]},
}
Error = api.SeedanceLowPriceError


def video_references(model, values):
    maximum = PROFILES[model]["videos"]
    local = []
    for name, value in values.items():
        if name.startswith("video") and name[5:].isdigit() and value is not None:
            index = int(name[5:])
            if not 1 <= index <= maximum:
                raise Error(f"This model supports at most {maximum} reference videos")
            local.append((index, value))
    urls = kling.string_list(values.get("video_urls", ""), "video_urls")
    if any(not kling.http_url(url) for url in urls):
        raise Error("Reference videos require public HTTP(S) URLs")
    if len(local) + len(urls) > maximum:
        raise Error(f"This model supports at most {maximum} reference videos")
    return sorted(local), urls


def validate(model, values, strict=False):
    if model not in PROFILES:
        raise Error("Unsupported Flash video model")
    profile = PROFILES[model]
    prompt = values.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        raise Error("prompt must be text")
    if strict and not (prompt or "").strip():
        raise Error("A non-empty prompt is required")
    seconds = values.get("seconds", 3)
    if type(seconds) is not int or not 3 <= seconds <= profile["seconds"]:
        raise Error(f"Duration must be an integer from 3 to {profile['seconds']} seconds")
    if values.get("resolution", "720p") not in profile["resolutions"]:
        raise Error("Unsupported Flash video resolution")
    if values.get("aspect_ratio", values.get("ratio", "16:9")) not in profile["ratios"]:
        raise Error("Unsupported Flash video aspect ratio")
    images = references(values, 10)
    local, urls = video_references(model, values)
    if images and (local or urls):
        raise Error("Choose image references OR video references, not both")
    for field in ("image_element_ids", "video_element_ids", "voice_ids"):
        value = values.get(field, "")
        if value is None and not strict:
            continue
        if not isinstance(value, str) or value.strip():
            raise Error("Kling Flash does not accept element or voice IDs; disconnect them or select Kling 4 Omni")


def payload(model, values, media):
    validate(model, values, strict=True)
    images, videos = list(media.get("images", [])), list(media.get("videos", []))
    if len(images) > 10 or len(videos) > PROFILES[model]["videos"] or (images and videos):
        raise Error("Unsupported Flash video reference combination")
    # The reference implementation verified that /v1/videos requires string seconds.
    result = {"model": model, "prompt": values["prompt"].strip(), "seconds": str(values.get("seconds", 3)),
              "resolution": values.get("resolution", "720p"),
              "aspect_ratio": values.get("aspect_ratio", values.get("ratio", "16:9"))}
    if images:
        result["images"] = images
    if videos:
        result["metadata"] = {"video_url": videos}
    return result


def prepare_media(model, values):
    validate(model, values, strict=True)
    images = [data for _, data in encode_references(values, 10)]
    local, urls = video_references(model, values)
    videos = []
    for _, video in local:
        data, extension = api.video_to_upload_bytes(video)
        kling.validate_local_video(data, extension)
        videos.append((data, extension))
    return {"images": images, "videos": videos, "video_urls": urls}


def run_task(request, config, progress):
    identifier, submitted = kling.submit_kling_task(request, config, endpoint="videos")
    progress(25)
    final = kling.poll_kling_task(identifier, config, endpoint="videos", on_progress=lambda value: progress(25 + value * .65))
    return identifier, submitted, final


class T8ZhenzhenOmni12FlashLowPrice(kling._Kling4Base):
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    ZHENZHEN_VALIDATE_CONCURRENT_AT_EXECUTION = True

    @classmethod
    def INPUT_TYPES(cls):
        optional = {f"image{i}": ("IMAGE",) for i in range(1, 11)}
        optional.update(video1=(api.VIDEO_TYPE,), video_urls=("STRING", {"default": "", "multiline": True,
            "tooltip": "One public HTTP(S) reference video URL; use instead of video1."}), **kling.config_inputs())
        return {"required": {
            "prompt": ("STRING", {"default": "", "multiline": True}),
            "seconds": ("INT", {"default": 3, "min": 3, "max": 15}),
            "resolution": (PROFILES[OMNI_MODEL]["resolutions"], {"default": "720p"}),
            "aspect_ratio": (PROFILES[OMNI_MODEL]["ratios"], {"default": "16:9"}),
        }, "optional": optional}

    @classmethod
    def validate(cls, values, strict):
        validate(OMNI_MODEL, values, strict)

    def prepare_media(self, values):
        return prepare_media(OMNI_MODEL, values)

    @classmethod
    def build_payload(cls, values, media):
        return payload(OMNI_MODEL, values, media)

    def run_task(self, request, config, progress):
        return run_task(request, config, progress)
