"""Documented Hitem3D and available Meshy 6 image generation contracts."""

import json
import os
from pathlib import Path
import shutil
import struct
import zipfile

try:
    from .seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError
except ImportError:
    from seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError


HITEM_MODELS = ["hitem3d-v2-image-to-3d", "hitem3d-v2-multi-image-to-3d"]
PORTRAIT_MODELS = ["hitem3d-portrait-v2.1-image-to-3d", "hitem3d-portrait-v2.1-multi-image-to-3d"]
MESHY_MODELS = ["meshy-6-global-image-to-3d"]
VIEWS = ["front", "back", "left", "right"]
BOOLEAN_FIELDS = ("should_remesh", "enable_pbr", "ta_pose", "should_texture")
OPTIONAL_BOOLEAN = ["api_default", "true", "false"]


def models(family):
    return {"hitem": HITEM_MODELS, "portrait": PORTRAIT_MODELS, "meshy": MESHY_MODELS}[family]


def integer(value, lower, upper):
    return isinstance(value, int) and not isinstance(value, bool) and lower <= value <= upper


def image_slots(kwargs):
    slots = []
    for key, value in kwargs.items():
        if key.startswith("image") and key[5:].isdigit() and value is not None:
            index = int(key[5:])
            if index < 1 or index > 4:
                raise SeedanceAPIError("Only image1..image4 are supported")
            slots.append(index)
    return sorted(slots)


def validate(family, kwargs, strict=False):
    model = kwargs.get("model", models(family)[0])
    if model not in models(family):
        return "Unsupported or unavailable 3D model"
    if family == "meshy":
        for name, values in (("topology", ["api_default", "triangle", "quad"]),
                             ("symmetry_mode", ["api_default", "off", "auto", "on"])):
            if kwargs.get(name, "api_default") not in values:
                return f"Unsupported Meshy {name}"
        count = kwargs.get("target_polycount", 0)
        if not integer(count, 0, 300000) or 0 < count < 100:
            return "target_polycount must be 0 (API default) or an integer from 100 to 300000"
        for name in BOOLEAN_FIELDS:
            if kwargs.get(name, "api_default") not in OPTIONAL_BOOLEAN:
                return f"{name} must be api_default, true or false"
    else:
        if kwargs.get("request_type", "both") not in ("mesh", "both"):
            return "request_type must be mesh or both"
        resolutions = ["1536pro"] if family == "portrait" else ["1536", "1536pro"]
        if kwargs.get("resolution", resolutions[0]) not in resolutions:
            return "Unsupported Hitem3D resolution"
        if not integer(kwargs.get("face", 1000000), 100000, 2000000):
            return "face must be an integer from 100000 to 2000000"
    try:
        slots = image_slots(kwargs)
    except SeedanceAPIError as exc:
        return str(exc)
    if strict:
        multi = "multi-image" in model
        if multi and not 2 <= len(slots) <= 4:
            return "Multi-image generation requires 2-4 views: front, back, left, right"
        if not multi and slots != [1]:
            return "Single-image generation requires exactly image1"
        if slots != list(range(1, len(slots) + 1)):
            return "Connect views contiguously: image1 front, image2 back, image3 left, image4 right"
    return True


def payload(family, kwargs, images):
    valid = validate(family, kwargs)
    if valid is not True:
        raise SeedanceAPIError(valid)
    model = kwargs.get("model", models(family)[0])
    multi = "multi-image" in model
    if not (2 <= len(images) <= 4 if multi else len(images) == 1):
        raise SeedanceAPIError("Incorrect reference image count for the selected 3D model")
    result = {"model": model, "images": list(images)}
    if family == "meshy":
        for name in ("topology", "symmetry_mode", *BOOLEAN_FIELDS):
            value = kwargs.get(name, "api_default")
            if value != "api_default":
                result[name] = value == "true" if name in BOOLEAN_FIELDS else value
        if kwargs.get("target_polycount", 0):
            result["target_polycount"] = kwargs["target_polycount"]
    else:
        result.update(request_type=kwargs.get("request_type", "both"),
                      resolution=kwargs.get("resolution", "1536pro" if family == "portrait" else "1536"),
                      face=kwargs.get("face", 1000000))
    return result


def prepare_model(path):
    """Recognize actual file bytes; never relabel a ZIP response as a GLB."""
    source = Path(path)
    with source.open("rb") as handle:
        header = handle.read(12)
    if header[:4] == b"glTF":
        if len(header) != 12 or struct.unpack_from("<II", header, 4) != (2, source.stat().st_size):
            raise SeedanceAPIError("Downloaded GLB is invalid or incomplete")
        with source.open("rb") as handle:
            handle.seek(12)
            chunk = handle.read(8)
            if len(chunk) != 8:
                raise SeedanceAPIError("Downloaded GLB has no JSON chunk")
            length, kind = struct.unpack("<II", chunk)
            if kind != 0x4E4F534A or length > min(source.stat().st_size - 20, 64 * 1024 * 1024):
                raise SeedanceAPIError("Downloaded GLB JSON chunk is invalid")
            try:
                document = json.loads(handle.read(length))
            except (ValueError, UnicodeError) as exc:
                raise SeedanceAPIError("Downloaded GLB JSON is invalid") from exc
            asset = document.get("asset") if isinstance(document, dict) else None
            if not isinstance(asset, dict) or asset.get("version") != "2.0":
                raise SeedanceAPIError("Downloaded GLB asset is invalid")
        return str(source), "glb"
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            entries = [info for info in archive.infolist() if not info.is_dir() and info.filename.lower().endswith(".glb")]
            if not entries:
                raise SeedanceAPIError("3D archive contains no self-contained GLB model; the original archive remains on disk")
            entry = entries[0]
            if entry.file_size > 1024 * 1024 * 1024 or entry.flag_bits & 1:
                raise SeedanceAPIError("3D archive member is too large or encrypted")
            # A self-contained GLB is written under our generated basename, not an archive path.
            target = source.with_name(source.stem + "_model.glb")
            partial = target.with_suffix(".glb.part")
            try:
                with archive.open(entry) as reader, partial.open("wb") as writer:
                    shutil.copyfileobj(reader, writer)
                if partial.stat().st_size != entry.file_size:
                    raise SeedanceAPIError("Extracted GLB is incomplete")
                prepare_model(str(partial))
                os.replace(partial, target)
                return str(target), "glb"
            finally:
                if partial.exists():
                    partial.unlink()
    extension = source.suffix.lower().lstrip(".")
    if extension == "obj":
        with source.open("r", encoding="utf-8", errors="replace") as handle:
            has_vertices = has_faces = False
            for line in handle:
                has_vertices |= line.startswith("v ")
                has_faces |= line.startswith("f ")
                if has_vertices and has_faces:
                    return str(source), "obj"
    raise SeedanceAPIError("The downloaded result is not a supported, valid GLB or OBJ model")

