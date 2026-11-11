"""Download Tripo's typed manifest without losing previews or changing formats."""

import json
import os
from pathlib import Path
import struct
import zipfile

try:
    from .tripo_contracts import SeedanceAPIError, http_url
    from .hitem_meshy_contracts import prepare_model
except ImportError:
    from tripo_contracts import SeedanceAPIError, http_url
    from hitem_meshy_contracts import prepare_model


FORMATS = {"glb", "gltf", "fbx", "obj", "stl", "usdz", "3mf", "splat", "zip", "png", "jpg", "jpeg", "webp"}


def result_manifest(final):
    data = final.get("data") if isinstance(final, dict) else None
    nested = data.get("data") if isinstance(data, dict) else None
    content = nested.get("content") if isinstance(nested, dict) else None
    if not isinstance(content, dict):
        raise SeedanceAPIError("Tripo result is missing its typed files manifest")
    files = content.get("files")
    if not isinstance(files, list) or not files:
        raise SeedanceAPIError("Tripo result is missing its typed files manifest")
    items = []
    for file in files:
        if not isinstance(file, dict) or not isinstance(file.get("name"), str) or not http_url(file.get("url")):
            raise SeedanceAPIError("Tripo file entries require name, type and public URL")
        format_ = file.get("type", "")
        if not isinstance(format_, str) or format_.lower() not in FORMATS:
            raise SeedanceAPIError("Tripo returned an unsupported file format")
        items.append({"name": file["name"], "type": format_.lower(), "url": file["url"]})
    main = [item for item in items if item["name"] == "modelUrl"]
    if len(main) != 1 or main[0]["type"] in {"png", "jpg", "jpeg", "webp"}:
        raise SeedanceAPIError("Tripo must return exactly one modelUrl model file")
    # Live responses can expose a different public mirror in result_url.
    # The typed modelUrl role remains authoritative for the model and format.
    if "file_url" in content and content["file_url"] != main[0]["url"]:
        raise SeedanceAPIError("Tripo file_url disagrees with modelUrl")
    if "file_urls" in content and content["file_urls"] != [item["url"] for item in items]:
        raise SeedanceAPIError("Tripo file_urls disagrees with the typed manifest order")
    tripo_id = content.get("tripo_task_id", "")
    if not isinstance(tripo_id, str):
        raise SeedanceAPIError("Tripo task identifier must be text")
    return items, tripo_id


def glb_document(path):
    with Path(path).open("rb") as handle:
        header = handle.read(20)
        if len(header) != 20 or header[:4] != b"glTF":
            raise SeedanceAPIError("Expected a GLB file")
        length, kind = struct.unpack_from("<II", header, 12)
        if kind != 0x4E4F534A or length > 64 * 1024 * 1024:
            raise SeedanceAPIError("Invalid GLB JSON chunk")
        return json.loads(handle.read(length))


def validate_file(path, declared):
    source = Path(path)
    if not source.is_file() or source.stat().st_size == 0:
        raise SeedanceAPIError("Tripo returned an empty file")
    with source.open("rb") as handle:
        header = handle.read(128)
    actual = declared
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            if sum(item.file_size for item in archive.infolist()) > 1024 * 1024 * 1024:
                raise SeedanceAPIError("Tripo archive exceeds the local 1 GiB integrity-check limit")
            if archive.testzip() is not None:
                raise SeedanceAPIError("Tripo archive is corrupt")
        # Preserve archives as archives, never extract or pretend they are meshes.
        actual = declared if declared in ("usdz", "3mf") else "zip"
    elif declared == "glb":
        prepare_model(str(source))
    elif declared == "gltf":
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise SeedanceAPIError("Invalid GLTF JSON") from exc
        if not isinstance(document, dict) or not isinstance(document.get("asset"), dict) or document["asset"].get("version") != "2.0":
            raise SeedanceAPIError("Invalid GLTF asset")
    elif declared == "fbx" and not (header.startswith(b"Kaydara FBX Binary") or b"FBX" in header):
        raise SeedanceAPIError("Tripo FBX file has an invalid header")
    elif declared in ("png", "jpg", "jpeg", "webp"):
        from PIL import Image
        with Image.open(source) as image:
            image.load()
    elif declared == "obj":
        prepare_model(str(source))
    elif declared == "stl":
        binary = False
        if source.stat().st_size >= 84:
            with source.open("rb") as handle:
                handle.seek(80)
                binary = source.stat().st_size == 84 + 50 * struct.unpack("<I", handle.read(4))[0]
        if not binary and not header.lstrip().lower().startswith(b"solid"):
            raise SeedanceAPIError("Tripo STL file has an invalid header")
    elif declared in ("zip", "usdz", "3mf"):
        raise SeedanceAPIError("Tripo archive format did not contain an archive")
    if source.suffix.lower() != "." + actual:
        target = source.with_suffix("." + actual)
        os.replace(source, target)
        source = target
    return str(source), actual


def download_results(final, downloader, prefix="tripo"):
    files, tripo_id = result_manifest(final)
    primary = None
    # Main media must finish before optional preview failures are tolerated.
    ordered = sorted(enumerate(files), key=lambda item: item[1]["name"] != "modelUrl")
    saved = [None] * len(files)
    for index, item in ordered:
        record = dict(item)
        try:
            downloaded = downloader(item["url"], filename_prefix=f"{prefix}_{index}", default_extension=item["type"], logger_prefix="Tripo")
            # The shared downloader guesses from HTTP headers; Tripo's typed manifest is authoritative.
            target = Path(downloaded).with_suffix("." + item["type"])
            if str(target) != downloaded:
                os.replace(downloaded, target)
            path, actual = validate_file(str(target), item["type"])
            record.update(local_path=path, actual_format=actual)
            if item["name"] == "modelUrl":
                primary = record
        except Exception as exc:
            if item["name"] not in ("renderedImageUrl", "generatedImageUrl"):
                raise
            record["download_error"] = type(exc).__name__
        saved[index] = record
    document = glb_document(primary["local_path"]) if primary["actual_format"] == "glb" else {}
    names = list(dict.fromkeys(node["name"] for node in document.get("nodes", [])
                             if isinstance(node, dict) and isinstance(node.get("name"), str) and node["name"]))
    return primary, saved, tripo_id, names
