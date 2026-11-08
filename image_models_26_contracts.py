"""Image G 2.6, Krea V3 and Z-image request contracts."""

from urllib.parse import urlparse

try:
    from .seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError
    from .preview_muse_flux_low_price_nodes import references
except ImportError:
    from seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError
    from preview_muse_flux_low_price_nodes import references


G26_MODELS = ["zhenzhen-image-g-v2.6-lowprice", "zhenzhen-image-g-v2.6-flare", "zhenzhen-image-g-v2.6-sunburst"]
G26_LOWPRICE_MAX_REFERENCES = 16
KREA_MODELS = ["krea-v3-t2i", "krea-v3-i2i"]
Z_MODEL = "z-image-t2i"
RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"]
IMAGE_SIZES = ["auto", "1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16", "2:1", "1:2", "21:9", "9:21", "custom"]
KREA_SIZES = {"1:1": (1024, 1024), "16:9": (1536, 864), "9:16": (864, 1536),
              "4:3": (1152, 864), "3:4": (864, 1152), "3:2": (1536, 1024), "2:3": (1024, 1536)}
QUALITIES = ["auto", "low", "medium", "high", "xhigh", "max"]
FRAME_SIZES = ["512x512", "768x512", "512x768", "auto", "custom"]
KREA_MAX_PIXELS = 4220000


def integer(value, low, high=None):
    return isinstance(value, int) and not isinstance(value, bool) and value >= low and (high is None or value <= high)


def http_url(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and parsed.username is None and not any(c.isspace() for c in value)
    except ValueError:
        return False


def validate_basic(kind, kwargs, strict=False):
    prompt = kwargs.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        return "prompt must be text"
    if strict and not (prompt or "").strip():
        return "A non-empty prompt is required | 必须填写提示词"
    seed = kwargs.get("seed", -1)
    if not integer(seed, -1, 9007199254740991 if kind == "z_image" else 2147483647):
        return "Unsupported native seed"
    maximum = 0 if kind == "z_image" else 8
    try:
        refs = references(kwargs, maximum)
    except SeedanceAPIError as exc:
        return str(exc)
    if kind == "z_image":
        return True if kwargs.get("ratio", "1:1") in RATIOS else "Unsupported Z-image ratio"
    model = kwargs.get("model", KREA_MODELS[0])
    if model not in KREA_MODELS:
        return "Unsupported Krea model"
    if model.endswith("-t2i") and refs:
        return "Krea T2I does not accept image references"
    if strict and model.endswith("-i2i") and not refs:
        return "Krea I2I requires 1-8 reference images"
    if kwargs.get("model_variant", "berry") not in ("berry", "jam"):
        return "Unsupported Krea model_variant"
    if kwargs.get("reasoning_level", "low") not in ("low", "medium"):
        return "Unsupported Krea reasoning_level"
    if kwargs.get("output_format", "png") not in ("png", "jpeg"):
        return "Krea output_format must be png or jpeg"
    if not isinstance(kwargs.get("negative_prompt", ""), str):
        return "negative_prompt must be text"
    size = kwargs.get("size", "1:1")
    if size not in (*KREA_SIZES, "custom"):
        return "Unsupported Krea size"
    if size == "custom":
        default = 1024 if strict else None
        width, height = kwargs.get("width", default), kwargs.get("height", default)
        for value in (width, height):
            if (strict or value is not None) and not integer(value, 256, 4096):
                return "Krea dimensions must be integers from 256 to 4096"
        if width is not None and height is not None and width * height > KREA_MAX_PIXELS:
            return "Krea size total pixels must not exceed 4220000"
    return True


def basic_payload(kind, kwargs, images):
    # Uploaded references are checked separately from unresolved input sockets.
    check = dict(kwargs)
    if kind == "krea" and kwargs.get("model", KREA_MODELS[0]).endswith("-i2i") and images:
        check.setdefault("image1", object())
    valid = validate_basic(kind, check, strict=True)
    if valid is not True:
        raise SeedanceAPIError(valid)
    seed = kwargs.get("seed", -1)
    if kind == "z_image":
        if images:
            raise SeedanceAPIError("Z-image does not accept image references")
        result = {"model": Z_MODEL, "prompt": kwargs["prompt"].strip(), "metadata": {"ratio": kwargs.get("ratio", "1:1")}}
        if seed >= 0:
            result["metadata"]["seed"] = seed
        return result
    model = kwargs.get("model", KREA_MODELS[0])
    if len(images) > 8 or (model.endswith("-i2i") and not images) or (model.endswith("-t2i") and images):
        raise SeedanceAPIError("Incorrect Krea reference count")
    size = kwargs.get("size", "1:1")
    width, height = (kwargs.get("width", 1024), kwargs.get("height", 1024)) if size == "custom" else KREA_SIZES[size]
    result = {"model": model, "prompt": kwargs["prompt"].strip(), "size": f"{width}*{height}",
              "metadata": {"model_variant": kwargs.get("model_variant", "berry"), "reasoning_level": kwargs.get("reasoning_level", "low")},
              "output_format": kwargs.get("output_format", "png")}
    if seed >= 0:
        result["seed"] = seed
    if kwargs.get("negative_prompt", "").strip():
        result["negative_prompt"] = kwargs["negative_prompt"].strip()
    if images:
        result["images"] = list(images)
    return result


def gif_dimensions(kwargs):
    size = kwargs.get("frame_size", "512x512")
    if size not in FRAME_SIZES:
        raise SeedanceAPIError("Unsupported GIF frame_size")
    if size == "custom":
        return kwargs.get("frame_width", 512), kwargs.get("frame_height", 512)
    if size == "auto":
        return 512, 512
    return tuple(map(int, size.split("x")))


def validate_g26(kwargs, strict=False):
    model = kwargs.get("model", G26_MODELS[0])
    if model not in G26_MODELS:
        return "Unsupported Image G 2.6 model"
    lowprice = model == G26_MODELS[0]
    mode = kwargs.get("mode", "image")
    if mode not in ("image", "gif"):
        return "Image G 2.6 mode must be image or gif"
    prompt = kwargs.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        return "prompt must be text"
    if strict and not (prompt or "").strip():
        return "A non-empty prompt is required"
    if not lowprice and prompt is not None and len(prompt) > 32000:
        return "Official Image G 2.6 prompt must not exceed 32000 characters"
    try:
        refs = references(kwargs, G26_LOWPRICE_MAX_REFERENCES if lowprice else 16)
    except SeedanceAPIError as exc:
        return str(exc)
    if mode == "gif" and refs:
        return "Image G 2.6 GIF mode is text-only; disconnect image references"
    if lowprice and kwargs.get("resolution", "1k") not in ("1k", "2k", "4k"):
        return "Unsupported resolution"
    if not lowprice and mode == "gif":
        count, duration = kwargs.get("frame_count", 9), kwargs.get("frame_duration_ms", 200)
        if not integer(count, 2, 16):
            return "GIF frame_count must be an integer from 2 to 16"
        if not integer(duration, 20) or duration % 10:
            return "GIF frame_duration_ms must be >=20 and a multiple of 10"
        try:
            width, height = gif_dimensions(kwargs)
        except SeedanceAPIError as exc:
            return str(exc)
        if not strict and kwargs.get("frame_size") == "custom":
            width, height = kwargs.get("frame_width"), kwargs.get("frame_height")
        if any(not integer(value, 16, 3840) or value % 16 for value in (width, height) if strict or value is not None):
            return "GIF dimensions must be positive multiples of 16"
        columns, rows = (4, 2) if count <= 8 else (3, 3) if count == 9 else (4, 3) if count <= 12 else (4, 4)
        fits = False
        for c, r in ((columns, rows), (rows, columns)):
            if width is None or height is None:
                fits = True
                continue
            w, h = width * c, height * r
            fits |= max(w, h) <= 3840 and w * h <= 8294400 and max(w, h) <= min(w, h) * 3
        if not fits:
            return "GIF contact-sheet dimensions exceed the documented limits"
    elif mode == "image":
        size = kwargs.get("size", "1:1")
        if size not in IMAGE_SIZES or (lowprice and size == "custom"):
            return "Unsupported Image G 2.6 size"
        if not lowprice and size == "custom":
            default = 1024 if strict else None
            width, height = kwargs.get("width", default), kwargs.get("height", default)
            for value in (width, height):
                if (strict or value is not None) and (not integer(value, 16, 3840) or value % 16):
                    return "Static dimensions must be multiples of 16, at most 3840"
            if width is not None and height is not None:
                if not 655360 <= width * height <= 8294400 or max(width, height) > 3 * min(width, height):
                    return "Static canvas area or aspect ratio exceeds the documented limits"
        if kwargs.get("output_format", "png") not in ("png", "jpeg", "webp"):
            return "Unsupported static output format"
        if not lowprice:
            if kwargs.get("resolution", "1k") not in ("1k", "2k", "4k"):
                return "Unsupported resolution"
            if not integer(kwargs.get("n", 1), 1, 4):
                return "Static n must be an integer from 1 to 4"
            if kwargs.get("complexity", "api_default") not in ("api_default", "low", "medium", "high"):
                return "Unsupported complexity"
            compression = kwargs.get("output_compression", -1)
            if not integer(compression, -1, 100):
                return "output_compression must be -1 (omit) or 0-100"
    if kwargs.get("quality", "auto") not in QUALITIES:
        return "Unsupported quality"
    mask, markup = kwargs.get("mask_url", ""), kwargs.get("markup_url", "")
    if not lowprice and mode == "image":
        if mask and markup:
            return "mask_url and markup_url are mutually exclusive"
        if any(value and not http_url(value) for value in (mask, markup)):
            return "mask_url and markup_url require public HTTP(S) URLs"
        if strict and (mask or markup) and not any(index == 1 for index, _ in refs):
            return "Mask/markup editing requires image1"
    return True


def g26_payload(kwargs, images):
    check = dict(kwargs)
    if images and not any(value is not None for name, value in check.items() if name.startswith("image") and name[5:].isdigit()):
        check["image1"] = object()
    valid = validate_g26(check, strict=True)
    if valid is not True:
        raise SeedanceAPIError(valid)
    model = kwargs.get("model", G26_MODELS[0])
    lowprice = model == G26_MODELS[0]
    mode = kwargs.get("mode", "image")
    if len(images) > (G26_LOWPRICE_MAX_REFERENCES if lowprice else 16) or (mode == "gif" and images):
        raise SeedanceAPIError("Unsupported reference count for this output mode")
    prompt = kwargs["prompt"].strip()
    if lowprice and mode == "gif":
        prompt += "\nGenerate an animated looping GIF with visible motion and a seamless loop."
    result = {"model": model, "prompt": prompt, "n": 1 if lowprice or mode == "gif" else kwargs.get("n", 1)}
    if lowprice:
        result.update(size="auto" if mode == "gif" else kwargs.get("size", "1:1"),
                      resolution=kwargs.get("resolution", "1k"), quality=kwargs.get("quality", "auto"),
                      output_format="gif" if mode == "gif" else kwargs.get("output_format", "png"))
    else:
        result["quality"] = kwargs.get("quality", "auto")
        if mode == "gif":
            size = kwargs.get("frame_size", "512x512")
            width, height = gif_dimensions(kwargs)
            result.update(output_format="gif", size="auto" if size == "auto" else f"{width}x{height}",
                          frame_count=kwargs.get("frame_count", 9), frame_duration_ms=kwargs.get("frame_duration_ms", 200))
        else:
            size = kwargs.get("size", "1:1")
            result.update(output_format=kwargs.get("output_format", "png"))
            if size == "custom":
                result["size"] = f"{kwargs.get('width', 1024)}x{kwargs.get('height', 1024)}"
            else:
                result.update(size=size, resolution=kwargs.get("resolution", "1k"))
            if kwargs.get("complexity", "api_default") != "api_default":
                result["complexity"] = kwargs["complexity"]
            if result["output_format"] in ("jpeg", "webp") and kwargs.get("output_compression", -1) >= 0:
                result["output_compression"] = kwargs["output_compression"]
            for field in ("mask_url", "markup_url"):
                if kwargs.get(field):
                    result[field] = kwargs[field].strip()
    if images:
        result["images"] = list(images)
    return result

