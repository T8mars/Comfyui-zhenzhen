"""Bounded original-file downloads and complete animation decoding."""

import io
import os
from pathlib import Path
import time
import uuid

from PIL import Image, ImageSequence
import numpy as np
import torch

try:
    from . import seedance_low_price_nodes as api
    from .media_download import get_media_response, direct_media_get, media_download_timeout
except ImportError:
    import seedance_low_price_nodes as api
    from media_download import get_media_response, direct_media_get, media_download_timeout


def output_target(prefix):
    try:
        import folder_paths
        root = Path(folder_paths.get_output_directory()).resolve()
    except ImportError:
        root = Path(os.environ.get("SEEDANCE_OUTPUT_DIR", "output")).resolve()
    if not isinstance(prefix, str) or not prefix.strip():
        raise api.SeedanceLowPriceError("filename_prefix must not be empty")
    relative = Path(prefix.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts or ":" in prefix:
        raise api.SeedanceLowPriceError("filename_prefix must stay inside the output directory")
    target = (root / relative).resolve()
    if target == root or not target.is_relative_to(root):
        raise api.SeedanceLowPriceError("filename_prefix escapes the output directory")
    return root, target


class ArtifactLimitError(api.SeedanceLowPriceError):
    pass


def download_file(url, prefix, maximum=1024 * 1024 * 1024, inspect=None):
    root, target = output_target(prefix)
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise api.SeedanceLowPriceError("Result URL must be HTTP(S)")
    target.parent.mkdir(parents=True, exist_ok=True)
    destination = target.with_name(target.name + "_" + uuid.uuid4().hex)
    partial = Path(str(destination) + ".part")
    last = None
    for attempt in range(3):
        response = None
        try:
            started = time.monotonic()
            response = get_media_response(url, request_get=api._get_session().get, direct_get=direct_media_get,
                stream=True, timeout=media_download_timeout(300), headers={"User-Agent": "ComfyUI-Zhenzhen/2.0"})
            response.raise_for_status()
            declared = (response.headers or {}).get("Content-Length")
            if declared and int(declared) > maximum:
                raise ArtifactLimitError("Result file exceeds the local download limit")
            size = 0
            with partial.open("wb") as stream:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        size += len(chunk)
                        if size > maximum:
                            raise ArtifactLimitError("Result file exceeds the local download limit")
                        stream.write(chunk)
                    if time.monotonic() - started > 300:
                        raise TimeoutError("Result download exceeded its 300-second attempt limit")
            if not size:
                raise OSError("Result file is empty")
            details = inspect(partial) if inspect else None
            if details is not None:
                extension = details[1]
            else:
                with partial.open("rb") as stream:
                    magic = stream.read(4)
                extension = "glb" if magic == b"glTF" else "zip" if magic[:2] == b"PK" else "bin"
            path = Path(str(destination) + "." + extension)
            os.replace(partial, path)
            entry = {"filename": path.name, "subfolder": path.parent.relative_to(root).as_posix(), "type": "output"}
            if entry["subfolder"] == ".":
                entry["subfolder"] = ""
            return str(path), entry, details
        except ArtifactLimitError:
            raise
        except (api.requests.RequestException, OSError, ValueError) as error:
            last = error
            if attempt < 2:
                time.sleep(2 ** attempt)
        finally:
            partial.unlink(missing_ok=True)
            if response is not None:
                response.close()
    raise api.SeedanceLowPriceError(f"Result download/decode failed after 3 attempts ({type(last).__name__})") from last


def decode_original(data, require_gif=False):
    with Image.open(io.BytesIO(data)) as source:
        format_ = (source.format or "").upper()
        count = getattr(source, "n_frames", 1)
        if require_gif and (format_ != "GIF" or count < 2):
            raise api.SeedanceLowPriceError("GIF mode requires an actual animated GIF; upstream returned a static result")
        extension = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif"}.get(format_)
        if extension is None:
            raise api.SeedanceLowPriceError("Unsupported image result format")
        if source.width * source.height * count > 64 * 1024 * 1024:
            raise ArtifactLimitError("Animation exceeds the local decoded-pixel safety limit")
        frames, durations = [], []
        for frame in ImageSequence.Iterator(source):
            frames.append(torch.from_numpy(np.array(frame.convert("RGB"), dtype=np.float32) / 255.0))
            durations.append(int(frame.info.get("duration", 0)))
        return torch.stack(frames), extension, durations


def download_original(url, prefix, require_gif=False):
    def inspect(path):
        return decode_original(path.read_bytes(), require_gif)
    path, entry, (image, extension, durations) = download_file(url, prefix, 128 * 1024 * 1024, inspect)
    return image, path, entry, durations, extension
