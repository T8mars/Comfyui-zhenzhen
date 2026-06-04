import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from io import BytesIO

import cv2
import comfy.utils
import requests
import torch
from PIL import Image
from comfy.comfy_types import IO

from .utils import pil2tensor, tensor2pil


baseurl = "https://ai.t8star.org"
FAL_SEED_MAX = 65535


def get_config():
    try:
        config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "Comflyapi.json")
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(config):
    config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "Comflyapi.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)


class FalVideoAdapter:
    def __init__(self, video_path_or_url):
        if video_path_or_url and str(video_path_or_url).startswith("http"):
            self.is_url = True
            self.video_url = video_path_or_url
            self.video_path = None
        else:
            self.is_url = False
            self.video_path = video_path_or_url
            self.video_url = None

    def get_dimensions(self):
        if self.is_url:
            return 1280, 720
        try:
            cap = cv2.VideoCapture(self.video_path)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            return width or 1280, height or 720
        except Exception:
            return 1280, 720

    def save_to(self, output_path, format="auto", codec="auto", metadata=None):
        if self.is_url:
            try:
                response = requests.get(self.video_url, stream=True, timeout=300)
                response.raise_for_status()
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
            except Exception as e:
                print(f"[fal_video_adapter] Error downloading video: {e}")
                return False
        try:
            shutil.copyfile(self.video_path, output_path)
            return True
        except Exception as e:
            print(f"[fal_video_adapter] Error saving video: {e}")
            return False


class ComflyFalBase:
    FAL_BASE = f"{baseurl}/fal"
    LOG_PREFIX = "fal"
    DEFAULT_POLL_INTERVAL = 6
    DEFAULT_MAX_POLL_ATTEMPTS = 600
    FAL_SEED_MAX = FAL_SEED_MAX
    PENDING_STATUSES = {"IN_QUEUE", "IN_PROGRESS"}
    COMPLETED_STATUSES = {"COMPLETED", "COMPLETE", "DONE"}
    FAILED_STATUSES = {"FAILED", "FAILURE", "ERROR", "CANCELLED", "CANCELED"}

    def __init__(self):
        self.api_key = get_config().get("api_key", "")
        self.timeout = 300

    def set_api_key(self, api_key):
        if api_key and str(api_key).strip():
            self.api_key = str(api_key).strip()
            config = get_config()
            config["api_key"] = self.api_key
            save_config(config)

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _log(self, message):
        print(f"[{self.LOG_PREFIX}] {message}")

    def normalize_seed(self, seed, random_value=0):
        try:
            seed_value = int(seed)
        except (TypeError, ValueError):
            return random_value
        if seed_value <= 0:
            return random_value
        return min(seed_value, self.FAL_SEED_MAX)

    def seed_payload_value(self, seed):
        seed_value = self.normalize_seed(seed, 0)
        return seed_value if seed_value > 0 else None

    def blank_image(self, width=1024, height=1024):
        return pil2tensor(Image.new("RGB", (width, height), color="white"))

    def fix_fal_url(self, url):
        if not url:
            return ""
        return (
            str(url)
            .replace("https://queue.fal.run", self.FAL_BASE)
            .replace("https://fal.run", self.FAL_BASE)
        )

    def image_to_base64(self, image_tensor):
        if image_tensor is None:
            return None
        pil_image = tensor2pil(image_tensor)[0]
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        base64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{base64_str}"

    def upload_image_to_get_url(self, image_tensor):
        if image_tensor is None:
            return None
        try:
            pil_image = tensor2pil(image_tensor)[0]
            buffered = BytesIO()
            pil_image.save(buffered, format="PNG")
            files = {"file": ("image.png", buffered.getvalue(), "image/png")}
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = requests.post(f"{baseurl}/v1/files", headers=headers, files=files, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            if "url" in result:
                return result["url"]
            self._log(f"Unexpected file upload response: {result}")
        except Exception as e:
            self._log(f"Error uploading image: {str(e)}")
        return None

    def upload_bytes_to_get_url(self, file_bytes, filename="file.bin", content_type=None):
        if not file_bytes:
            return None
        try:
            guessed_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
            files = {"file": (filename, file_bytes, guessed_type)}
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = requests.post(f"{baseurl}/v1/files", headers=headers, files=files, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            if "url" in result:
                return result["url"]
            self._log(f"Unexpected file upload response: {result}")
        except Exception as e:
            self._log(f"Error uploading file: {str(e)}")
        return None

    def prepare_image(self, image_tensor=None, image_url="", image_way="base64"):
        if image_tensor is not None:
            return self.image_to_base64(image_tensor) if image_way == "base64" else self.upload_image_to_get_url(image_tensor)
        if image_url and str(image_url).strip():
            return str(image_url).strip()
        return ""

    def _direct_url_from_media(self, media_input):
        if media_input is None:
            return ""
        if isinstance(media_input, str) and media_input.strip().startswith(("http://", "https://")):
            return media_input.strip()
        for attr in ("video_url", "url"):
            value = getattr(media_input, attr, "")
            if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
                return value.strip()
        if isinstance(media_input, dict):
            for key in ("video_url", "url"):
                value = media_input.get(key)
                if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
                    return value.strip()
        return ""

    def media_to_bytes(self, media_input, bytesio_ext=".mp4", label="media"):
        if media_input is None:
            return None, None

        get_stream = getattr(media_input, "get_stream_source", None)
        if callable(get_stream):
            try:
                source = media_input.get_stream_source()
                if isinstance(source, str):
                    source = source.strip()
                    if source and os.path.isfile(source):
                        with open(source, "rb") as f:
                            return f.read(), os.path.basename(source)
                    if source:
                        self._log(f"{label}: path not found on disk: {source}")
                    return None, None
                if isinstance(source, BytesIO):
                    source.seek(0)
                    data = source.read()
                    if data:
                        return data, f"reference_{label}_{abs(hash(data)) % 10**10}{bytesio_ext}"
                    return None, None
                if hasattr(source, "read"):
                    if hasattr(source, "seek"):
                        source.seek(0)
                    data = source.read()
                    if data:
                        return data, f"reference_{label}_{abs(hash(data)) % 10**10}{bytesio_ext}"
                    return None, None
            except Exception as e:
                self._log(f"{label}: get_stream_source() failed: {e}")

        if isinstance(media_input, str):
            path = media_input.strip()
            if path and os.path.isfile(path):
                with open(path, "rb") as f:
                    return f.read(), os.path.basename(path)
            return None, None

        if isinstance(media_input, dict):
            path = (
                media_input.get("path")
                or media_input.get("file")
                or media_input.get("file_path")
                or media_input.get("filename")
                or ""
            )
            path = str(path).strip() if path else ""
            if path and os.path.isfile(path):
                with open(path, "rb") as f:
                    return f.read(), os.path.basename(path)
            return None, None

        for attr in ("path", "file_path"):
            path = getattr(media_input, attr, None)
            if isinstance(path, str) and path.strip() and os.path.isfile(path.strip()):
                with open(path.strip(), "rb") as f:
                    return f.read(), os.path.basename(path.strip())

        self._log(f"Could not read bytes for {label} from type {type(media_input).__name__}")
        return None, None

    def prepare_video(self, video_input=None, video_url="", video_way="upload"):
        explicit_url = str(video_url or "").strip()
        if video_way == "video_url" and explicit_url:
            return explicit_url
        direct_url = self._direct_url_from_media(video_input)
        if direct_url:
            return direct_url
        file_bytes, filename = self.media_to_bytes(video_input, ".mp4", "video")
        if file_bytes:
            return self.upload_bytes_to_get_url(file_bytes, filename or "video.mp4", mimetypes.guess_type(filename or "")[0] or "video/mp4")
        if explicit_url:
            return explicit_url
        return ""

    def blank_audio(self, sample_rate=44100, duration_seconds=1):
        return {
            "waveform": torch.zeros((1, 1, int(sample_rate * duration_seconds))),
            "sample_rate": sample_rate,
        }

    def audio_url_to_audio_object(self, audio_url):
        if not audio_url:
            return self.blank_audio()
        try:
            import torchaudio
            try:
                import folder_paths
                temp_root = folder_paths.get_temp_directory()
            except Exception:
                temp_root = tempfile.gettempdir()
            temp_dir = os.path.join(temp_root, "fal_audio")
            os.makedirs(temp_dir, exist_ok=True)
            url_path = str(audio_url).split("?", 1)[0]
            ext = os.path.splitext(url_path)[1] or ".m4a"
            temp_file = os.path.join(temp_dir, f"fal_{str(uuid.uuid4())[:8]}{ext}")
            response = requests.get(audio_url, stream=True, timeout=self.timeout)
            response.raise_for_status()
            with open(temp_file, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            try:
                waveform, sample_rate = torchaudio.load(temp_file)
                if len(waveform.shape) == 2:
                    waveform = waveform.unsqueeze(0)
                return {"waveform": waveform, "sample_rate": sample_rate, "url": audio_url}
            except Exception as e:
                self._log(f"Error loading audio with torchaudio: {e}")
                ffmpeg_path = shutil.which("ffmpeg")
                try:
                    import folder_paths
                    if hasattr(folder_paths, "get_ffmpeg_path"):
                        ffmpeg_path = folder_paths.get_ffmpeg_path() or ffmpeg_path
                except Exception:
                    pass
                if ffmpeg_path:
                    temp_wav = os.path.splitext(temp_file)[0] + ".wav"
                    subprocess.run([ffmpeg_path, "-y", "-i", temp_file, temp_wav], check=True, capture_output=True)
                    waveform, sample_rate = torchaudio.load(temp_wav)
                    if len(waveform.shape) == 2:
                        waveform = waveform.unsqueeze(0)
                    try:
                        os.remove(temp_wav)
                    except Exception:
                        pass
                    return {"waveform": waveform, "sample_rate": sample_rate, "url": audio_url}
                self._log("ffmpeg not found, returning blank AUDIO with url metadata")
        except Exception as e:
            self._log(f"Error downloading or processing audio: {e}")
        audio = self.blank_audio()
        audio["url"] = audio_url
        return audio

    def _parse_json_response(self, response):
        try:
            return response.json()
        except Exception:
            raise RuntimeError(f"Non-JSON response: {response.text[:500]}")

    def _status_value(self, data):
        if not isinstance(data, dict):
            return ""
        status = data.get("status", "")
        return str(status).strip().upper() if status is not None else ""

    def _format_error_value(self, value):
        if isinstance(value, list):
            return "; ".join(self._format_error_value(item) for item in value[:3])
        if isinstance(value, dict):
            message = (
                value.get("msg")
                or value.get("message")
                or value.get("detail")
                or value.get("error")
                or value.get("reason")
            )
            parts = []
            if value.get("type"):
                parts.append(str(value["type"]))
            if value.get("loc"):
                loc = value["loc"]
                if isinstance(loc, (list, tuple)):
                    loc = ".".join(str(item) for item in loc)
                parts.append(str(loc))
            if message:
                prefix = " / ".join(parts)
                return f"{prefix}: {message}" if prefix else str(message)
            return json.dumps(value, ensure_ascii=False)[:800]
        return str(value)

    def _extract_error_message(self, data):
        if isinstance(data, list):
            return self._format_error_value(data)
        if not isinstance(data, dict):
            return str(data)

        messages = []
        for key in ("failure_details", "detail", "error", "errors", "failure_reason", "message", "msg"):
            value = data.get(key)
            if value not in (None, "", [], {}):
                messages.append(self._format_error_value(value))

        nested = data.get("data")
        if not messages and isinstance(nested, (dict, list)):
            nested_message = self._extract_error_message(nested)
            if nested_message:
                messages.append(nested_message)

        return "; ".join(messages) if messages else json.dumps(data, ensure_ascii=False)[:800]

    def _raise_for_error_payload(self, data, context="API Error"):
        if isinstance(data, list):
            raise RuntimeError(f"{context}: {self._extract_error_message(data)}")
        if not isinstance(data, dict):
            return

        status = self._status_value(data)
        if status in self.PENDING_STATUSES:
            return
        if status in self.FAILED_STATUSES:
            raise RuntimeError(f"Task {status}: {self._extract_error_message(data)}")

        for key in ("failure_details", "detail", "error", "errors"):
            if data.get(key) not in (None, "", [], {}):
                raise RuntimeError(f"{context}: {self._extract_error_message(data)}")

    def _json_from_text(self, text):
        body = str(text or "").strip()
        if not body or not body.startswith(("{", "[")):
            return None
        try:
            return json.loads(body)
        except Exception:
            return None

    def _raise_for_http_error(self, response, context="API error"):
        body = response.text[:800]
        body_json = self._json_from_text(body)
        if body_json is not None:
            status = self._status_value(body_json)
            if status in self.PENDING_STATUSES:
                return
            self._raise_for_error_payload(body_json, f"{context} (HTTP {response.status_code})")
        raise RuntimeError(f"{context} (HTTP {response.status_code}): {body[:500]}")

    def _has_output(self, data, output_keys):
        return self._find_output_data(data, output_keys) is not None

    def _find_output_data(self, data, output_keys):
        if not isinstance(data, dict):
            return None
        if any(bool(data.get(key)) for key in output_keys):
            return data
        nested = data.get("data")
        if isinstance(nested, dict):
            return self._find_output_data(nested, output_keys)
        return None

    def submit_and_poll(self, endpoint, payload, output_keys, pbar=None, poll_interval=6, max_poll_attempts=600):
        api_url = f"{self.FAL_BASE}/{endpoint}"
        self._log(f"Submitting to {api_url}")
        response = requests.post(api_url, headers=self.get_headers(), json=payload, timeout=self.timeout)
        if response.status_code != 200:
            self._raise_for_http_error(response, "API Error")

        result = self._parse_json_response(response)
        self._raise_for_error_payload(result, "API Error")

        if pbar:
            pbar.update_absolute(30)
        output_data = self._find_output_data(result, output_keys)
        if output_data is not None:
            return output_data

        request_id = result.get("request_id")
        if not request_id:
            raise RuntimeError(f"No request_id in response: {str(result)[:500]}")

        response_url = self.fix_fal_url(result.get("response_url", ""))
        status_url = self.fix_fal_url(result.get("status_url", ""))
        if not response_url:
            response_url = f"{self.FAL_BASE}/{endpoint}/requests/{request_id}"
        if not status_url:
            status_url = f"{response_url}/status"

        self._log(f"Queued, request_id={request_id}, polling (timeout={poll_interval * max_poll_attempts}s)...")

        for attempt in range(max_poll_attempts):
            if pbar:
                pbar.update_absolute(30 + min(65, int((attempt + 1) / max_poll_attempts * 65)))
            time.sleep(poll_interval)

            try:
                poll_resp = requests.get(status_url or response_url, headers=self.get_headers(), timeout=self.timeout)
                if poll_resp.status_code != 200:
                    body_json = self._json_from_text(poll_resp.text[:800])
                    body_status = self._status_value(body_json)
                    if body_status in self.PENDING_STATUSES:
                        if attempt % 10 == 0:
                            self._log(f"Poll #{attempt+1}: HTTP {poll_resp.status_code}, status={body_status} (waiting)")
                        continue
                    self._raise_for_http_error(poll_resp, "API error")

                poll_data = self._parse_json_response(poll_resp)
                self._raise_for_error_payload(poll_data, "API Error")
                output_data = self._find_output_data(poll_data, output_keys)
                if output_data is not None:
                    return output_data

                status = self._status_value(poll_data)
                if status in self.COMPLETED_STATUSES:
                    result_resp = requests.get(response_url, headers=self.get_headers(), timeout=self.timeout)
                    if result_resp.status_code != 200:
                        body_status = self._status_value(self._json_from_text(result_resp.text[:800]))
                        if body_status in self.PENDING_STATUSES:
                            continue
                        self._raise_for_http_error(result_resp, "API error")
                    result_payload = self._parse_json_response(result_resp)
                    self._raise_for_error_payload(result_payload, "API Error")
                    output_data = self._find_output_data(result_payload, output_keys)
                    if output_data is not None:
                        return output_data
                if attempt % 10 == 0:
                    self._log(f"Polling... attempt {attempt+1}/{max_poll_attempts}, status={status or 'UNKNOWN'}")
            except requests.exceptions.RequestException as e:
                self._log(f"Poll error: {e}")
                continue

        raise RuntimeError(f"Timeout: no result after {max_poll_attempts * poll_interval}s")

    def collect_file_urls(self, value):
        urls = []
        if isinstance(value, dict):
            url = value.get("url")
            if isinstance(url, str) and url:
                urls.append(url)
            for child in value.values():
                urls.extend(self.collect_file_urls(child))
        elif isinstance(value, list):
            for item in value:
                urls.extend(self.collect_file_urls(item))
        return urls

    def extract_image_urls(self, result):
        urls = []
        if isinstance(result, dict):
            for key in ("images", "image", "output", "files"):
                urls.extend(self.collect_file_urls(result.get(key)))
            if isinstance(result.get("data"), dict):
                urls.extend(self.extract_image_urls(result["data"]))
        return list(dict.fromkeys([u for u in urls if u]))

    def download_images(self, urls):
        tensors = []
        for idx, url in enumerate(urls):
            try:
                if str(url).startswith("data:image"):
                    pil_img = Image.open(BytesIO(base64.b64decode(str(url).split(",", 1)[-1]))).convert("RGB")
                else:
                    img_resp = requests.get(url, timeout=self.timeout)
                    img_resp.raise_for_status()
                    pil_img = Image.open(BytesIO(img_resp.content)).convert("RGB")
                tensors.append(pil2tensor(pil_img))
                self._log(f"Downloaded image {idx+1}/{len(urls)}")
            except Exception as e:
                self._log(f"Error downloading image {idx+1}: {e}")
        if not tensors:
            raise RuntimeError("Failed to download any result images")
        return torch.cat(tensors, dim=0)

    def extract_video_url(self, result):
        if not isinstance(result, dict):
            return ""
        if isinstance(result.get("data"), dict):
            nested_url = self.extract_video_url(result["data"])
            if nested_url:
                return nested_url
        video = result.get("video")
        if isinstance(video, dict) and video.get("url"):
            return video["url"]
        urls = self.collect_file_urls(video)
        if urls:
            return urls[0]
        for key in ("video_url", "url"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
        return ""

    def extract_audio_urls(self, result):
        urls = []
        if isinstance(result, dict):
            if isinstance(result.get("data"), dict):
                urls.extend(self.extract_audio_urls(result["data"]))
            for key in ("audios", "audio", "output", "files"):
                urls.extend(self.collect_file_urls(result.get(key)))
            for key in ("audio_url", "url"):
                value = result.get(key)
                if isinstance(value, str) and value:
                    urls.append(value)
        return list(dict.fromkeys([u for u in urls if u]))

    def extract_model_urls(self, result):
        urls = []
        if isinstance(result, dict):
            for key in ("model_mesh", "model_meshes", "textures", "files", "output"):
                urls.extend(self.collect_file_urls(result.get(key)))
        return list(dict.fromkeys([u for u in urls if u]))

    def choose_model_url(self, urls, preferred_format=""):
        if not urls:
            return ""
        preferred = str(preferred_format or "").lstrip(".").lower()
        if preferred:
            for url in urls:
                url_path = str(url).split("?", 1)[0].lower()
                if url_path.endswith(f".{preferred}"):
                    return url
        model_exts = (".glb", ".gltf", ".obj", ".fbx", ".stl", ".usdz")
        for url in urls:
            url_path = str(url).split("?", 1)[0].lower()
            if url_path.endswith(model_exts):
                return url
        return urls[0]

    def url_to_file_3d(self, model_url, file_format=""):
        if not model_url:
            return None
        file_3d_class = self.get_file_3d_class()

        file_format = str(file_format or "").lstrip(".").lower()
        if not file_format:
            url_path = str(model_url).split("?", 1)[0]
            file_format = os.path.splitext(url_path)[1].lstrip(".").lower() or "glb"

        data = BytesIO()
        response = requests.get(model_url, stream=True, timeout=self.timeout)
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                data.write(chunk)
        data.seek(0)
        return file_3d_class(source=data, file_format=file_format)

    def get_file_3d_class(self):
        save_3d = sys.modules.get("comfy_extras.nodes_save_3d")
        types_obj = getattr(save_3d, "Types", None)
        file_3d_class = getattr(types_obj, "File3D", None)
        if file_3d_class is not None:
            return file_3d_class

        from comfy_api.latest import Types
        return Types.File3D

    def info(self, data):
        return json.dumps(data, ensure_ascii=False, indent=2)


class Comfly_ideogram_v4_fal(ComflyFalBase):
    LOG_PREFIX = "ideogram_v4_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": ""})}, "optional": {
            "api_key": ("STRING", {"default": ""}),
            "image_size": (["square_hd", "square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"], {"default": "square_hd"}),
            "rendering_speed": (["TURBO", "BALANCED", "QUALITY"], {"default": "BALANCED"}),
            "acceleration": (["none", "low", "regular", "high"], {"default": "none"}),
            "num_images": ("INT", {"default": 1, "min": 1, "max": 4}),
            "seed": ("INT", {"default": 0, "min": 0, "max": FAL_SEED_MAX, "tooltip": "0 = random seed. FAL seed max is 65535."}),
            "output_format": (["jpeg", "png"], {"default": "jpeg"}),
            "enable_prompt_expansion": ("BOOLEAN", {"default": True}),
            "enable_safety_checker": ("BOOLEAN", {"default": True}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("images", "response", "image_urls")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"

    def process(self, prompt, api_key="", image_size="square_hd", rendering_speed="BALANCED",
                acceleration="none", num_images=1, seed=0, output_format="jpeg",
                enable_prompt_expansion=True, enable_safety_checker=True,
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        seed_value = self.seed_payload_value(seed)
        return _run_image_node(
            self, "ideogram/v4", prompt, api_key, skip_error,
            {
                "image_size": image_size,
                "rendering_speed": rendering_speed,
                "acceleration": acceleration,
                "num_images": num_images,
                "output_format": output_format,
                "enable_prompt_expansion": enable_prompt_expansion,
                "enable_safety_checker": enable_safety_checker,
                **({"seed": seed_value} if seed_value is not None else {}),
            },
            poll_interval, max_poll_attempts
        )


class Comfly_mai_image_2_5_fal(ComflyFalBase):
    LOG_PREFIX = "mai_image_2_5_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": ""})}, "optional": {
            "api_key": ("STRING", {"default": ""}),
            "aspect_ratio": (["auto", "1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3"], {"default": "auto"}),
            "num_images": ("INT", {"default": 1, "min": 1, "max": 4}),
            "output_format": (["png", "jpeg", "webp"], {"default": "png"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("images", "response", "image_urls")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"

    def process(self, prompt, api_key="", aspect_ratio="auto", num_images=1, output_format="png",
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        return _run_image_node(
            self, "microsoft/mai-image-2.5", prompt, api_key, skip_error,
            {"aspect_ratio": aspect_ratio, "num_images": num_images, "output_format": output_format},
            poll_interval, max_poll_attempts
        )


class Comfly_cosmos_3_super_fal(ComflyFalBase):
    LOG_PREFIX = "cosmos_3_super_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": ""})}, "optional": {
            "mode": (["text_to_image", "image_to_video"], {"default": "text_to_image"}),
            "image": ("IMAGE",),
            "image_url": ("STRING", {"default": ""}),
            "api_key": ("STRING", {"default": ""}),
            "negative_prompt": ("STRING", {"default": "", "multiline": True}),
            "image_size": (["square_hd", "square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9", "custom_832x480"], {"default": "square_hd"}),
            "num_images": ("INT", {"default": 1, "min": 1, "max": 4}),
            "num_frames": ("INT", {"default": 49, "min": 25, "max": 189, "step": 1}),
            "frames_per_second": ("INT", {"default": 24, "min": 8, "max": 30, "step": 1}),
            "num_inference_steps": ("INT", {"default": 28, "min": 1, "max": 50, "step": 1}),
            "guidance_scale": ("FLOAT", {"default": 4.0, "min": 0.0, "max": 20.0, "step": 0.1}),
            "enable_prompt_expansion": ("BOOLEAN", {"default": False}),
            "enable_agentic_generation": ("BOOLEAN", {"default": False}),
            "enable_safety_checker": ("BOOLEAN", {"default": True}),
            "seed": ("INT", {"default": 0, "min": 0, "max": FAL_SEED_MAX, "tooltip": "0 = random seed. FAL seed max is 65535."}),
            "output_format": (["jpeg", "png"], {"default": "jpeg"}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("IMAGE", IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("images", "video", "response", "url")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def _image_size_value(self, image_size):
        return {"width": 832, "height": 480} if image_size == "custom_832x480" else image_size

    def process(self, prompt, mode="text_to_image", image=None, image_url="", api_key="",
                negative_prompt="", image_size="square_hd", num_images=1, num_frames=49,
                frames_per_second=24, num_inference_steps=28, guidance_scale=4.0,
                enable_prompt_expansion=False, enable_agentic_generation=False,
                enable_safety_checker=True, seed=0, output_format="jpeg", image_way="base64",
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        default_image = self.blank_image()
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            payload = {
                "prompt": prompt,
                "image_size": self._image_size_value(image_size),
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "enable_prompt_expansion": enable_prompt_expansion,
                "enable_agentic_generation": enable_agentic_generation,
                "enable_safety_checker": enable_safety_checker,
            }
            if negative_prompt.strip():
                payload["negative_prompt"] = negative_prompt
            seed_value = self.seed_payload_value(seed)
            if seed_value is not None:
                payload["seed"] = seed_value
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            if mode == "image_to_video":
                prepared_image = self.prepare_image(image, image_url, image_way)
                if not prepared_image:
                    raise RuntimeError("image_to_video mode requires image or image_url.")
                payload.update({"image_url": prepared_image, "num_frames": num_frames, "frames_per_second": frames_per_second})
                result = self.submit_and_poll("nvidia/cosmos-3-super/image-to-video", payload, ["video"], pbar, poll_interval, max_poll_attempts)
                video_url = self.extract_video_url(result)
                if not video_url:
                    raise RuntimeError("No video URL in result")
                pbar.update_absolute(100)
                return (default_image, FalVideoAdapter(video_url), self.info(result), video_url)
            payload.update({"num_images": num_images, "output_format": output_format})
            result = self.submit_and_poll("nvidia/cosmos-3-super/text-to-image", payload, ["images"], pbar, poll_interval, max_poll_attempts)
            urls = self.extract_image_urls(result)
            images = self.download_images(urls)
            pbar.update_absolute(100)
            return (images, "", self.info(result), "\n".join(urls))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return (default_image, "", error_message, "")


class Comfly_hyper3d_rodin_v2_5_fal(ComflyFalBase):
    LOG_PREFIX = "hyper3d_rodin_v2_5_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": ""})}, "optional": {
            "mode": (["text_to_3d", "image_to_3d"], {"default": "text_to_3d"}),
            "image1": ("IMAGE",),
            "image2": ("IMAGE",),
            "image_url1": ("STRING", {"default": ""}),
            "image_url2": ("STRING", {"default": ""}),
            "api_key": ("STRING", {"default": ""}),
            "tier": (["Gen-2.5-Extreme-Low", "Gen-2.5-Low", "Gen-2.5-Medium", "Gen-2.5-High", "Gen-2.5-Extreme-High"], {"default": "Gen-2.5-Extreme-Low"}),
            "geometry_file_format": (["glb", "usdz", "fbx", "obj", "stl"], {"default": "glb"}),
            "material": (["PBR", "Shaded", "All", "None"], {"default": "All"}),
            "quality_mesh_option": (["4K Quad", "8K Quad", "18K Quad", "50K Quad", "100K Quad", "200K Quad", "2K Triangle", "20K Triangle", "150K Triangle", "500K Triangle", "1M Triangle", "2M Triangle"], {"default": "4K Quad"}),
            "texture_mode": (["legacy", "extreme-low", "low", "medium", "high"], {"default": "extreme-low"}),
            "geometry_instruct_mode": (["faithful", "creative"], {"default": "faithful"}),
            "is_symmetric": (["symmetric", "balanced", "asymmetric", "unknown"], {"default": "unknown"}),
            "use_original_alpha": ("BOOLEAN", {"default": False}),
            "hd_texture": ("BOOLEAN", {"default": False}),
            "texture_delight": ("BOOLEAN", {"default": False}),
            "is_micro": ("BOOLEAN", {"default": False}),
            "TAPose": ("BOOLEAN", {"default": False}),
            "seed": ("INT", {"default": 0, "min": 0, "max": FAL_SEED_MAX, "tooltip": "0 = random seed. FAL seed max is 65535."}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("STRING", "STRING", "STRING", "FILE_3D")
    RETURN_NAMES = ("model_url", "response", "texture_urls", "model_3d")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"

    def process(self, prompt, mode="text_to_3d", image1=None, image2=None, image_url1="", image_url2="",
                api_key="", tier="Gen-2.5-Extreme-Low", geometry_file_format="glb",
                material="All", quality_mesh_option="4K Quad", texture_mode="extreme-low",
                geometry_instruct_mode="faithful", is_symmetric="unknown", use_original_alpha=False,
                hd_texture=False, texture_delight=False, is_micro=False, TAPose=False, seed=0,
                image_way="base64", poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            payload = {
                "prompt": prompt,
                "tier": tier,
                "geometry_file_format": geometry_file_format,
                "material": material,
                "quality_mesh_option": quality_mesh_option,
                "texture_mode": texture_mode,
                "geometry_instruct_mode": geometry_instruct_mode,
                "is_symmetric": is_symmetric,
                "hd_texture": hd_texture,
                "texture_delight": texture_delight,
                "is_micro": is_micro,
                "TAPose": TAPose,
            }
            seed_value = self.seed_payload_value(seed)
            if seed_value is not None:
                payload["seed"] = seed_value
            endpoint = "fal-ai/hyper3d/rodin/v2.5/text-to-3d"
            if mode == "image_to_3d":
                urls = [u for u in (self.prepare_image(image1, image_url1, image_way), self.prepare_image(image2, image_url2, image_way)) if u]
                if not urls:
                    raise RuntimeError("image_to_3d mode requires image or image_url.")
                payload["image_urls"] = urls
                payload["use_original_alpha"] = use_original_alpha
                endpoint = "fal-ai/hyper3d/rodin/v2.5"
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll(endpoint, payload, ["model_mesh", "model_meshes"], pbar, poll_interval, max_poll_attempts)
            urls = self.extract_model_urls(result)
            model_url = self.choose_model_url(urls, geometry_file_format)
            if not model_url:
                raise RuntimeError("No model mesh URL in result")
            model_3d = self.url_to_file_3d(model_url, geometry_file_format)
            pbar.update_absolute(100)
            return (model_url, self.info(result), "\n".join([u for u in urls if u != model_url]), model_3d)
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return ("", error_message, "", None)


class Comfly_krea_v2_fal(ComflyFalBase):
    LOG_PREFIX = "krea_v2_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": ""})}, "optional": {
            "model_size": (["medium", "large"], {"default": "medium"}),
            "style_image1": ("IMAGE",),
            "style_image2": ("IMAGE",),
            "style_image_url1": ("STRING", {"default": ""}),
            "style_image_url2": ("STRING", {"default": ""}),
            "api_key": ("STRING", {"default": ""}),
            "aspect_ratio": (["1:1", "4:3", "3:2", "16:9", "2.35:1", "4:5", "2:3", "9:16"], {"default": "1:1"}),
            "creativity": (["raw", "low", "medium", "high"], {"default": "medium"}),
            "style_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05}),
            "seed": ("INT", {"default": 0, "min": 0, "max": FAL_SEED_MAX, "tooltip": "0 = random seed. FAL seed max is 65535."}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("images", "response", "image_urls")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"

    def process(self, prompt, model_size="medium", style_image1=None, style_image2=None,
                style_image_url1="", style_image_url2="", api_key="", aspect_ratio="1:1",
                creativity="medium", style_strength=1.0, seed=0, image_way="base64",
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        default_image = self.blank_image()
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            payload = {"prompt": prompt, "aspect_ratio": aspect_ratio, "creativity": creativity}
            seed_value = self.seed_payload_value(seed)
            if seed_value is not None:
                payload["seed"] = seed_value
            refs = []
            for img, url in ((style_image1, style_image_url1), (style_image2, style_image_url2)):
                prepared = self.prepare_image(img, url, image_way)
                if prepared:
                    refs.append({"image_url": prepared, "strength": style_strength})
            if refs:
                payload["image_style_references"] = refs
            endpoint = f"krea/v2/{model_size}/text-to-image"
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll(endpoint, payload, ["images"], pbar, poll_interval, max_poll_attempts)
            urls = self.extract_image_urls(result)
            images = self.download_images(urls)
            pbar.update_absolute(100)
            return (images, self.info(result), "\n".join(urls))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return (default_image, error_message, "")


class Comfly_flux_pro_vto_fal(ComflyFalBase):
    LOG_PREFIX = "flux_pro_vto_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": ""})}, "optional": {
            "human_image": ("IMAGE",),
            "garment_image": ("IMAGE",),
            "human_image_url": ("STRING", {"default": ""}),
            "garment_image_url": ("STRING", {"default": ""}),
            "api_key": ("STRING", {"default": ""}),
            "num_inference_steps": ("INT", {"default": 4, "min": 1, "max": 50, "step": 1}),
            "output_format": (["jpeg", "png"], {"default": "jpeg"}),
            "seed": ("INT", {"default": 0, "min": 0, "max": FAL_SEED_MAX, "tooltip": "0 = random seed. FAL seed max is 65535."}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("images", "response", "image_urls")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"

    def process(self, prompt, human_image=None, garment_image=None, human_image_url="", garment_image_url="",
                api_key="", num_inference_steps=4, output_format="jpeg", seed=0, image_way="base64",
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        default_image = human_image if human_image is not None else self.blank_image()
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            human_url = self.prepare_image(human_image, human_image_url, image_way)
            garment_url = self.prepare_image(garment_image, garment_image_url, image_way)
            if not human_url or not garment_url:
                raise RuntimeError("FLUX VTO requires human_image and garment_image, or both URLs.")
            payload = {
                "prompt": prompt,
                "human_image_url": human_url,
                "garment_image_url": garment_url,
                "num_inference_steps": num_inference_steps,
                "output_format": output_format,
            }
            seed_value = self.seed_payload_value(seed)
            if seed_value is not None:
                payload["seed"] = seed_value
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("fal-ai/flux-pro/v1/vto", payload, ["images"], pbar, poll_interval, max_poll_attempts)
            urls = self.extract_image_urls(result)
            images = self.download_images(urls)
            pbar.update_absolute(100)
            return (images, self.info(result), "\n".join(urls))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return (default_image, error_message, "")


class Comfly_heygen_avatar5_fal(ComflyFalBase):
    LOG_PREFIX = "heygen_avatar5_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": ""})}, "optional": {
            "api_key": ("STRING", {"default": ""}),
            "avatar": ("STRING", {"default": "Abigail Sofa Front"}),
            "voice": ("STRING", {"default": "Warm Pro Narrator"}),
            "audio_url": ("STRING", {"default": ""}),
            "fit": (["contain", "cover"], {"default": "cover"}),
            "remove_background": ("BOOLEAN", {"default": False}),
            "caption": ("BOOLEAN", {"default": False}),
            "output_format": (["mp4", "webm"], {"default": "mp4"}),
            "resolution": (["720p", "1080p", "4k"], {"default": "720p"}),
            "aspect_ratio": (["16:9", "9:16", "4:5", "5:4", "1:1", "auto"], {"default": "16:9"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def process(self, prompt, api_key="", avatar="Abigail Sofa Front", voice="Warm Pro Narrator",
                audio_url="", fit="cover", remove_background=False, caption=False,
                output_format="mp4", resolution="720p", aspect_ratio="16:9",
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            payload = {
                "avatar": avatar,
                "prompt": prompt,
                "voice": voice,
                "fit": fit,
                "remove_background": remove_background,
                "caption": caption,
                "output_format": output_format,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
            }
            if audio_url.strip():
                payload["audio_url"] = audio_url.strip()
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("fal-ai/heygen/avatar5/digital-twin", payload, ["video", "video_url"], pbar, poll_interval, max_poll_attempts)
            video_url = self.extract_video_url(result)
            if not video_url:
                raise RuntimeError("No video URL in result")
            pbar.update_absolute(100)
            return (FalVideoAdapter(video_url), video_url, self.info(result))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return ("", "", error_message)


class Comfly_recraft_v4_1_fal(ComflyFalBase):
    LOG_PREFIX = "recraft_v4_1_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": ""})}, "optional": {
            "api_key": ("STRING", {"default": ""}),
            "image_size": (["square_hd", "square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"], {"default": "square_hd"}),
            "background_r": ("INT", {"default": -1, "min": -1, "max": 255, "tooltip": "-1 disables background_color."}),
            "background_g": ("INT", {"default": -1, "min": -1, "max": 255}),
            "background_b": ("INT", {"default": -1, "min": -1, "max": 255}),
            "palette_colors": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional RGB colors, one per line, format: r,g,b"}),
            "enable_safety_checker": ("BOOLEAN", {"default": True}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("images", "response", "image_urls")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"

    def parse_colors(self, palette_colors):
        colors = []
        for line in str(palette_colors or "").splitlines():
            parts = [p.strip() for p in line.replace(";", ",").split(",") if p.strip()]
            if len(parts) >= 3:
                try:
                    colors.append({"r": max(0, min(255, int(float(parts[0])))),
                                   "g": max(0, min(255, int(float(parts[1])))),
                                   "b": max(0, min(255, int(float(parts[2]))))})
                except Exception:
                    pass
        return colors

    def process(self, prompt, api_key="", image_size="square_hd", background_r=-1, background_g=-1,
                background_b=-1, palette_colors="", enable_safety_checker=True,
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        payload = {"image_size": image_size, "enable_safety_checker": enable_safety_checker}
        if background_r >= 0 and background_g >= 0 and background_b >= 0:
            payload["background_color"] = {"r": background_r, "g": background_g, "b": background_b}
        colors = self.parse_colors(palette_colors)
        if colors:
            payload["colors"] = colors
        return _run_image_node(self, "fal-ai/recraft/v4.1/text-to-image", prompt, api_key, skip_error, payload, poll_interval, max_poll_attempts)


class Comfly_topaz_upscale_fal(ComflyFalBase):
    LOG_PREFIX = "topaz_upscale_fal"
    IMAGE_MODELS = [
        "Low Resolution V2", "Standard V2", "CGI", "High Fidelity V2", "Text Refine",
        "Recovery", "Redefine", "Recovery V2", "Standard MAX", "Wonder",
    ]
    VIDEO_MODELS = [
        "Proteus", "Artemis HQ", "Artemis MQ", "Artemis LQ", "Nyx", "Nyx Fast",
        "Nyx XL", "Nyx HF", "Gaia HQ", "Gaia CG", "Gaia 2", "Starlight Precise 1",
        "Starlight Precise 2", "Starlight Precise 2.5", "Starlight HQ",
        "Starlight Mini", "Starlight Sharp", "Starlight Fast 1", "Starlight Fast 2",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"mode": (["image", "video"], {"default": "image"})}, "optional": {
            "image": ("IMAGE",),
            "video": (IO.VIDEO,),
            "image_url": ("STRING", {"default": ""}),
            "video_url": ("STRING", {"default": ""}),
            "api_key": ("STRING", {"default": ""}),
            "image_model": (cls.IMAGE_MODELS, {"default": "Standard V2"}),
            "video_model": (cls.VIDEO_MODELS, {"default": "Proteus"}),
            "upscale_factor": ("FLOAT", {"default": 2.0, "min": 1.0, "max": 8.0, "step": 0.5}),
            "output_format": (["jpeg", "png"], {"default": "jpeg"}),
            "subject_detection": (["All", "Foreground", "Background"], {"default": "All"}),
            "crop_to_fill": ("BOOLEAN", {"default": False}),
            "face_enhancement": ("BOOLEAN", {"default": True}),
            "face_enhancement_creativity": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": 0.05, "tooltip": "-1 leaves API default/unset."}),
            "face_enhancement_strength": ("FLOAT", {"default": 0.8, "min": -1.0, "max": 1.0, "step": 0.05, "tooltip": "-1 leaves API default/unset."}),
            "sharpen": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": 0.05, "tooltip": "-1 leaves API default/unset."}),
            "denoise": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": 0.05, "tooltip": "-1 leaves API default/unset."}),
            "fix_compression": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": 0.05, "tooltip": "-1 leaves API default/unset."}),
            "strength": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": 0.05, "tooltip": "Text Refine only; -1 leaves unset."}),
            "creativity": ("INT", {"default": 0, "min": 0, "max": 6, "step": 1, "tooltip": "Redefine only; 0 leaves unset."}),
            "texture": ("INT", {"default": 0, "min": 0, "max": 5, "step": 1, "tooltip": "Redefine only; 0 leaves unset."}),
            "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "Redefine prompt."}),
            "autoprompt": ("BOOLEAN", {"default": False}),
            "detail": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": 0.05, "tooltip": "Recovery V2 only; -1 leaves unset."}),
            "target_fps": ("INT", {"default": 0, "min": 0, "max": 120, "step": 1, "tooltip": "0 leaves unset. Setting FPS enables frame interpolation."}),
            "compression": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": 0.05, "tooltip": "-1 leaves API default/unset."}),
            "noise": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": 0.05, "tooltip": "-1 leaves API default/unset."}),
            "halo": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": 0.05, "tooltip": "-1 leaves API default/unset."}),
            "grain": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 0.1, "step": 0.01, "tooltip": "-1 leaves API default/unset."}),
            "recover_detail": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": 0.05, "tooltip": "-1 leaves API default/unset."}),
            "h264_output": ("BOOLEAN", {"default": False}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "video_way": (["upload", "video_url"], {"default": "upload"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("IMAGE", IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("image", "video", "response", "url")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def _add_optional_float(self, payload, key, value):
        if value is not None and float(value) >= 0:
            payload[key] = float(value)

    def process(self, mode="image", image=None, video=None, image_url="", video_url="", api_key="",
                image_model="Standard V2", video_model="Proteus", upscale_factor=2.0,
                output_format="jpeg", subject_detection="All", crop_to_fill=False,
                face_enhancement=True, face_enhancement_creativity=-1.0,
                face_enhancement_strength=0.8, sharpen=-1.0, denoise=-1.0,
                fix_compression=-1.0, strength=-1.0, creativity=0, texture=0,
                prompt="", autoprompt=False, detail=-1.0, target_fps=0,
                compression=-1.0, noise=-1.0, halo=-1.0, grain=-1.0,
                recover_detail=-1.0, h264_output=False, image_way="base64",
                video_way="upload", poll_interval=6, max_poll_attempts=600,
                skip_error=False):
        self.set_api_key(api_key)
        default_image = image if image is not None else self.blank_image()
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            if mode == "video":
                prepared_video = self.prepare_video(video, video_url, video_way)
                if not prepared_video:
                    raise RuntimeError("video mode requires a video input or video_url.")
                payload = {
                    "video_url": prepared_video,
                    "model": video_model,
                    "upscale_factor": float(upscale_factor),
                    "H264_output": h264_output,
                }
                if target_fps > 0:
                    payload["target_fps"] = int(target_fps)
                for key, value in (
                    ("compression", compression),
                    ("noise", noise),
                    ("halo", halo),
                    ("grain", grain),
                    ("recover_detail", recover_detail),
                ):
                    self._add_optional_float(payload, key, value)
                result = self.submit_and_poll("fal-ai/topaz/upscale/video", payload, ["video", "video_url"], pbar, poll_interval, max_poll_attempts)
                result_video_url = self.extract_video_url(result)
                if not result_video_url:
                    raise RuntimeError("No video URL in result")
                pbar.update_absolute(100)
                return (default_image, FalVideoAdapter(result_video_url), self.info(result), result_video_url)

            prepared_image = self.prepare_image(image, image_url, image_way)
            if not prepared_image:
                raise RuntimeError("image mode requires an image input or image_url.")
            payload = {
                "model": image_model,
                "upscale_factor": float(upscale_factor),
                "crop_to_fill": crop_to_fill,
                "image_url": prepared_image,
                "output_format": output_format,
                "subject_detection": subject_detection,
                "face_enhancement": face_enhancement,
            }
            for key, value in (
                ("face_enhancement_creativity", face_enhancement_creativity),
                ("face_enhancement_strength", face_enhancement_strength),
                ("sharpen", sharpen),
                ("denoise", denoise),
                ("fix_compression", fix_compression),
                ("strength", strength),
                ("detail", detail),
            ):
                self._add_optional_float(payload, key, value)
            if creativity > 0:
                payload["creativity"] = int(creativity)
            if texture > 0:
                payload["texture"] = int(texture)
            if str(prompt or "").strip():
                payload["prompt"] = str(prompt).strip()
            if autoprompt:
                payload["autoprompt"] = True

            result = self.submit_and_poll("fal-ai/topaz/upscale/image", payload, ["image", "images"], pbar, poll_interval, max_poll_attempts)
            urls = self.extract_image_urls(result)
            images = self.download_images(urls)
            pbar.update_absolute(100)
            return (images, "", self.info(result), "\n".join(urls))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return (default_image, "", error_message, "")


class Comfly_sonilo_video_to_music_fal(ComflyFalBase):
    LOG_PREFIX = "sonilo_video_to_music_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"video_url": ("STRING", {"default": "", "tooltip": "Public video URL. Ignored when video input is connected."})}, "optional": {
            "video": (IO.VIDEO,),
            "api_key": ("STRING", {"default": ""}),
            "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional music style/mood prompt. Empty lets Sonilo infer from video."}),
            "num_samples": ("INT", {"default": 1, "min": 1, "max": 3, "step": 1}),
            "start_offset": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 600.0, "step": 0.1, "tooltip": "Seconds. 0 leaves unset."}),
            "duration": ("FLOAT", {"default": 5.0, "min": 0.0, "max": 600.0, "step": 0.1, "tooltip": "Seconds. 0 leaves unset/full remaining video. 5s is a low-cost default."}),
            "video_way": (["upload", "video_url"], {"default": "upload"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("AUDIO", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio", "audio_url", "all_audio_urls", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def process(self, video_url="", video=None, api_key="", prompt="", num_samples=1,
                start_offset=0.0, duration=5.0, video_way="upload", poll_interval=6,
                max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            prepared_video = self.prepare_video(video, video_url, video_way)
            if not prepared_video:
                raise RuntimeError("Sonilo video-to-music requires a video input or video_url.")
            payload = {"video_url": prepared_video, "num_samples": int(num_samples)}
            if str(prompt or "").strip():
                payload["prompt"] = str(prompt).strip()
            if float(start_offset) > 0:
                payload["start_offset"] = float(start_offset)
            if float(duration) > 0:
                payload["duration"] = float(duration)
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("sonilo/v1.1/video-to-music", payload, ["audio", "audios"], pbar, poll_interval, max_poll_attempts)
            audio_urls = self.extract_audio_urls(result)
            if not audio_urls:
                raise RuntimeError("No audio URL in result")
            audio_url = audio_urls[0]
            audio = self.audio_url_to_audio_object(audio_url)
            pbar.update_absolute(100)
            return (audio, audio_url, "\n".join(audio_urls), self.info(result))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return (self.blank_audio(), "", "", error_message)


class Comfly_mai_image_2_5_edit_fal(ComflyFalBase):
    LOG_PREFIX = "mai_image_2_5_edit_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": ""})}, "optional": {
            "image1": ("IMAGE",),
            "image2": ("IMAGE",),
            "image3": ("IMAGE",),
            "image4": ("IMAGE",),
            "image_urls": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional external image URLs, one per line."}),
            "api_key": ("STRING", {"default": ""}),
            "num_images": ("INT", {"default": 1, "min": 1, "max": 4, "step": 1}),
            "aspect_ratio": (["auto", "1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3"], {"default": "auto"}),
            "output_format": (["png", "jpeg", "webp"], {"default": "png"}),
            "sync_mode": ("BOOLEAN", {"default": False}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("images", "response", "image_urls")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"

    def _parse_url_lines(self, image_urls):
        urls = []
        for line in str(image_urls or "").splitlines():
            value = line.strip()
            if value:
                urls.append(value)
        return urls

    def process(self, prompt, image1=None, image2=None, image3=None, image4=None,
                image_urls="", api_key="", num_images=1, aspect_ratio="auto",
                output_format="png", sync_mode=False, image_way="base64",
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        default_image = image1 if image1 is not None else self.blank_image()
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            prepared_images = []
            for img in (image1, image2, image3, image4):
                prepared = self.prepare_image(img, "", image_way)
                if prepared:
                    prepared_images.append(prepared)
            prepared_images.extend(self._parse_url_lines(image_urls))
            prepared_images = list(dict.fromkeys([u for u in prepared_images if u]))
            if not prepared_images:
                raise RuntimeError("MAI Image 2.5 Edit requires at least one image input or image URL.")
            payload = {
                "prompt": prompt,
                "image_urls": prepared_images,
                "num_images": int(num_images),
                "aspect_ratio": aspect_ratio,
                "output_format": output_format,
                "sync_mode": sync_mode,
            }
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("microsoft/mai-image-2.5/edit", payload, ["images"], pbar, poll_interval, max_poll_attempts)
            urls = self.extract_image_urls(result)
            images = self.download_images(urls)
            pbar.update_absolute(100)
            return (images, self.info(result), "\n".join(urls))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return (default_image, error_message, "")


def _run_image_node(node, endpoint, prompt, api_key, skip_error, extra_payload, poll_interval, max_poll_attempts):
    node.set_api_key(api_key)
    default_image = node.blank_image()
    try:
        if not node.api_key:
            raise RuntimeError("API key not provided. Please set your API key.")
        payload = {"prompt": prompt}
        payload.update(extra_payload)
        pbar = comfy.utils.ProgressBar(100)
        pbar.update_absolute(10)
        result = node.submit_and_poll(endpoint, payload, ["images"], pbar, poll_interval, max_poll_attempts)
        urls = node.extract_image_urls(result)
        images = node.download_images(urls)
        pbar.update_absolute(100)
        return (images, node.info(result), "\n".join(urls))
    except Exception as e:
        error_message = f"Error: {str(e)}"
        node._log(error_message)
        if not skip_error:
            raise
        return (default_image, error_message, "")
