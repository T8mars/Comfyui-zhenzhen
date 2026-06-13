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
HEYGEN_AVATAR5_OPENAPI_URL = "https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/heygen/avatar5/digital-twin"
HEYGEN_AVATAR5_SERVER_DEFAULT = "server_default"
HEYGEN_AVATAR4_I2V_OPENAPI_URL = "https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/heygen/avatar4/image-to-video"
HEYGEN_AVATAR4_SERVER_DEFAULT = HEYGEN_AVATAR5_SERVER_DEFAULT
HEYGEN_AVATAR4_FALLBACK_VOICES = [
    "Melissa",
    "Warm Pro Narrator",
    "Ann - IA",
    "Chill Brian",
]
HEYGEN_AVATAR5_FALLBACK_AVATARS = [
    "Abigail Sofa Front",
    "Abigail Office Front",
    "Ann Doctor Standing",
    "Ann Doctor Sitting",
]
HEYGEN_AVATAR5_FALLBACK_VOICES = [
    "Warm Pro Narrator",
    "Ann - IA",
    "Chill Brian",
    "Ivy",
]
_HEYGEN_AVATAR5_CATALOG = None
_HEYGEN_AVATAR4_VOICE_CATALOG = None


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


def _dedupe_preserve_order(values):
    seen = set()
    result = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _heygen_avatar5_catalog():
    global _HEYGEN_AVATAR5_CATALOG
    if _HEYGEN_AVATAR5_CATALOG is not None:
        return _HEYGEN_AVATAR5_CATALOG

    avatars = list(HEYGEN_AVATAR5_FALLBACK_AVATARS)
    voices = list(HEYGEN_AVATAR5_FALLBACK_VOICES)
    try:
        response = requests.get(HEYGEN_AVATAR5_OPENAPI_URL, timeout=5)
        response.raise_for_status()
        schema = response.json()
        properties = (
            schema.get("components", {})
            .get("schemas", {})
            .get("HeygenAvatar5DigitalTwinInput", {})
            .get("properties", {})
        )
        avatars = properties.get("avatar", {}).get("enum") or properties.get("avatar", {}).get("examples") or avatars
        voices = properties.get("voice", {}).get("enum") or properties.get("voice", {}).get("examples") or voices
    except Exception as e:
        print(f"[heygen_avatar5_fal] Could not load avatar/voice catalog, using fallback list: {e}")

    avatar_choices = [HEYGEN_AVATAR5_SERVER_DEFAULT] + _dedupe_preserve_order(avatars)
    voice_choices = [HEYGEN_AVATAR5_SERVER_DEFAULT] + _dedupe_preserve_order(voices)
    _HEYGEN_AVATAR5_CATALOG = (avatar_choices, voice_choices)
    return _HEYGEN_AVATAR5_CATALOG


def _heygen_avatar4_i2v_voice_catalog():
    global _HEYGEN_AVATAR4_VOICE_CATALOG
    if _HEYGEN_AVATAR4_VOICE_CATALOG is not None:
        return _HEYGEN_AVATAR4_VOICE_CATALOG

    voices = list(HEYGEN_AVATAR4_FALLBACK_VOICES)
    try:
        response = requests.get(HEYGEN_AVATAR4_I2V_OPENAPI_URL, timeout=5)
        response.raise_for_status()
        schema = response.json()
        voice_property = (
            schema.get("components", {})
            .get("schemas", {})
            .get("HeygenAvatar4ImageToVideoInput", {})
            .get("properties", {})
            .get("voice", {})
        )
        voices = (voice_property.get("examples") or []) + (voice_property.get("enum") or voices)
    except Exception as e:
        print(f"[heygen_avatar4_i2v_fal] Could not load voice catalog, using fallback list: {e}")

    _HEYGEN_AVATAR4_VOICE_CATALOG = [HEYGEN_AVATAR4_SERVER_DEFAULT] + _dedupe_preserve_order(voices)
    return _HEYGEN_AVATAR4_VOICE_CATALOG


def _optional_catalog_value(selected_value, custom_value=""):
    custom_value = str(custom_value).strip() if custom_value is not None else ""
    if custom_value:
        return custom_value
    if selected_value is None:
        return ""
    selected_value = str(selected_value)
    if not selected_value or selected_value == HEYGEN_AVATAR5_SERVER_DEFAULT:
        return ""
    return selected_value


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

    def parse_url_lines(self, text):
        urls = []
        for line in str(text or "").splitlines():
            value = line.strip()
            if value:
                urls.append(value)
        return _dedupe_preserve_order(urls)

    def parse_json_field(self, text, field_name, expected_type=None):
        value = str(text or "").strip()
        if not value:
            return None
        try:
            parsed = json.loads(value)
        except Exception as e:
            raise RuntimeError(f"{field_name} must be valid JSON: {e}")
        if expected_type is not None and not isinstance(parsed, expected_type):
            expected_name = getattr(expected_type, "__name__", str(expected_type))
            raise RuntimeError(f"{field_name} must be {expected_name} JSON.")
        return parsed

    def prepare_image_list(self, image_items=None, image_urls="", image_way="base64", max_count=0):
        values = []
        for image_tensor, image_url in image_items or []:
            prepared = self.prepare_image(image_tensor, image_url, image_way)
            if prepared:
                values.append(prepared)
        values.extend(self.parse_url_lines(image_urls))
        values = _dedupe_preserve_order(values)
        if max_count and len(values) > max_count:
            return values[:max_count]
        return values

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

    def audio_to_wav_bytes(self, audio_input):
        if not isinstance(audio_input, dict):
            return None, None
        waveform = audio_input.get("waveform")
        sample_rate = int(audio_input.get("sample_rate") or 44100)
        if waveform is None:
            return None, None
        try:
            import torchaudio
            if len(waveform.shape) == 3:
                waveform = waveform[0]
            if len(waveform.shape) == 1:
                waveform = waveform.unsqueeze(0)
            buffer = BytesIO()
            torchaudio.save(buffer, waveform.cpu(), sample_rate, format="wav")
            return buffer.getvalue(), "audio.wav"
        except Exception as e:
            self._log(f"Error encoding AUDIO input: {e}")
            return None, None

    def prepare_audio(self, audio_input=None, audio_url="", audio_way="upload"):
        explicit_url = str(audio_url or "").strip()
        if audio_way == "audio_url" and explicit_url:
            return explicit_url
        direct_url = self._direct_url_from_media(audio_input)
        if direct_url:
            return direct_url
        wav_bytes, wav_name = self.audio_to_wav_bytes(audio_input)
        if wav_bytes:
            return self.upload_bytes_to_get_url(wav_bytes, wav_name or "audio.wav", "audio/wav")
        file_bytes, filename = self.media_to_bytes(audio_input, ".wav", "audio")
        if file_bytes:
            return self.upload_bytes_to_get_url(file_bytes, filename or "audio.wav", mimetypes.guess_type(filename or "")[0] or "audio/wav")
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

        code = str(data.get("code", "")).strip().lower()
        if code and any(token in code for token in ("fail", "error", "unauthorized", "forbidden")):
            raise RuntimeError(f"{context}: {self._extract_error_message(data)}")

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
            for key in ("model_glb", "model_urls", "model_mesh", "model_meshes", "model", "mesh", "meshes", "textures", "files", "output", "outputs"):
                urls.extend(self.collect_file_urls(result.get(key)))
            if isinstance(result.get("data"), dict):
                urls.extend(self.extract_model_urls(result["data"]))
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
            "model_size": (["medium", "medium_turbo", "large"], {"default": "medium"}),
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
            endpoint_model = "medium/turbo" if model_size == "medium_turbo" else model_size
            endpoint = f"krea/v2/{endpoint_model}/text-to-image"
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
        avatar_choices, voice_choices = _heygen_avatar5_catalog()
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": ""})}, "optional": {
            "api_key": ("STRING", {"default": ""}),
            "avatar": (avatar_choices, {"default": HEYGEN_AVATAR5_SERVER_DEFAULT, "tooltip": "server_default leaves avatar unset and lets FAL use its default. Use custom_avatar for an exact custom name."}),
            "custom_avatar": ("STRING", {"default": "", "tooltip": "Overrides avatar dropdown when filled."}),
            "voice": (voice_choices, {"default": HEYGEN_AVATAR5_SERVER_DEFAULT, "tooltip": "server_default leaves voice unset and lets FAL use its default. Ignored when audio_url is provided."}),
            "custom_voice": ("STRING", {"default": "", "tooltip": "Overrides voice dropdown when filled."}),
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

    def process(self, prompt, api_key="", avatar=HEYGEN_AVATAR5_SERVER_DEFAULT, custom_avatar="",
                voice=HEYGEN_AVATAR5_SERVER_DEFAULT, custom_voice="", audio_url="",
                fit="cover", remove_background=False, caption=False,
                output_format="mp4", resolution="720p", aspect_ratio="16:9",
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            selected_avatar = _optional_catalog_value(avatar, custom_avatar)
            selected_voice = _optional_catalog_value(voice, custom_voice)
            audio_url = str(audio_url).strip() if audio_url else ""
            payload = {
                "fit": fit,
                "remove_background": remove_background,
                "caption": caption,
                "output_format": output_format,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
            }
            if selected_avatar:
                payload["avatar"] = selected_avatar
            if audio_url:
                payload["audio_url"] = audio_url
            else:
                if str(prompt).strip():
                    payload["prompt"] = prompt
                if selected_voice:
                    payload["voice"] = selected_voice
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


class Comfly_heygen_avatar4_i2v_fal(ComflyFalBase):
    LOG_PREFIX = "heygen_avatar4_i2v_fal"

    @classmethod
    def INPUT_TYPES(cls):
        voice_choices = _heygen_avatar4_i2v_voice_catalog()
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": "Hi."})}, "optional": {
            "image": ("IMAGE",),
            "image_url": ("STRING", {"default": ""}),
            "api_key": ("STRING", {"default": ""}),
            "audio": ("AUDIO",),
            "audio_url": ("STRING", {"default": ""}),
            "voice": (voice_choices, {"default": HEYGEN_AVATAR4_SERVER_DEFAULT, "tooltip": "server_default leaves voice unset and lets FAL use its default. Ignored when audio is provided."}),
            "custom_voice": ("STRING", {"default": "", "tooltip": "Overrides voice dropdown when filled."}),
            "talking_style": (["stable", "expressive"], {"default": "stable"}),
            "expression": (["none", "happy"], {"default": "none"}),
            "background_type": (["none", "color", "image", "video"], {"default": "none"}),
            "background_value": ("STRING", {"default": "#FFFFFF", "tooltip": "Hex color for color background, or URL for image/video background."}),
            "resolution": (["360p", "480p", "540p", "720p", "1080p"], {"default": "720p"}),
            "aspect_ratio": (["16:9", "9:16", "4:5", "5:4", "1:1", "auto"], {"default": "16:9"}),
            "caption": ("BOOLEAN", {"default": False}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "audio_way": (["upload", "audio_url"], {"default": "upload"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def process(self, prompt, image=None, image_url="", api_key="", audio=None, audio_url="",
                voice=HEYGEN_AVATAR4_SERVER_DEFAULT, custom_voice="", talking_style="stable",
                expression="none", background_type="none", background_value="#FFFFFF",
                resolution="720p", aspect_ratio="16:9", caption=False, image_way="base64",
                audio_way="upload", poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")

            prepared_image = self.prepare_image(image, image_url, image_way)
            if not prepared_image:
                raise RuntimeError("Heygen Avatar4 image-to-video requires an IMAGE input or image_url.")

            prepared_audio = self.prepare_audio(audio, audio_url, audio_way)
            selected_voice = _optional_catalog_value(voice, custom_voice)

            payload = {
                "image_url": prepared_image,
                "talking_style": talking_style,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "caption": bool(caption),
            }
            if prepared_audio:
                payload["audio_url"] = prepared_audio
            else:
                if str(prompt or "").strip():
                    payload["prompt"] = str(prompt).strip()
                if selected_voice:
                    payload["voice"] = selected_voice
            if expression != "none":
                payload["expression"] = expression
            if background_type != "none":
                value = str(background_value or "").strip()
                if background_type == "color":
                    payload["background"] = {"type": "color", "value": value or "#FFFFFF"}
                elif value:
                    payload["background"] = {"type": background_type, "value": value}
                else:
                    raise RuntimeError(f"background_value is required when background_type is {background_type}.")

            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("fal-ai/heygen/avatar4/image-to-video", payload, ["video", "video_url"], pbar, poll_interval, max_poll_attempts)
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


class Comfly_seed_speech_tts_v2_fal(ComflyFalBase):
    LOG_PREFIX = "seed_speech_tts_v2_fal"

    VOICES = [
        "stokie_en", "vivi_mixed_en_zh_ja_es_id", "mindy_en_es_id_pt_zh", "dacey_en",
        "tim_en", "kian_en_zh", "cedric_en_zh", "sophie_en_zh", "jean_en_zh",
        "magnus_en_zh", "mabel_en_zh", "nadia_en_zh", "opal_en_zh", "pearl_en_zh",
        "quentin_en_zh", "vienna_mixed_en_zh", "alina_mixed_en_zh", "bonnie_zh",
        "felix_zh", "celeste_zh", "monkey_king_zh",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"text": ("STRING", {"multiline": True, "default": "Hello, this is a short text to speech test."})}, "optional": {
            "api_key": ("STRING", {"default": ""}),
            "voice": (cls.VOICES, {"default": "stokie_en"}),
            "output_format": (["mp3", "opus"], {"default": "mp3"}),
            "sample_rate": (["8000", "16000", "22050", "24000", "32000", "44100", "48000"], {"default": "24000"}),
            "speed": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.05}),
            "volume": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05}),
            "pitch": ("INT", {"default": 0, "min": -12, "max": 12, "step": 1}),
            "language": (["auto", "zh", "en", "ja", "es-mx", "id", "pt-br", "ko", "it", "de", "fr"], {"default": "auto"}),
            "voice_instruction": ("STRING", {"default": "", "multiline": True}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "audio_url", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def process(self, text, api_key="", voice="stokie_en", output_format="mp3", sample_rate="24000",
                speed=1.0, volume=1.0, pitch=0, language="auto", voice_instruction="",
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            payload = {
                "text": text,
                "voice": voice,
                "output_format": output_format,
                "sample_rate": int(sample_rate),
                "speed": float(speed),
                "volume": float(volume),
                "pitch": int(pitch),
            }
            if language != "auto":
                payload["language"] = language
            if str(voice_instruction or "").strip():
                payload["voice_instruction"] = str(voice_instruction).strip()
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("fal-ai/bytedance/seed-speech/tts/v2", payload, ["audio"], pbar, poll_interval, max_poll_attempts)
            audio_urls = self.extract_audio_urls(result)
            if not audio_urls:
                raise RuntimeError("No audio URL in result")
            audio_url = audio_urls[0]
            audio = self.audio_url_to_audio_object(audio_url)
            pbar.update_absolute(100)
            return (audio, audio_url, self.info(result))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return (self.blank_audio(), "", error_message)


class Comfly_minimax_speech_2_8_fal(ComflyFalBase):
    LOG_PREFIX = "minimax_speech_2_8_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": "Hello world! Welcome to MiniMax speech."})}, "optional": {
            "model_quality": (["turbo", "hd"], {"default": "turbo"}),
            "api_key": ("STRING", {"default": ""}),
            "voice_id": ("STRING", {"default": "Wise_Woman"}),
            "speed": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.05}),
            "vol": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.05}),
            "pitch": ("INT", {"default": 0, "min": -12, "max": 12, "step": 1}),
            "emotion": (["none", "happy", "sad", "angry", "fearful", "disgusted", "surprised", "neutral"], {"default": "none"}),
            "english_normalization": ("BOOLEAN", {"default": False}),
            "sample_rate": (["8000", "16000", "22050", "24000", "32000", "44100"], {"default": "32000"}),
            "bitrate": (["32000", "64000", "128000", "256000"], {"default": "128000"}),
            "format": (["mp3", "wav", "flac"], {"default": "mp3"}),
            "language_boost": (["auto", "English", "Chinese", "Chinese,Yue", "Japanese", "Korean", "Spanish", "French", "Portuguese", "German", "Italian", "Indonesian", "Vietnamese", "Thai"], {"default": "auto"}),
            "output_format": (["url", "hex"], {"default": "url"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "audio_url", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def process(self, prompt, model_quality="turbo", api_key="", voice_id="Wise_Woman",
                speed=1.0, vol=1.0, pitch=0, emotion="none", english_normalization=False,
                sample_rate="32000", bitrate="128000", format="mp3", language_boost="auto",
                output_format="url", poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            voice_setting = {
                "voice_id": voice_id,
                "speed": float(speed),
                "vol": float(vol),
                "pitch": int(pitch),
                "english_normalization": bool(english_normalization),
            }
            if emotion != "none":
                voice_setting["emotion"] = emotion
            payload = {
                "prompt": prompt,
                "voice_setting": voice_setting,
                "audio_setting": {
                    "sample_rate": int(sample_rate),
                    "bitrate": int(bitrate),
                    "format": format,
                },
                "output_format": output_format,
            }
            if language_boost != "auto":
                payload["language_boost"] = language_boost
            endpoint = f"fal-ai/minimax/speech-2.8-{model_quality}"
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll(endpoint, payload, ["audio"], pbar, poll_interval, max_poll_attempts)
            audio_urls = self.extract_audio_urls(result)
            if not audio_urls:
                raise RuntimeError("No audio URL in result")
            audio_url = audio_urls[0]
            audio = self.audio_url_to_audio_object(audio_url)
            pbar.update_absolute(100)
            return (audio, audio_url, self.info(result))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return (self.blank_audio(), "", error_message)


class Comfly_lyria2_fal(ComflyFalBase):
    LOG_PREFIX = "lyria2_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": "A short ambient piano melody with soft warm strings."})}, "optional": {
            "api_key": ("STRING", {"default": ""}),
            "negative_prompt": ("STRING", {"default": "low quality", "multiline": True}),
            "seed": ("INT", {"default": 0, "min": 0, "max": FAL_SEED_MAX, "tooltip": "0 = random seed. FAL seed max is 65535."}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "audio_url", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def process(self, prompt, api_key="", negative_prompt="low quality", seed=0,
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            payload = {"prompt": prompt}
            if str(negative_prompt or "").strip():
                payload["negative_prompt"] = str(negative_prompt).strip()
            seed_value = self.seed_payload_value(seed)
            if seed_value is not None:
                payload["seed"] = seed_value
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("fal-ai/lyria2", payload, ["audio"], pbar, poll_interval, max_poll_attempts)
            audio_urls = self.extract_audio_urls(result)
            if not audio_urls:
                raise RuntimeError("No audio URL in result")
            audio_url = audio_urls[0]
            audio = self.audio_url_to_audio_object(audio_url)
            pbar.update_absolute(100)
            return (audio, audio_url, self.info(result))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return (self.blank_audio(), "", error_message)


class Comfly_bria_fibo_edit_fal(ComflyFalBase):
    LOG_PREFIX = "bria_fibo_edit_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"instruction": ("STRING", {"multiline": True, "default": "change lighting to starlight nighttime"})}, "optional": {
            "image": ("IMAGE",),
            "mask": ("IMAGE",),
            "image_url": ("STRING", {"default": ""}),
            "mask_url": ("STRING", {"default": ""}),
            "api_key": ("STRING", {"default": ""}),
            "seed": ("INT", {"default": 5555, "min": 0, "max": FAL_SEED_MAX, "tooltip": "0 = random seed. FAL seed max is 65535."}),
            "steps_num": ("INT", {"default": 30, "min": 20, "max": 100, "step": 1}),
            "negative_prompt": ("STRING", {"default": "", "multiline": True}),
            "guidance_scale": ("FLOAT", {"default": 5.0, "min": 0.0, "max": 30.0, "step": 0.1}),
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

    def process(self, instruction, image=None, mask=None, image_url="", mask_url="", api_key="",
                seed=5555, steps_num=30, negative_prompt="", guidance_scale=5.0, sync_mode=False,
                image_way="base64", poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        default_image = image if image is not None else self.blank_image()
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            prepared_image = self.prepare_image(image, image_url, image_way)
            if not prepared_image:
                raise RuntimeError("Bria Fibo Edit requires image or image_url.")
            payload = {
                "image_url": prepared_image,
                "instruction": instruction,
                "steps_num": int(steps_num),
                "guidance_scale": float(guidance_scale),
                "sync_mode": sync_mode,
            }
            seed_value = self.seed_payload_value(seed)
            if seed_value is not None:
                payload["seed"] = seed_value
            prepared_mask = self.prepare_image(mask, mask_url, image_way)
            if prepared_mask:
                payload["mask_url"] = prepared_mask
            if str(negative_prompt or "").strip():
                payload["negative_prompt"] = str(negative_prompt).strip()
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("bria/fibo-edit/edit", payload, ["image", "images"], pbar, poll_interval, max_poll_attempts)
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


class Comfly_grok_video_tools_fal(ComflyFalBase):
    LOG_PREFIX = "grok_video_tools_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": "Colorize the video"})}, "optional": {
            "mode": (["extend_video", "edit_video"], {"default": "edit_video"}),
            "video": (IO.VIDEO,),
            "video_url": ("STRING", {"default": "", "tooltip": "Public video URL. Ignored when video input is connected."}),
            "api_key": ("STRING", {"default": ""}),
            "duration": ("INT", {"default": 6, "min": 1, "max": 15, "step": 1, "tooltip": "Used by extend_video mode."}),
            "resolution": (["auto", "480p", "720p"], {"default": "auto", "tooltip": "Used by edit_video mode."}),
            "video_way": (["upload", "video_url"], {"default": "upload"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def process(self, prompt, mode="edit_video", video=None, video_url="", api_key="",
                duration=6, resolution="auto", video_way="upload",
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            prepared_video = self.prepare_video(video, video_url, video_way)
            if not prepared_video:
                raise RuntimeError("Grok video tools require a video input or video_url.")
            payload = {"prompt": prompt, "video_url": prepared_video}
            endpoint = "xai/grok-imagine-video/edit-video"
            if mode == "extend_video":
                endpoint = "xai/grok-imagine-video/extend-video"
                payload["duration"] = int(duration)
            else:
                payload["resolution"] = resolution
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll(endpoint, payload, ["video"], pbar, poll_interval, max_poll_attempts)
            result_video_url = self.extract_video_url(result)
            if not result_video_url:
                raise RuntimeError("No video URL in result")
            pbar.update_absolute(100)
            return (FalVideoAdapter(result_video_url), result_video_url, self.info(result))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return ("", "", error_message)


class Comfly_pixverse_v6_fal(ComflyFalBase):
    LOG_PREFIX = "pixverse_v6_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": "A cinematic camera move with subtle motion."})}, "optional": {
            "image": ("IMAGE",),
            "image_url": ("STRING", {"default": ""}),
            "api_key": ("STRING", {"default": ""}),
            "resolution": (["360p", "540p", "720p", "1080p"], {"default": "720p"}),
            "duration": ("INT", {"default": 5, "min": 1, "max": 15, "step": 1}),
            "negative_prompt": ("STRING", {"default": "blurry, low quality, low resolution, pixelated, noisy, grainy", "multiline": True}),
            "style": (["none", "anime", "3d_animation", "clay", "comic", "cyberpunk"], {"default": "none"}),
            "seed": ("INT", {"default": 0, "min": 0, "max": FAL_SEED_MAX, "tooltip": "0 = random seed. FAL seed max is 65535."}),
            "generate_audio_switch": ("BOOLEAN", {"default": False}),
            "generate_multi_clip_switch": ("BOOLEAN", {"default": False}),
            "thinking_type": (["auto", "enabled", "disabled"], {"default": "auto"}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def process(self, prompt, image=None, image_url="", api_key="", resolution="720p",
                duration=5, negative_prompt="blurry, low quality, low resolution, pixelated, noisy, grainy",
                style="none", seed=0, generate_audio_switch=False, generate_multi_clip_switch=False,
                thinking_type="auto", image_way="base64", poll_interval=6,
                max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            prepared_image = self.prepare_image(image, image_url, image_way)
            if not prepared_image:
                raise RuntimeError("PixVerse V6 requires image or image_url.")
            payload = {
                "prompt": prompt,
                "image_url": prepared_image,
                "resolution": resolution,
                "duration": int(duration),
                "generate_audio_switch": generate_audio_switch,
                "generate_multi_clip_switch": generate_multi_clip_switch,
                "thinking_type": thinking_type,
            }
            if str(negative_prompt or "").strip():
                payload["negative_prompt"] = str(negative_prompt).strip()
            if style != "none":
                payload["style"] = style
            seed_value = self.seed_payload_value(seed)
            if seed_value is not None:
                payload["seed"] = seed_value
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("fal-ai/pixverse/v6/image-to-video", payload, ["video"], pbar, poll_interval, max_poll_attempts)
            result_video_url = self.extract_video_url(result)
            if not result_video_url:
                raise RuntimeError("No video URL in result")
            pbar.update_absolute(100)
            return (FalVideoAdapter(result_video_url), result_video_url, self.info(result))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return ("", "", error_message)


class Comfly_creatify_aurora_fal(ComflyFalBase):
    LOG_PREFIX = "creatify_aurora_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image_url": ("STRING", {"default": ""}), "audio_url": ("STRING", {"default": ""})}, "optional": {
            "image": ("IMAGE",),
            "audio": ("AUDIO",),
            "api_key": ("STRING", {"default": ""}),
            "prompt": ("STRING", {"default": "", "multiline": True}),
            "guidance_scale": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.1}),
            "audio_guidance_scale": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 10.0, "step": 0.1}),
            "resolution": (["480p", "720p"], {"default": "480p"}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "audio_way": (["upload", "audio_url"], {"default": "upload"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def process(self, image_url="", audio_url="", image=None, audio=None, api_key="",
                prompt="", guidance_scale=1.0, audio_guidance_scale=2.0, resolution="480p",
                image_way="base64", audio_way="upload", poll_interval=6,
                max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            prepared_image = self.prepare_image(image, image_url, image_way)
            prepared_audio = self.prepare_audio(audio, audio_url, audio_way)
            if not prepared_image or not prepared_audio:
                raise RuntimeError("Creatify Aurora requires image/audio inputs or URLs.")
            payload = {
                "image_url": prepared_image,
                "audio_url": prepared_audio,
                "guidance_scale": float(guidance_scale),
                "audio_guidance_scale": float(audio_guidance_scale),
                "resolution": resolution,
            }
            if str(prompt or "").strip():
                payload["prompt"] = str(prompt).strip()
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("fal-ai/creatify/aurora", payload, ["video"], pbar, poll_interval, max_poll_attempts)
            result_video_url = self.extract_video_url(result)
            if not result_video_url:
                raise RuntimeError("No video URL in result")
            pbar.update_absolute(100)
            return (FalVideoAdapter(result_video_url), result_video_url, self.info(result))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return ("", "", error_message)


class Comfly_veed_fabric_1_0_fal(ComflyFalBase):
    LOG_PREFIX = "veed_fabric_1_0_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image_url": ("STRING", {"default": ""}), "audio_url": ("STRING", {"default": ""})}, "optional": {
            "image": ("IMAGE",),
            "audio": ("AUDIO",),
            "api_key": ("STRING", {"default": ""}),
            "resolution": (["480p", "720p"], {"default": "480p"}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "audio_way": (["upload", "audio_url"], {"default": "upload"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def process(self, image_url="", audio_url="", image=None, audio=None, api_key="",
                resolution="480p", image_way="base64", audio_way="upload",
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            prepared_image = self.prepare_image(image, image_url, image_way)
            prepared_audio = self.prepare_audio(audio, audio_url, audio_way)
            if not prepared_image or not prepared_audio:
                raise RuntimeError("Veed Fabric requires image/audio inputs or URLs.")
            payload = {"image_url": prepared_image, "audio_url": prepared_audio, "resolution": resolution}
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("veed/fabric-1.0", payload, ["video"], pbar, poll_interval, max_poll_attempts)
            result_video_url = self.extract_video_url(result)
            if not result_video_url:
                raise RuntimeError("No video URL in result")
            pbar.update_absolute(100)
            return (FalVideoAdapter(result_video_url), result_video_url, self.info(result))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return ("", "", error_message)


class Comfly_hunyuan_3d_v3_1_pro_fal(ComflyFalBase):
    LOG_PREFIX = "hunyuan_3d_v3_1_pro_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": "A small stylized spaceship"})}, "optional": {
            "mode": (["text_to_3d", "image_to_3d"], {"default": "text_to_3d"}),
            "front_image": ("IMAGE",),
            "back_image": ("IMAGE",),
            "left_image": ("IMAGE",),
            "right_image": ("IMAGE",),
            "front_image_url": ("STRING", {"default": ""}),
            "back_image_url": ("STRING", {"default": ""}),
            "left_image_url": ("STRING", {"default": ""}),
            "right_image_url": ("STRING", {"default": ""}),
            "api_key": ("STRING", {"default": ""}),
            "generate_type": (["Normal", "Geometry"], {"default": "Normal"}),
            "enable_pbr": ("BOOLEAN", {"default": False}),
            "face_count": ("INT", {"default": 500000, "min": 40000, "max": 1500000, "step": 10000}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("STRING", "STRING", "STRING", "FILE_3D")
    RETURN_NAMES = ("model_url", "response", "asset_urls", "model_3d")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"

    def process(self, prompt, mode="text_to_3d", front_image=None, back_image=None, left_image=None,
                right_image=None, front_image_url="", back_image_url="", left_image_url="",
                right_image_url="", api_key="", generate_type="Normal", enable_pbr=False,
                face_count=500000, image_way="base64", poll_interval=6,
                max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            payload = {"generate_type": generate_type, "enable_pbr": enable_pbr, "face_count": int(face_count)}
            endpoint = "fal-ai/hunyuan-3d/v3.1/pro/text-to-3d"
            if mode == "image_to_3d":
                front = self.prepare_image(front_image, front_image_url, image_way)
                if not front:
                    raise RuntimeError("Hunyuan image_to_3d requires front_image or front_image_url.")
                payload["input_image_url"] = front
                for key, img, url in (
                    ("back_image_url", back_image, back_image_url),
                    ("left_image_url", left_image, left_image_url),
                    ("right_image_url", right_image, right_image_url),
                ):
                    prepared = self.prepare_image(img, url, image_way)
                    if prepared:
                        payload[key] = prepared
                endpoint = "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d"
            else:
                payload["prompt"] = prompt
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll(endpoint, payload, ["model_glb", "model_urls"], pbar, poll_interval, max_poll_attempts)
            urls = self.extract_model_urls(result)
            model_url = self.choose_model_url(urls, "glb")
            if not model_url:
                raise RuntimeError("No model URL in result")
            model_3d = self.url_to_file_3d(model_url, "glb")
            pbar.update_absolute(100)
            return (model_url, self.info(result), "\n".join([u for u in urls if u != model_url]), model_3d)
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return ("", error_message, "", None)


class Comfly_trellis_2_fal(ComflyFalBase):
    LOG_PREFIX = "trellis_2_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image_url": ("STRING", {"default": ""})}, "optional": {
            "image1": ("IMAGE",),
            "image2": ("IMAGE",),
            "image3": ("IMAGE",),
            "api_key": ("STRING", {"default": ""}),
            "seed": ("INT", {"default": 0, "min": 0, "max": FAL_SEED_MAX, "tooltip": "0 = random seed. FAL seed max is 65535."}),
            "resolution": (["512", "1024", "1536"], {"default": "1024"}),
            "ss_sampling_steps": ("INT", {"default": 12, "min": 1, "max": 50, "step": 1}),
            "shape_slat_sampling_steps": ("INT", {"default": 12, "min": 1, "max": 50, "step": 1}),
            "tex_slat_sampling_steps": ("INT", {"default": 12, "min": 1, "max": 50, "step": 1}),
            "decimation_target": ("INT", {"default": 500000, "min": 20000, "max": 1000000, "step": 10000}),
            "texture_size": (["1024", "2048", "4096"], {"default": "2048"}),
            "remesh": ("BOOLEAN", {"default": True}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("STRING", "STRING", "STRING", "FILE_3D")
    RETURN_NAMES = ("model_url", "response", "asset_urls", "model_3d")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"

    def process(self, image_url="", image1=None, image2=None, image3=None, api_key="",
                seed=0, resolution="1024", ss_sampling_steps=12, shape_slat_sampling_steps=12,
                tex_slat_sampling_steps=12, decimation_target=500000, texture_size="2048",
                remesh=True, image_way="base64", poll_interval=6,
                max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            prepared_images = []
            first_external = str(image_url or "").strip()
            if first_external:
                prepared_images.append(first_external)
            for img in (image1, image2, image3):
                prepared = self.prepare_image(img, "", image_way)
                if prepared:
                    prepared_images.append(prepared)
            prepared_images = list(dict.fromkeys([u for u in prepared_images if u]))
            if not prepared_images:
                raise RuntimeError("Trellis 2 requires image or image_url.")
            payload = {
                "resolution": int(resolution),
                "ss_sampling_steps": int(ss_sampling_steps),
                "shape_slat_sampling_steps": int(shape_slat_sampling_steps),
                "tex_slat_sampling_steps": int(tex_slat_sampling_steps),
                "decimation_target": int(decimation_target),
                "texture_size": int(texture_size),
                "remesh": remesh,
            }
            seed_value = self.seed_payload_value(seed)
            if seed_value is not None:
                payload["seed"] = seed_value
            if len(prepared_images) > 1:
                payload["image_urls"] = prepared_images
            else:
                payload["image_url"] = prepared_images[0]
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("fal-ai/trellis-2", payload, ["model_glb", "model_urls"], pbar, poll_interval, max_poll_attempts)
            urls = self.extract_model_urls(result)
            model_url = self.choose_model_url(urls, "glb")
            if not model_url:
                raise RuntimeError("No model URL in result")
            model_3d = self.url_to_file_3d(model_url, "glb")
            pbar.update_absolute(100)
            return (model_url, self.info(result), "\n".join([u for u in urls if u != model_url]), model_3d)
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return ("", error_message, "", None)


class Comfly_bernini_r_video_fal(ComflyFalBase):
    LOG_PREFIX = "bernini_r_video_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": "A cinematic subtle motion shot."})}, "optional": {
            "mode": (["reference_to_video", "edit_video", "reference_edit_video"], {"default": "reference_to_video"}),
            "video": (IO.VIDEO,),
            "video_url": ("STRING", {"default": ""}),
            "reference_image1": ("IMAGE",),
            "reference_image2": ("IMAGE",),
            "reference_image3": ("IMAGE",),
            "reference_image4": ("IMAGE",),
            "reference_image5": ("IMAGE",),
            "reference_image_urls": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional reference image URLs, one per line. Up to 5 total."}),
            "api_key": ("STRING", {"default": ""}),
            "negative_prompt": ("STRING", {"default": "", "multiline": True}),
            "max_image_size": ("INT", {"default": 848, "min": 256, "max": 1280, "step": 8}),
            "num_frames": ("INT", {"default": 81, "min": 5, "max": 121, "step": 4, "tooltip": "Snapped internally to 4k+1. Use 5 for lowest-cost smoke."}),
            "frames_per_second": ("INT", {"default": 16, "min": 4, "max": 30, "step": 1}),
            "num_inference_steps": ("INT", {"default": 30, "min": 1, "max": 50, "step": 1}),
            "acceleration": (["none", "regular"], {"default": "none"}),
            "aspect_ratio": (["16:9", "9:16", "1:1"], {"default": "16:9", "tooltip": "reference_to_video mode only."}),
            "enable_prompt_expansion": ("BOOLEAN", {"default": False}),
            "seed": ("INT", {"default": 0, "min": 0, "max": FAL_SEED_MAX, "tooltip": "0 = random seed. FAL seed max is 65535."}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "video_way": (["upload", "video_url"], {"default": "upload"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def process(self, prompt, mode="reference_to_video", video=None, video_url="", reference_image1=None,
                reference_image2=None, reference_image3=None, reference_image4=None, reference_image5=None,
                reference_image_urls="", api_key="", negative_prompt="", max_image_size=848,
                num_frames=81, frames_per_second=16, num_inference_steps=30, acceleration="none",
                aspect_ratio="16:9", enable_prompt_expansion=False, seed=0, image_way="base64",
                video_way="upload", poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")

            payload = {
                "prompt": prompt,
                "max_image_size": int(max_image_size),
                "num_frames": int(num_frames),
                "frames_per_second": int(frames_per_second),
                "num_inference_steps": int(num_inference_steps),
                "acceleration": acceleration,
                "enable_prompt_expansion": bool(enable_prompt_expansion),
            }
            if str(negative_prompt or "").strip():
                payload["negative_prompt"] = str(negative_prompt).strip()
            seed_value = self.seed_payload_value(seed)
            if seed_value is not None:
                payload["seed"] = seed_value

            endpoint = "fal-ai/bernini-r/reference-to-video"
            if mode in ("reference_to_video", "reference_edit_video"):
                references = self.prepare_image_list(
                    [
                        (reference_image1, ""),
                        (reference_image2, ""),
                        (reference_image3, ""),
                        (reference_image4, ""),
                        (reference_image5, ""),
                    ],
                    reference_image_urls,
                    image_way,
                    max_count=5,
                )
                if not references:
                    raise RuntimeError(f"{mode} mode requires at least one reference image or reference_image_url.")
                payload["reference_image_urls"] = references

            if mode == "reference_to_video":
                payload["aspect_ratio"] = aspect_ratio
            elif mode == "edit_video":
                endpoint = "fal-ai/bernini-r/edit-video"
                prepared_video = self.prepare_video(video, video_url, video_way)
                if not prepared_video:
                    raise RuntimeError("edit_video mode requires video input or video_url.")
                payload["video_url"] = prepared_video
            elif mode == "reference_edit_video":
                endpoint = "fal-ai/bernini-r/reference-edit-video"
                prepared_video = self.prepare_video(video, video_url, video_way)
                if not prepared_video:
                    raise RuntimeError("reference_edit_video mode requires video input or video_url.")
                payload["video_url"] = prepared_video
            else:
                raise RuntimeError(f"Unsupported mode: {mode}")

            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll(endpoint, payload, ["video"], pbar, poll_interval, max_poll_attempts)
            result_video_url = self.extract_video_url(result)
            if not result_video_url:
                raise RuntimeError("No video URL in result")
            pbar.update_absolute(100)
            return (FalVideoAdapter(result_video_url), result_video_url, self.info(result))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return ("", "", error_message)


class Comfly_bernini_r_edit_image_fal(ComflyFalBase):
    LOG_PREFIX = "bernini_r_edit_image_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": "Make the image more cinematic."})}, "optional": {
            "image": ("IMAGE",),
            "image_url": ("STRING", {"default": ""}),
            "api_key": ("STRING", {"default": ""}),
            "negative_prompt": ("STRING", {"default": "", "multiline": True}),
            "max_image_size": ("INT", {"default": 848, "min": 256, "max": 1280, "step": 8}),
            "num_inference_steps": ("INT", {"default": 30, "min": 1, "max": 50, "step": 1}),
            "enable_prompt_expansion": ("BOOLEAN", {"default": False}),
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

    def process(self, prompt, image=None, image_url="", api_key="", negative_prompt="",
                max_image_size=848, num_inference_steps=30, enable_prompt_expansion=False,
                seed=0, image_way="base64", poll_interval=6, max_poll_attempts=600,
                skip_error=False):
        self.set_api_key(api_key)
        default_image = image if image is not None else self.blank_image()
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            prepared_image = self.prepare_image(image, image_url, image_way)
            if not prepared_image:
                raise RuntimeError("Bernini R Edit Image requires image or image_url.")
            payload = {
                "prompt": prompt,
                "image_url": prepared_image,
                "max_image_size": int(max_image_size),
                "num_inference_steps": int(num_inference_steps),
                "enable_prompt_expansion": bool(enable_prompt_expansion),
            }
            if str(negative_prompt or "").strip():
                payload["negative_prompt"] = str(negative_prompt).strip()
            seed_value = self.seed_payload_value(seed)
            if seed_value is not None:
                payload["seed"] = seed_value
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("fal-ai/bernini-r/edit-image", payload, ["image", "images"], pbar, poll_interval, max_poll_attempts)
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


class Comfly_luma_ray_v3_2_fal(ComflyFalBase):
    LOG_PREFIX = "luma_ray_v3_2_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": "A smooth cinematic camera move."})}, "optional": {
            "mode": (["text_to_video", "image_to_video"], {"default": "text_to_video"}),
            "image": ("IMAGE",),
            "end_image": ("IMAGE",),
            "reference_image1": ("IMAGE",),
            "reference_image2": ("IMAGE",),
            "reference_image3": ("IMAGE",),
            "reference_image4": ("IMAGE",),
            "image_url": ("STRING", {"default": ""}),
            "end_image_url": ("STRING", {"default": ""}),
            "reference_image_urls": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional reference image URLs, one per line. Max 4."}),
            "api_key": ("STRING", {"default": ""}),
            "duration": (["5s", "10s"], {"default": "5s"}),
            "resolution": (["540p", "720p", "1080p"], {"default": "540p"}),
            "aspect_ratio": (["3:4", "4:3", "1:1", "9:16", "16:9", "21:9"], {"default": "16:9"}),
            "hdr": ("BOOLEAN", {"default": False}),
            "exr_export": ("BOOLEAN", {"default": False}),
            "loop": ("BOOLEAN", {"default": False}),
            "keyframes_json": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional JSON array of keyframe image URLs."}),
            "keyframe_indexes_json": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional JSON array of integer frame indexes."}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def process(self, prompt, mode="text_to_video", image=None, end_image=None,
                reference_image1=None, reference_image2=None, reference_image3=None,
                reference_image4=None, image_url="", end_image_url="",
                reference_image_urls="", api_key="", duration="5s", resolution="540p",
                aspect_ratio="16:9", hdr=False, exr_export=False, loop=False,
                keyframes_json="", keyframe_indexes_json="", image_way="base64",
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            payload = {
                "prompt": prompt,
                "duration": duration,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "hdr": bool(hdr),
                "exr_export": bool(exr_export),
                "loop": bool(loop),
            }
            references = self.prepare_image_list(
                [
                    (reference_image1, ""),
                    (reference_image2, ""),
                    (reference_image3, ""),
                    (reference_image4, ""),
                ],
                reference_image_urls,
                image_way,
                max_count=4,
            )
            if references:
                payload["reference_image_urls"] = references

            endpoint = "luma/agent/ray/v3.2/text-to-video"
            if mode == "image_to_video":
                endpoint = "luma/agent/ray/v3.2/image-to-video"
                keyframes = self.parse_json_field(keyframes_json, "keyframes_json", list)
                keyframe_indexes = self.parse_json_field(keyframe_indexes_json, "keyframe_indexes_json", list)
                if keyframes is not None or keyframe_indexes is not None:
                    if not keyframes or not keyframe_indexes:
                        raise RuntimeError("keyframes_json and keyframe_indexes_json must be provided together.")
                    payload["keyframes"] = keyframes
                    payload["keyframe_indexes"] = keyframe_indexes
                else:
                    if duration == "10s":
                        raise RuntimeError("Luma image_to_video duration=10s requires keyframes_json and keyframe_indexes_json.")
                    prepared_image = self.prepare_image(image, image_url, image_way)
                    if not prepared_image:
                        raise RuntimeError("image_to_video mode requires image/image_url or keyframes_json.")
                    payload["image_url"] = prepared_image
                    prepared_end = self.prepare_image(end_image, end_image_url, image_way)
                    if prepared_end:
                        payload["end_image_url"] = prepared_end
                    if loop and prepared_end:
                        raise RuntimeError("loop cannot be combined with end_image/end_image_url.")
            elif mode != "text_to_video":
                raise RuntimeError(f"Unsupported mode: {mode}")

            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll(endpoint, payload, ["video"], pbar, poll_interval, max_poll_attempts)
            result_video_url = self.extract_video_url(result)
            if not result_video_url:
                raise RuntimeError("No video URL in result")
            pbar.update_absolute(100)
            return (FalVideoAdapter(result_video_url), result_video_url, self.info(result))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return ("", "", error_message)


class Comfly_luma_uni_1_v1_fal(ComflyFalBase):
    LOG_PREFIX = "luma_uni_1_v1_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": "A clean editorial image with strong composition."})}, "optional": {
            "mode": (["text_to_image", "text_to_image_max", "edit", "edit_max"], {"default": "text_to_image"}),
            "image": ("IMAGE",),
            "reference_image1": ("IMAGE",),
            "reference_image2": ("IMAGE",),
            "reference_image3": ("IMAGE",),
            "reference_image4": ("IMAGE",),
            "image_url": ("STRING", {"default": ""}),
            "reference_image_urls": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional reference image URLs, one per line. Max 9."}),
            "api_key": ("STRING", {"default": ""}),
            "aspect_ratio": (["auto", "3:1", "2:1", "16:9", "3:2", "1:1", "2:3", "9:16", "1:2", "1:3"], {"default": "16:9"}),
            "output_format": (["auto", "png", "jpeg"], {"default": "png"}),
            "style": (["auto", "manga"], {"default": "auto"}),
            "enable_web_search": ("BOOLEAN", {"default": False, "tooltip": "Text-to-image modes only."}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("images", "response", "image_urls")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"

    def process(self, prompt, mode="text_to_image", image=None, reference_image1=None,
                reference_image2=None, reference_image3=None, reference_image4=None,
                image_url="", reference_image_urls="", api_key="", aspect_ratio="16:9",
                output_format="png", style="auto", enable_web_search=False,
                image_way="base64", poll_interval=6, max_poll_attempts=600,
                skip_error=False):
        self.set_api_key(api_key)
        default_image = image if image is not None else self.blank_image()
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            payload = {"prompt": prompt, "style": style}
            if output_format != "auto":
                payload["output_format"] = output_format
            references = self.prepare_image_list(
                [
                    (reference_image1, ""),
                    (reference_image2, ""),
                    (reference_image3, ""),
                    (reference_image4, ""),
                ],
                reference_image_urls,
                image_way,
                max_count=9,
            )
            if references:
                payload["reference_image_urls"] = references

            endpoint_map = {
                "text_to_image": "luma/agent/uni-1/v1/text-to-image",
                "text_to_image_max": "luma/agent/uni-1/v1/max",
                "edit": "luma/agent/uni-1/v1/edit",
                "edit_max": "luma/agent/uni-1/v1/max/edit",
            }
            endpoint = endpoint_map.get(mode)
            if not endpoint:
                raise RuntimeError(f"Unsupported mode: {mode}")
            if mode.startswith("text_to_image"):
                if aspect_ratio != "auto":
                    payload["aspect_ratio"] = aspect_ratio
                payload["enable_web_search"] = bool(enable_web_search)
            else:
                prepared_image = self.prepare_image(image, image_url, image_way)
                if not prepared_image:
                    raise RuntimeError(f"{mode} mode requires image or image_url.")
                payload["image_url"] = prepared_image

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


class Comfly_bria_video_background_removal_v3_fal(ComflyFalBase):
    LOG_PREFIX = "bria_video_background_removal_v3_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"video_url": ("STRING", {"default": "", "tooltip": "Public video URL. Ignored when video input is connected."})}, "optional": {
            "video": (IO.VIDEO,),
            "api_key": ("STRING", {"default": ""}),
            "background_color": (["Transparent", "Black", "White", "Gray", "Red", "Green", "Blue", "Yellow", "Cyan", "Magenta", "Orange"], {"default": "Black"}),
            "preserve_audio": ("BOOLEAN", {"default": True}),
            "output_container_and_codec": (["mp4_h265", "mp4_h264", "webm_vp9", "mov_h265", "mov_proresks", "mkv_h265", "mkv_h264", "mkv_vp9", "avi_h264", "gif"], {"default": "webm_vp9"}),
            "video_way": (["upload", "video_url"], {"default": "upload"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def process(self, video_url="", video=None, api_key="", background_color="Black",
                preserve_audio=True, output_container_and_codec="webm_vp9", video_way="upload",
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            prepared_video = self.prepare_video(video, video_url, video_way)
            if not prepared_video:
                raise RuntimeError("Bria video background removal requires video input or video_url.")
            payload = {
                "video_url": prepared_video,
                "background_color": background_color,
                "preserve_audio": bool(preserve_audio),
                "output_container_and_codec": output_container_and_codec,
            }
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("bria/video/background-removal/v3", payload, ["video"], pbar, poll_interval, max_poll_attempts)
            result_video_url = self.extract_video_url(result)
            if not result_video_url:
                raise RuntimeError("No video URL in result")
            pbar.update_absolute(100)
            return (FalVideoAdapter(result_video_url), result_video_url, self.info(result))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return ("", "", error_message)


class Comfly_nemotron_asr_multilingual_fal(ComflyFalBase):
    LOG_PREFIX = "nemotron_asr_multilingual_fal"

    LANGUAGES = [
        "auto", "en-US", "en-GB", "es-US", "es-ES", "de-DE", "fr-FR", "fr-CA",
        "it-IT", "ar-AR", "ja-JP", "ko-KR", "pt-BR", "pt-PT", "ru-RU", "hi-IN",
        "zh-CN", "vi-VN", "he-IL", "nl-NL", "cs-CZ", "da-DK", "pl-PL", "nn-NO",
        "nb-NO", "sv-SE", "th-TH", "tr-TR", "bg-BG", "el-GR", "et-EE", "fi-FI",
        "hr-HR", "hu-HU", "lt-LT", "lv-LV", "ro-RO", "sk-SK", "uk-UA", "mt-MT",
        "sl-SI",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"audio_url": ("STRING", {"default": "", "tooltip": "Public audio URL. Ignored when AUDIO input is connected."})}, "optional": {
            "audio": ("AUDIO",),
            "api_key": ("STRING", {"default": ""}),
            "language": (cls.LANGUAGES, {"default": "auto"}),
            "acceleration": (["none", "regular", "high", "full"], {"default": "regular"}),
            "audio_way": (["upload", "audio_url"], {"default": "upload"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("transcript", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"

    def process(self, audio_url="", audio=None, api_key="", language="auto", acceleration="regular",
                audio_way="upload", poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            prepared_audio = self.prepare_audio(audio, audio_url, audio_way)
            if not prepared_audio:
                raise RuntimeError("Nemotron ASR requires AUDIO input or audio_url.")
            payload = {"audio_url": prepared_audio, "language": language, "acceleration": acceleration}
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("nvidia/nemotron-asr-multilingual/asr", payload, ["output"], pbar, poll_interval, max_poll_attempts)
            transcript = ""
            if isinstance(result, dict):
                transcript = str(result.get("output") or "")
            pbar.update_absolute(100)
            return (transcript, self.info(result))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return ("", error_message)


class Comfly_bria_genfill_v2_fal(ComflyFalBase):
    LOG_PREFIX = "bria_genfill_v2_fal"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"instruction": ("STRING", {"multiline": True, "default": "A beautiful colorful butterfly"})}, "optional": {
            "image": ("IMAGE",),
            "mask": ("IMAGE",),
            "image_url": ("STRING", {"default": ""}),
            "mask_url": ("STRING", {"default": ""}),
            "api_key": ("STRING", {"default": ""}),
            "seed": ("INT", {"default": 5555, "min": 0, "max": FAL_SEED_MAX, "tooltip": "0 = random seed. FAL seed max is 65535."}),
            "steps_num": ("INT", {"default": 30, "min": 20, "max": 50, "step": 1}),
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

    def process(self, instruction, image=None, mask=None, image_url="", mask_url="", api_key="",
                seed=5555, steps_num=30, sync_mode=False, image_way="base64",
                poll_interval=6, max_poll_attempts=600, skip_error=False):
        self.set_api_key(api_key)
        default_image = image if image is not None else self.blank_image()
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            prepared_image = self.prepare_image(image, image_url, image_way)
            prepared_mask = self.prepare_image(mask, mask_url, image_way)
            if not prepared_image or not prepared_mask:
                raise RuntimeError("Bria GenFill requires image/mask inputs or image_url/mask_url.")
            payload = {
                "image_url": prepared_image,
                "mask_url": prepared_mask,
                "instruction": instruction,
                "steps_num": int(steps_num),
                "sync_mode": bool(sync_mode),
            }
            seed_value = self.seed_payload_value(seed)
            if seed_value is not None:
                payload["seed"] = seed_value
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("bria/genfill/v2", payload, ["image", "images"], pbar, poll_interval, max_poll_attempts)
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


class Comfly_luma_ray_v3_2_video_to_video_fal(ComflyFalBase):
    LOG_PREFIX = "luma_ray_v3_2_video_to_video_fal"

    EDIT_STRENGTHS = ["auto", "adhere_1", "adhere_2", "adhere_3", "flex_1", "flex_2", "flex_3", "reimagine_1", "reimagine_2", "reimagine_3"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"multiline": True, "default": "Restyle the footage as a hand-painted watercolor animation."})}, "optional": {
            "video": (IO.VIDEO,),
            "video_url": ("STRING", {"default": ""}),
            "start_image": ("IMAGE",),
            "start_image_url": ("STRING", {"default": ""}),
            "api_key": ("STRING", {"default": ""}),
            "duration": (["5s", "10s"], {"default": "5s"}),
            "resolution": (["540p", "720p", "1080p"], {"default": "540p"}),
            "edit_strength": (cls.EDIT_STRENGTHS, {"default": "auto"}),
            "auto_controls": ("BOOLEAN", {"default": False}),
            "hdr": ("BOOLEAN", {"default": False}),
            "exr_export": ("BOOLEAN", {"default": False}),
            "controls_json": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional JSON object for Ray edit controls."}),
            "keyframes_json": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional JSON array of keyframe image URLs."}),
            "keyframe_indexes_json": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional JSON array of integer source frame indexes."}),
            "image_way": (["base64", "image_url"], {"default": "base64"}),
            "video_way": (["upload", "video_url"], {"default": "upload"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def process(self, prompt, video=None, video_url="", start_image=None, start_image_url="",
                api_key="", duration="5s", resolution="540p", edit_strength="auto",
                auto_controls=False, hdr=False, exr_export=False, controls_json="",
                keyframes_json="", keyframe_indexes_json="", image_way="base64",
                video_way="upload", poll_interval=6, max_poll_attempts=600,
                skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            prepared_video = self.prepare_video(video, video_url, video_way)
            if not prepared_video:
                raise RuntimeError("Luma Ray video-to-video requires video input or video_url.")
            payload = {
                "prompt": prompt,
                "video_url": prepared_video,
                "duration": duration,
                "resolution": resolution,
                "hdr": bool(hdr),
                "exr_export": bool(exr_export),
                "auto_controls": bool(auto_controls),
            }
            if not auto_controls and edit_strength != "auto":
                payload["edit_strength"] = edit_strength
            controls = self.parse_json_field(controls_json, "controls_json", dict)
            if controls:
                if auto_controls:
                    raise RuntimeError("controls_json cannot be combined with auto_controls=True.")
                payload["controls"] = controls
            keyframes = self.parse_json_field(keyframes_json, "keyframes_json", list)
            keyframe_indexes = self.parse_json_field(keyframe_indexes_json, "keyframe_indexes_json", list)
            if keyframes is not None or keyframe_indexes is not None:
                if not keyframes or not keyframe_indexes:
                    raise RuntimeError("keyframes_json and keyframe_indexes_json must be provided together.")
                payload["keyframes"] = keyframes
                payload["keyframe_indexes"] = keyframe_indexes
            else:
                prepared_start = self.prepare_image(start_image, start_image_url, image_way)
                if prepared_start:
                    payload["start_image_url"] = prepared_start

            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("luma/agent/ray/v3.2/video-to-video", payload, ["video"], pbar, poll_interval, max_poll_attempts)
            result_video_url = self.extract_video_url(result)
            if not result_video_url:
                raise RuntimeError("No video URL in result")
            pbar.update_absolute(100)
            return (FalVideoAdapter(result_video_url), result_video_url, self.info(result))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return ("", "", error_message)


class Comfly_pixelcut_video_background_removal_fal(ComflyFalBase):
    LOG_PREFIX = "pixelcut_video_background_removal_fal"

    OUTPUT_FORMATS = ["auto", "webm_vp9", "mp4_h264", "mp4_h265", "mov_proresks", "mov_h265", "mkv_h264", "mkv_h265", "mkv_vp9", "gif"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"video_url": ("STRING", {"default": "", "tooltip": "Public video URL. Ignored when video input is connected."})}, "optional": {
            "video": (IO.VIDEO,),
            "api_key": ("STRING", {"default": ""}),
            "background": (["transparent", "black", "white", "green", "blue", "magenta", "custom"], {"default": "transparent"}),
            "output_format": (cls.OUTPUT_FORMATS, {"default": "auto"}),
            "custom_r": ("INT", {"default": 0, "min": 0, "max": 255}),
            "custom_g": ("INT", {"default": 0, "min": 0, "max": 255}),
            "custom_b": ("INT", {"default": 0, "min": 0, "max": 255}),
            "video_way": (["upload", "video_url"], {"default": "upload"}),
            "poll_interval": ("INT", {"default": 6, "min": 1, "max": 60, "step": 1}),
            "max_poll_attempts": ("INT", {"default": 600, "min": 10, "max": 3600, "step": 10, "tooltip": "Default 600*6s = 3600s timeout."}),
            "skip_error": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "response")
    FUNCTION = "process"
    CATEGORY = "zhenzhen/FAL"
    OUTPUT_NODE = True

    def process(self, video_url="", video=None, api_key="", background="transparent",
                output_format="auto", custom_r=0, custom_g=0, custom_b=0,
                video_way="upload", poll_interval=6, max_poll_attempts=600,
                skip_error=False):
        self.set_api_key(api_key)
        try:
            if not self.api_key:
                raise RuntimeError("API key not provided. Please set your API key.")
            prepared_video = self.prepare_video(video, video_url, video_way)
            if not prepared_video:
                raise RuntimeError("Pixelcut video background removal requires video input or video_url.")
            payload = {"video_url": prepared_video, "background": background}
            if output_format != "auto":
                payload["output_format"] = output_format
            if background == "custom":
                payload["background_color"] = {"r": int(custom_r), "g": int(custom_g), "b": int(custom_b)}
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            result = self.submit_and_poll("pixelcut/video-background-removal", payload, ["video"], pbar, poll_interval, max_poll_attempts)
            result_video_url = self.extract_video_url(result)
            if not result_video_url:
                raise RuntimeError("No video URL in result")
            pbar.update_absolute(100)
            return (FalVideoAdapter(result_video_url), result_video_url, self.info(result))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self._log(error_message)
            if not skip_error:
                raise
            return ("", "", error_message)


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
