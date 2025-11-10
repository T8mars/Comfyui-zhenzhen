import os
import io
import math
import random
import tempfile
import torch
import torchaudio
import requests
import nest_asyncio
import time
import numpy as np
from PIL import Image
from io import BytesIO
import json
import comfy.utils
import re
import aiohttp
import asyncio
import base64
import uuid
import folder_paths
import mimetypes
import cv2
import shutil
import subprocess
import threading
import concurrent.futures
from .utils import pil2tensor, tensor2pil
from comfy.utils import common_upscale
from comfy.comfy_types import IO
from typing import Optional, Any
#from comfy_api_nodes.apinode_utils import download_url_to_video_output
import asyncio
from comfy_api.input import VideoInput
from comfy_api.input_impl import VideoFromFile
from comfy_api.util import VideoComponents
from comfy_api.input_impl import VideoFromComponents
from fractions import Fraction


def get_config():
    try:
        config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'Comflyapi.json')
        with open(config_path, 'r') as f:  
            config = json.load(f)
        return config
    except:
        return {}

def save_config(config):
    config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'Comflyapi.json')
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)



class Comfly_api_set:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_base": (["zhenzhen", "ip", "hk", "us"], {"default": "zhenzhen"}),
                "apikey": ("STRING", {"default": ""}),
            },
            "optional": {
                "custom_ip": ("STRING", {"default": "", "placeholder": "Enter IP when using 'ip' option (e.g. http://104.194.8.112:9088)"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("apikey",)
    FUNCTION = "set_api_base"
    CATEGORY = "Comfly"

    def set_api_base(self, api_base, apikey="", custom_ip=""):
        global baseurl
        
        base_url_mapping = {
            "zhenzhen": "https://ai.t8star.cn",
            "ip": custom_ip,
            "hk": "https://hk-api.gptbest.vip",
            "us": "https://api.gptbest.vip"
        }
        
        if api_base == "ip" and not custom_ip.strip():
            raise ValueError("When selecting 'ip' option, you must provide a custom IP address in the 'custom_ip' field")
        
        if api_base in base_url_mapping:
            baseurl = base_url_mapping[api_base]
            
        if apikey.strip():
            config = get_config()
            config['api_key'] = apikey
            save_config(config)
            
        message = f"API Base URL set to: {baseurl}"
        if apikey.strip():
            message += "\nAPI key has been updated"
            
        print(message)
        return (apikey,)


class ComflyVideoAdapter:
    def __init__(self, video_path_or_url):
        if video_path_or_url.startswith('http'):
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
        else:
            try: 
                cap = cv2.VideoCapture(self.video_path)
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
                return width, height
            except Exception as e:
                print(f"Error getting video dimensions: {str(e)}")
                return 1280, 720
            
    def save_to(self, output_path, format="auto", codec="auto", metadata=None):
        if self.is_url:
            try:
                response = requests.get(self.video_url, stream=True)
                response.raise_for_status()
                
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
            except Exception as e:
                print(f"Error downloading video from URL: {str(e)}")
                return False
        else:
            try:
                shutil.copyfile(self.video_path, output_path)
                return True
            except Exception as e:
                print(f"Error saving video: {str(e)}")
                return False


def create_audio_object(audio_url):
    """Create an audio object compatible with ComfyUI's audio nodes"""
    if not audio_url:
        return {
            "waveform": torch.zeros((1, 1, 44100)),  
            "sample_rate": 44100
        }
        
    try:
        temp_dir = os.path.join(folder_paths.get_temp_directory(), "suno_audio")
        os.makedirs(temp_dir, exist_ok=True)
        temp_file = os.path.join(temp_dir, f"suno_{str(uuid.uuid4())[:8]}.mp3")
        
        response = requests.get(audio_url, stream=True)
        response.raise_for_status()
        
        with open(temp_file, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        try:
            waveform, sample_rate = torchaudio.load(temp_file)
            if len(waveform.shape) == 2:  
                waveform = waveform.unsqueeze(0)  
            
            return {
                "waveform": waveform,
                "sample_rate": sample_rate
            }
        except Exception as e:
            print(f"Error loading audio with torchaudio: {str(e)}")

            try:
                if hasattr(folder_paths, "get_ffmpeg_path"):
                    ffmpeg_path = folder_paths.get_ffmpeg_path()
                else:
                    ffmpeg_path = shutil.which("ffmpeg")
                
                if ffmpeg_path:
                    temp_wav = temp_file.replace(".mp3", ".wav")
                    subprocess.run([ffmpeg_path, "-y", "-i", temp_file, temp_wav], 
                                  check=True, capture_output=True)

                    waveform, sample_rate = torchaudio.load(temp_wav)
                    if len(waveform.shape) == 2:  
                        waveform = waveform.unsqueeze(0)  

                    try:
                        os.remove(temp_wav)
                    except:
                        pass
                        
                    return {
                        "waveform": waveform,
                        "sample_rate": sample_rate
                    }
                else:
                    raise Exception("ffmpeg not found, can't process audio")
            except Exception as ffmpeg_error:
                print(f"Error with ffmpeg conversion: {str(ffmpeg_error)}")

                return {
                    "waveform": torch.zeros((1, 1, 44100)),  
                    "sample_rate": 44100,
                    "url": audio_url  
                }
        
    except Exception as e:
        print(f"Error downloading or processing audio: {str(e)}")

    return {
        "waveform": torch.zeros((1, 1, 44100)),
        "sample_rate": 44100
    }



############################# Midjourney ###########################

class ComflyBaseNode:
    def __init__(self):
        self.midjourney_api_url = {
            "turbo mode": f"{baseurl}/mj-turbo",
            "fast mode": f"{baseurl}/mj-fast",
            "relax mode": f"{baseurl}/mj-relax"
        }
        self.api_key = get_config().get('api_key', '') 
        self.speed = "fast mode"
        self.timeout = 800

    def set_speed(self, speed):
        self.speed = speed

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key
        }

    def generateUUID(self):
        return str(uuid.uuid4())

    async def midjourney_submit_action(self, action, taskId, index, custom_id):
        headers = self.get_headers()
        payload = {
            "customId": custom_id,
            "taskId": taskId
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.midjourney_api_url[self.speed]}/mj/submit/action", headers=headers, json=payload, timeout=self.timeout) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()

                            if data.get("status") == "FAILURE":
                                fail_reason = data.get("fail_reason", "Unknown failure reason")
                                error_message = f"Action submission failed: {fail_reason}"
                                print(error_message)
                                raise Exception(error_message)
                                
                            return data
                        except aiohttp.client_exceptions.ContentTypeError:
                            text_response = await response.text()
                            
                            try:
                                import json
                                data = json.loads(text_response)

                                if data.get("status") == "FAILURE":
                                    fail_reason = data.get("fail_reason", "Unknown failure reason")
                                    error_message = f"Action submission failed: {fail_reason}"
                                    print(error_message)
                                    raise Exception(error_message)
                                    
                                return data
                            except json.JSONDecodeError:
                                if text_response and len(text_response) < 100:
                                    return {"result": text_response.strip()}
                                raise Exception(f"Invalid response format: {text_response}")
                    else:
                        error_message = f"Error submitting Midjourney action: {response.status}"
                        try:
                            error_details = await response.text()
                            error_message += f" - {error_details}"
                        except:
                            pass
                        raise Exception(error_message)
        except asyncio.TimeoutError:
            error_message = f"Timeout error: Request to submit action timed out after {self.timeout} seconds"
            raise Exception(error_message)
        except Exception as e:
            if "Action submission failed" in str(e):
                raise 
            print(f"Exception in midjourney_submit_action: {str(e)}")
            raise e


    def extract_taskId(self, U, action, index):
        pattern = fr'"customId": "MJ::JOB::{action}::{index}::(.*?)"'
        match = re.search(pattern, U)
        if match:
            return match.group(1)
        else:
            raise ValueError(f"Invalid custom ID format in U: {U}")

    async def midjourney_submit_imagine_task(self, prompt, ar, no, c, s, iw, tile, r, video, sw, cw, sv, seed):
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key
        }
        payload = {
            "base64Array": [],
            "instanceId": "",
            "modes": [],
            "notifyHook": "",
            "prompt": prompt,
            "remix": True,
            "state": "",
            "ar": ar,
            "no": no,
            "c": c,
            "s": s,
            "iw": iw,
            "tile": tile,
            "r": r,
            "video": video,
            "sw": sw,
            "cw": cw,
            "sv": sv,
            "seed": seed
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.midjourney_api_url[self.speed]}/mj/submit/imagine", headers=headers, json=payload, timeout=self.timeout) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()

                            if data.get("status") == "FAILURE":
                                fail_reason = data.get("fail_reason", "Unknown failure reason")
                                error_message = f"Midjourney task failed: {fail_reason}"
                                print(error_message)
                                raise Exception(error_message)
                                
                            return data["result"]
                        except aiohttp.client_exceptions.ContentTypeError:
                            text_response = await response.text()
                            
                            try:
                                import json
                                data = json.loads(text_response)
 
                                if data.get("status") == "FAILURE":
                                    fail_reason = data.get("fail_reason", "Unknown failure reason")
                                    error_message = f"Midjourney task failed: {fail_reason}"
                                    print(error_message)
                                    raise Exception(error_message)
                                    
                                return data["result"]
                            except (json.JSONDecodeError, KeyError):
                                if text_response and len(text_response) < 100:
                                    return text_response.strip()
                                raise Exception(f"Server returned invalid response: {text_response}")
                    else:
                        error_message = f"Error submitting Midjourney task: {response.status}"
                        try:
                            error_details = await response.text()
                            error_message += f" - {error_details}"
                        except:
                            pass
                        raise Exception(error_message)
        except asyncio.TimeoutError:
            error_message = f"Timeout error: Request to submit imagine task timed out after {self.timeout} seconds"
            raise Exception(error_message)
        except Exception as e:
            if "Midjourney task failed" in str(e):
                raise  
            print(f"Exception in midjourney_submit_imagine_task: {str(e)}")
            raise e


    async def midjourney_fetch_task_result(self, taskId):
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.midjourney_api_url[self.speed]}/mj/task/{taskId}/fetch", headers=headers, timeout=self.timeout) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            return data
                        except aiohttp.client_exceptions.ContentTypeError:
                            text_response = await response.text()
                            try:
                                import json
                                data = json.loads(text_response)
                                return data
                            except json.JSONDecodeError:
                                if text_response and len(text_response) < 100:
                                    return {"status": "SUCCESS", "progress": "100%", "imageUrl": text_response.strip()}
                                raise Exception(f"Server returned invalid response: {text_response}")
                    else:
                        error_message = f"Error fetching Midjourney task result: {response.status}"
                        try:
                            error_details = await response.text()
                            error_message += f" - {error_details}"
                        except:
                            pass
                        raise Exception(error_message)
        except asyncio.TimeoutError:
            error_message = f"Timeout error: Request to fetch task result timed out after {self.timeout} seconds"
            raise Exception(error_message)



class Comfly_upload(ComflyBaseNode):
    """
    Comfly_upload node
    Uploads an image to Midjourney and returns the URL link.
    Inputs:
        image (IMAGE): Input image to be uploaded.
    Outputs:
        url (STRING): URL link of the uploaded image.
    """
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "api_key": ("STRING", {"default": ""}),
            },
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("url",)
    FUNCTION = "upload_image"
    CATEGORY = "Comfly-v2/Midjourney"

    async def upload_image_to_midjourney(self, image):

        image = tensor2pil(image)[0]
        buffered = BytesIO()
        image_format = "PNG" 
        image.save(buffered, format=image_format)
        image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        payload = {
            "base64Array": [f"data:image/{image_format.lower()};base64,{image_base64}"],
            "instanceId": "",
            "notifyHook": ""
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.midjourney_api_url[self.speed]}/mj/submit/upload-discord-images", headers=self.get_headers(), json=payload, timeout=self.timeout) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()

                            if data.get("status") == "FAILURE":
                                fail_reason = data.get("fail_reason", "Unknown failure reason")
                                error_message = f"Image upload failed: {fail_reason}"
                                print(error_message)
                                raise Exception(error_message)
                                
                            if "result" in data and data["result"]:
                                return data["result"][0]
                            else:
                                error_message = f"Unexpected response from Midjourney API: {data}"
                                raise Exception(error_message)
                        except aiohttp.client_exceptions.ContentTypeError:
                            text_response = await response.text()
                            try:
                                import json
                                data = json.loads(text_response)
                                if data.get("status") == "FAILURE":
                                    fail_reason = data.get("fail_reason", "Unknown failure reason")
                                    error_message = f"Image upload failed: {fail_reason}"
                                    print(error_message)
                                    raise Exception(error_message)
                                    
                                if "result" in data and data["result"]:
                                    return data["result"][0]
                            except (json.JSONDecodeError, KeyError):
                                if text_response and len(text_response) < 100:
                                    return text_response.strip()
                                raise Exception(f"Invalid response format: {text_response}")
                    else:
                        error_message = f"Error uploading image to Midjourney: {response.status}"
                        try:
                            error_details = await response.text()
                            error_message += f" - {error_details}"
                        except:
                            pass
                        raise Exception(error_message)
                        
        except asyncio.TimeoutError:
            error_message = f"Timeout error: Request to upload image timed out after {self.timeout} seconds"
            raise Exception(error_message)
        
    def upload_image(self, image, api_key=""):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        try:
            pil_image = tensor2pil(image)[0]
            buffered = BytesIO()
            pil_image.save(buffered, format="PNG")
            image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            payload = {
                "base64Array": [f"data:image/png;base64,{image_base64}"],
                "instanceId": "",
                "notifyHook": ""
            }
            
            response = requests.post(
                f"{self.midjourney_api_url[self.speed]}/mj/submit/upload-discord-images",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "FAILURE":
                    fail_reason = result.get("fail_reason", "Unknown failure reason")
                    error_message = f"Image upload failed: {fail_reason}"
                    print(error_message)
                    raise Exception(error_message)
                    
                if "result" in result and result["result"]:
                    return (result["result"][0],)
                else:
                    error_message = f"Unexpected response from Midjourney API: {result}"
                    raise Exception(error_message)
            else:
                error_message = f"Error uploading image to Midjourney: {response.status_code} - {response.text}"
                raise Exception(error_message)
                
        except Exception as e:
            print(f"Error in upload_image: {str(e)}")
            raise e
        

class Comfly_Mj(ComflyBaseNode):
    """
    Comfly_Mj node
    Processes text or image inputs using Midjourney AI model and returns the processed results.
    Inputs:
        text (STRING, optional): Input text.
        api_key (STRING): API key for Midjourney.
        model_version (STRING): Selected Midjourney model version (v 6.1, v 6.0, v 5.2, v 5.1, niji 6, niji 5, niji 4).
        speed (STRING): Selected speed mode (turbo mode, fast mode, relax mode).
        ar (STRING): Aspect ratio.
        no (STRING): Number of images.
        c (STRING): Chaos value (0-100).
        s (STRING): Stylize value (0-1000).
        iw (STRING): Image weight (0-2).
        tile (BOOL): Enable/disable tile.
        r (STRING): Repeat value (1-40).
        video (BOOL): Enable/disable video.
        sw (STRING): Style weight (0-1000).
        cw (STRING): Color weight (0-100).
        sv (STRING): Style variation (1-4).
        seed (INT): Random seed.
        cref (STRING): Creative reference.
        oref (STRING): Object reference.
        sref (STRING): Style reference.
        positive (STRING): Additional positive prompt to be appended to the main prompt.
    Outputs:
        image_url (STRING): URL of the processed image.
        text (STRING): Processed text output.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True}),
                "speed": (["turbo mode", "fast mode", "relax mode"], {"default": "fast mode"}), 
            },
            "optional": {
                "text_en": ("STRING", {"multiline": True, "default": ""}),
                "api_key": ("STRING", {"default": ""}),  
                "ar": ("STRING", {"default": "1:1"}),
                "model_version": (["v 7", "v 6.1", "v 6.0", "v 5.2", "v 5.1", "niji 6", "niji 5", "niji 4"], {"default": "v 6.1"}),
                "no": ("STRING", {"default": "", "forceInput": True}),
                "c": ("INT", {"default": 0, "min": 0, "max": 100, "forceInput": True}),
                "s": ("INT", {"default": 0, "min": 0, "max": 1000, "forceInput": True}),
                "iw": ("FLOAT", {"default": 0, "min": 0, "max": 2, "forceInput": True}),
                "r": ("INT", {"default": 1, "min": 1, "max": 40, "forceInput": True}),
                "sw": ("INT", {"default": 0, "min": 0, "max": 1000, "forceInput": True}),
                "cw": ("INT", {"default": 0, "min": 0, "max": 100, "forceInput": True}),
                "sv": (["1", "2", "3", "4"], {"default": "1", "forceInput": True}),
                "oref": ("STRING", {"default": "none", "forceInput": True}),
                "cref": ("STRING", {"default": "none", "forceInput": True}),
                "sref": ("STRING", {"default": "none", "forceInput": True}),
                "positive": ("STRING", {"default": "", "forceInput": True}),                
                "video": ("BOOLEAN", {"default": False}),
                "tile": ("BOOLEAN", {"default": False}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING", "STRING")  
    RETURN_NAMES = ("image", "text", "taskId")    
    OUTPUT_NODE = True

    FUNCTION = "process_input"

    CATEGORY = "Comfly-v2/Midjourney"

    def __init__(self):
        super().__init__()
        self.image = None
        self.text = ""

    def process_input(self, speed, text, text_en="", image=None, model_version=None, ar=None, no=None, c=None, s=None, iw=None, r=None, sw=None, cw=None, sv=None, video=False, tile=False, seed=0, cref="none", oref="none", sref="none", positive="", api_key=""):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        self.image = image
        self.speed = speed

        prompt = text_en if text_en else text

        if positive:
            prompt += f" {positive}"

        if model_version:
            prompt += f" --{model_version}"
        if ar:
            prompt += f" --ar {ar}"
        if no:
            prompt += f" --no {no}"
        if c:
            prompt += f" --c {c}"
        if s:
            prompt += f" --s {s}"
        if iw:
            prompt += f" --iw {iw}"
        if r:
            prompt += f" --r {r}"
        if sw:
            prompt += f" --sw {sw}"
        if cw:
            prompt += f" --cw {cw}"
        if sv:
            prompt += f" --sv {sv}"
        if video:
            prompt += " --video"
        if tile:
            prompt += " --tile"
        if oref != "none":
            prompt += f" --oref {oref}"    
        if cref != "none":
            prompt += f" --cref {cref}"
        if sref != "none":
            prompt += f" --sref {sref}"

        self.text = prompt

        if self.image is not None:
            image_url, text = self.process_image()
        elif self.text:
            pbar = comfy.utils.ProgressBar(10)
            image_url, text, taskId = self.process_text(pbar, ar, no, c, s, iw, tile, r, video, sw, cw, sv, seed)
            
            response = requests.get(image_url)
            image = Image.open(BytesIO(response.content))
            tensor_image = pil2tensor(image)
            return tensor_image, text, taskId
        else:
            raise ValueError("Either image or text input must be provided for Midjourney model.")
        
        return image_url, text, taskId

    def process_text_midjourney_sync(self, text, pbar, ar, no, c, s, iw, tile, r, video, sw, cw, sv, seed):
        try:
            taskId = self.midjourney_submit_imagine_task_sync(text, ar, no, c, s, iw, tile, r, video, sw, cw, sv, seed)
            print(f"Task ID: {taskId}")
            
            task_result = None

            while True:
                time.sleep(1)
                try:
                    task_result = self.midjourney_fetch_task_result_sync(taskId)
 
                    if task_result.get("status") == "FAILURE":
                        fail_reason = task_result.get("fail_reason", "Unknown failure reason")
                        error_message = f"Midjourney task failed: {fail_reason}"
                        print(error_message)  
                        raise Exception(error_message)  
                    if task_result.get("status") == "SUCCESS":
                        break
                        
                    progress = task_result.get("progress", 0)
                    try:
                        progress_int = int(progress[:-1])
                    except (ValueError, TypeError):
                        progress_int = 0
                    pbar.update_absolute(progress_int)

                except Exception as e:
                    if "Midjourney task failed" in str(e):
                        raise  
                    print(f"Error fetching task result: {str(e)}")
                    time.sleep(2)
                    continue
                
            image_url = task_result.get("imageUrl", "")
            prompt = task_result.get("prompt", text)

            U1 = self.generate_custom_id(task_result.get("id", taskId), "upsample", 1)
            U2 = self.generate_custom_id(task_result.get("id", taskId), "upsample", 2)
            U3 = self.generate_custom_id(task_result.get("id", taskId), "upsample", 3)
            U4 = self.generate_custom_id(task_result.get("id", taskId), "upsample", 4)

            return image_url, prompt, U1, U2, U3, U4, taskId 
        
        except Exception as e:
            print(f"Error in process_text_midjourney_sync: {str(e)}")
            raise e

    def midjourney_submit_imagine_task_sync(self, prompt, ar, no, c, s, iw, tile, r, video, sw, cw, sv, seed):
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key
        }
        payload = {
            "base64Array": [],
            "instanceId": "",
            "modes": [],
            "notifyHook": "",
            "prompt": prompt,
            "remix": True,
            "state": "",
            "ar": ar,
            "no": no,
            "c": c,
            "s": s,
            "iw": iw,
            "tile": tile,
            "r": r,
            "video": video,
            "sw": sw,
            "cw": cw,
            "sv": sv,
            "seed": seed
        }
        try:
            response = requests.post(
                f"{self.midjourney_api_url[self.speed]}/mj/submit/imagine", 
                headers=headers, 
                json=payload, 
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                error_message = f"Error submitting Midjourney task: {response.status_code}"
                try:
                    error_details = response.text
                    error_message += f" - {error_details}"
                except:
                    pass
                raise Exception(error_message)
                
            try:
                data = response.json()
                
                if data.get("status") == "FAILURE":
                    fail_reason = data.get("fail_reason", "Unknown failure reason")
                    error_message = f"Midjourney task failed: {fail_reason}"
                    print(error_message)
                    raise Exception(error_message)
                    
                return data["result"]
            except (json.JSONDecodeError, KeyError):
                text_response = response.text
                if text_response and len(text_response) < 100:
                    return text_response.strip()
                raise Exception(f"Server returned invalid response: {text_response}")
        except Exception as e:
            if "Midjourney task failed" in str(e):
                raise  
            print(f"Exception in midjourney_submit_imagine_task_sync: {str(e)}")
            raise e

    def midjourney_fetch_task_result_sync(self, taskId):
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key
        }
        try:
            response = requests.get(
                f"{self.midjourney_api_url[self.speed]}/mj/task/{taskId}/fetch",
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                error_message = f"Error fetching Midjourney task result: {response.status_code}"
                try:
                    error_details = response.text
                    error_message += f" - {error_details}"
                except:
                    pass
                raise Exception(error_message)
                
            try:
                data = response.json()
                return data
            except json.JSONDecodeError:
                text_response = response.text
                if text_response and len(text_response) < 100:
                    return {"status": "SUCCESS", "progress": "100%", "imageUrl": text_response.strip()}
                raise Exception(f"Server returned invalid response: {text_response}")
        except Exception as e:
            print(f"Error in midjourney_fetch_task_result_sync: {str(e)}")
            raise e
            
    def process_text(self, pbar, ar, no, c, s, iw, tile, r, video, sw, cw, sv, seed):

        image_url, text, U1, U2, U3, U4, taskId = self.process_text_midjourney_sync(self.text, pbar, ar, no, c, s, iw, tile, r, video, sw, cw, sv, seed)
        
        U = json.dumps({"U1": U1, "U2": U2, "U3": U3, "U4": U4})

        self.taskId = taskId
    
        return image_url, text, self.taskId

    def generate_custom_id(self, taskId, action, index):
        uuid = self.generateUUID()
        if action in ["upsample_v6_2x_subtle", "upsample_v6_2x_creative", "pan_left", "pan_right", "pan_up", "pan_down"]:
            return f"MJ::JOB::{action}::{index}::{uuid}::SOLO"
        elif action == "Outpaint::50":
            return f"MJ::Outpaint::50::{index}::{uuid}::SOLO"
        else:
            return f"MJ::JOB::{action}::{index}::{uuid}"
    
    
class Comfly_Mju(ComflyBaseNode):
    class MidjourneyError(Exception):
        pass
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "taskId": ("STRING", {"default": "", "forceInput": True}),
                "U1": ("BOOLEAN", {"default": False}),
                "U2": ("BOOLEAN", {"default": False}),
                "U3": ("BOOLEAN", {"default": False}),
                "U4": ("BOOLEAN", {"default": False})
            },
            "optional": {
                "api_key": ("STRING", {"default": ""})
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")  
    RETURN_NAMES = ("image", "taskId")  
    FUNCTION = "run"
    CATEGORY = "Comfly-v2/Midjourney"

    def run(self, taskId, U1=False, U2=False, U3=False, U4=False, api_key=""):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
        
        try:
            try:
                current_loop = asyncio.get_running_loop()
            
                def run_async():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(self.process_input(taskId, U1, U2, U3, U4))
                    finally:
                        new_loop.close()

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_async)
                    return future.result()
                    
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    results = loop.run_until_complete(self.process_input(taskId, U1, U2, U3, U4))
                finally:
                    loop.close()
                return results
                
        except Exception as e:
            print(f"Error in run method: {str(e)}")
            blank_image = Image.new('RGB', (512, 512), color='white')
            blank_tensor = pil2tensor(blank_image)
            return (blank_tensor, "")


    async def process_input(self, taskId, U1=False, U2=False, U3=False, U4=False):
        try:
            if not any([U1, U2, U3, U4]):
                raise self.MidjourneyError("NO_ACTION_SELECTED")

            action = None
            index = None
            if U1:
                action = "upsample"
                index = 1
            elif U2:
                action = "upsample"
                index = 2
            elif U3:
                action = "upsample"
                index = 3
            elif U4:
                action = "upsample"
                index = 4

            task_result = await self.midjourney_fetch_task_result(taskId)

            if task_result.get("status") == "FAILURE":
                fail_reason = task_result.get("fail_reason", "Unknown failure reason")
                error_message = f"Original task failed: {fail_reason}"
                print(error_message)
                raise self.MidjourneyError(error_message)

            messageId = None

            if "properties" in task_result and task_result["properties"]:
                properties = task_result["properties"]

                if isinstance(properties, str):
                    try:
                        properties = json.loads(properties)
                    except json.JSONDecodeError as e:
                        print(f"Failed to parse properties JSON: {e}")
                        properties = {}

                if isinstance(properties, dict):
                    messageId = properties.get("messageId") or properties.get("message_id")

            if not messageId and "buttons" in task_result and task_result["buttons"]:
                buttons = task_result["buttons"]
                
                try:
                    if isinstance(buttons, str):
                        buttons = json.loads(buttons)

                    if isinstance(buttons, list) and buttons:
                        for button in buttons:
                            if isinstance(button, dict):
                                custom_id = button.get("customId", "")
                                if custom_id:
                                    parts = custom_id.split("::")
                                    if len(parts) >= 5:
                                        messageId = parts[4]
                                        break
                                
                except (json.JSONDecodeError, TypeError, AttributeError) as e:
                    print(f"Error processing buttons: {str(e)}")

            if not messageId:
                possible_fields = ['messageId', 'message_id', 'id', 'task_id']
                for field in possible_fields:
                    if field in task_result and task_result[field]:
                        messageId = task_result[field]
                        print(f"Found messageId in field '{field}': {messageId}")
                        break

            if not messageId:
                response_str = str(task_result)

                id_patterns = [
                    r'"(?:messageId|message_id|id)"\s*:\s*"([a-zA-Z0-9\-_]{16,})"',
                    r'MJ::JOB::\w+::\d+::([a-zA-Z0-9\-_]{16,})',
                    r'"([a-zA-Z0-9\-_]{20,})"'
                ]
                
                for pattern in id_patterns:
                    match = re.search(pattern, response_str)
                    if match:
                        messageId = match.group(1)
                        print(f"Found messageId using pattern: {messageId}")
                        break

            if not messageId:
                messageId = taskId
                print(f"Using taskId as messageId: {messageId}")

            if not messageId:
                error_message = "Could not find messageId in task result"
                print(error_message)
                print(f"Task result structure: {json.dumps(task_result, indent=2)}")
                raise self.MidjourneyError(error_message)

            custom_id = self.generate_custom_id(action, index, messageId)

            response = await self.midjourney_submit_action(action, taskId, index, custom_id)

            if isinstance(response, str) and response.startswith("Error"):
                raise self.MidjourneyError(response)

            if "result" not in response:
                raise self.MidjourneyError(f"Unexpected response from Midjourney API: {response}")

            new_task_id = response["result"]
            while True:
                await asyncio.sleep(1)
                task_result = await self.midjourney_fetch_task_result(new_task_id)

                if task_result.get("status") == "FAILURE":
                    fail_reason = task_result.get("fail_reason", "Unknown failure reason")
                    error_message = f"Task failed: {fail_reason}"
                    print(error_message)
                    raise self.MidjourneyError(error_message)

                if task_result.get("status") == "SUCCESS":
                    break

            if task_result.get("code") == 5 and task_result.get("description") == "task_no_found":
                raise self.MidjourneyError(f"Task not found for taskId: {new_task_id}")

            response = requests.get(task_result["imageUrl"])
            image = Image.open(BytesIO(response.content))
            tensor_image = pil2tensor(image)
            return tensor_image, new_task_id 

        except self.MidjourneyError as e:
            print(f"Midjourney API error: {str(e)}")
            raise e
        except Exception as e:
            print(f"An error occurred while processing input: {str(e)}")
            raise e
       

    def generate_custom_id(self, action, index, message_id):
        if action == "zoom":
            return f"MJ::CustomZoom::{message_id}"
        elif action in ["upsample_v6_2x_subtle", "upsample_v6_2x_creative", "upsample_v5_2x", "upsample_v5_4x",
                "pan_left", "pan_right", "pan_up", "pan_down", "reroll"]:
            return f"MJ::JOB::{action}::{index}::{message_id}::SOLO"
        elif action.startswith("Outpaint"):
            return f"MJ::{action}::{index}::{message_id}::SOLO"
        elif action == "Inpaint":
            return f"MJ::{action}::1::{index}::{message_id}::SOLO"
        elif action == "CustomZoom":
            return f"MJ::CustomZoom::{index}::{message_id}"
        else:
            return f"MJ::JOB::{action}::{index}::{message_id}"

    def generateUUID(self):
        return str(uuid.uuid4()) 

    async def process_custom_id(self, custom_id):
        if custom_id:
            try:
                action, index, uuid = self.parse_custom_id(custom_id)
                taskId = self.extract_taskId(custom_id)

                
                response = await self.midjourney_submit_action(action, taskId, index, custom_id)
                taskId = response["result"]

                
                task_result = None
                while not task_result or task_result.get("status") != "SUCCESS":
                    await asyncio.sleep(1)
                    task_result = await self.midjourney_fetch_task_result(taskId)
                
                image_url = task_result["imageUrl"]
                return image_url
                
            except Exception as e:
                print(f"Error processing custom_id: {custom_id}. Error: {str(e)}")
                raise ValueError(f"Error processing image from custom ID: {custom_id}. Error: {str(e)}")
        else:
            print("Custom ID is empty, returning empty string")
            return ""

    def parse_custom_id(self, custom_id):
        parts = custom_id.split("::")
        action = parts[2]
        index = int(parts[3])
        uuid = parts[4]
        return action, index, uuid

    def extract_custom_id(self, U, action, index):
        pattern = fr"MJ::JOB::{action}::{index}::(\w+)"
        match = re.search(pattern, U)
        if match:
            return f"MJ::JOB::{action}::{index}::{match.group(1)}"
        else:
            return None

    def extract_taskId(self, U, action, index):
        pattern = fr'"customId": "MJ::JOB::{action}::{index}::(.*?)"'
        match = re.search(pattern, U)
        if match:
            return match.group(1)
        else:
            raise ValueError(f"Invalid custom ID format in U: {U}")

    async def midjourney_submit_action(self, action, taskId, index, custom_id):
        headers = self.get_headers()
        payload = {
            "customId": custom_id,
            "taskId": taskId
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.midjourney_api_url[self.speed]}/mj/submit/action", headers=headers, json=payload, timeout=self.timeout) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()

                            if data.get("status") == "FAILURE":
                                fail_reason = data.get("fail_reason", "Unknown failure reason")
                                error_message = f"Action submission failed: {fail_reason}"
                                print(error_message)
                                raise Exception(error_message)
                                
                            return data
                        except aiohttp.client_exceptions.ContentTypeError:
                            text_response = await response.text()
                            
                            try:
                                import json
                                data = json.loads(text_response)
 
                                if data.get("status") == "FAILURE":
                                    fail_reason = data.get("fail_reason", "Unknown failure reason")
                                    error_message = f"Action submission failed: {fail_reason}"
                                    print(error_message)
                                    raise Exception(error_message)
                                    
                                return data
                            except json.JSONDecodeError:
                                if text_response and len(text_response) < 100:
                                    return {"result": text_response.strip()}
                                raise Exception(f"Invalid response format: {text_response}")
                    else:
                        error_message = f"Error submitting Midjourney action: {response.status}"
                        try:
                            error_details = await response.text()
                            error_message += f" - {error_details}"
                        except:
                            pass
                        raise Exception(error_message)
        except asyncio.TimeoutError:
            error_message = f"Timeout error: Request to submit action timed out after {self.timeout} seconds"
            raise Exception(error_message)
        except Exception as e:
            if "Action submission failed" in str(e):
                raise 
            print(f"Exception in midjourney_submit_action: {str(e)}")
            raise e


    async def midjourney_fetch_task_result(self, taskId):
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.midjourney_api_url[self.speed]}/mj/task/{taskId}/fetch", headers=headers, timeout=self.timeout) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()

                            return data
                        except aiohttp.client_exceptions.ContentTypeError:
                            text_response = await response.text()
                            try:
                                import json
                                data = json.loads(text_response)
                                return data
                            except json.JSONDecodeError:
                                if text_response and len(text_response) < 100:
                                    return {"status": "SUCCESS", "progress": "100%", "imageUrl": text_response.strip()}
                                raise Exception(f"Server returned invalid response: {text_response}")
                    else:
                        error_message = f"Error fetching Midjourney task result: {response.status}"
                        try:
                            error_details = await response.text()
                            error_message += f" - {error_details}"
                        except:
                            pass
                        raise Exception(error_message)
        except asyncio.TimeoutError:
            error_message = f"Timeout error: Request to fetch task result timed out after {self.timeout} seconds"
            raise Exception(error_message)

                

    async def midjourney_submit_imagine_task(self, prompt, ar, no, c, s, iw, tile, r, video, sw, cw, sv, seed):
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key
        }
        payload = {
            "base64Array": [],
            "instanceId": "",
            "modes": [],
            "notifyHook": "",
            "prompt": prompt,
            "remix": True,
            "state": "",
            "ar": ar,
            "no": no,
            "c": c,
            "s": s,
            "iw": iw,
            "tile": tile,
            "r": r,
            "video": video,
            "sw": sw,
            "cw": cw,
            "sv": sv,
            "seed": seed
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.midjourney_api_url[self.speed]}/mj/submit/imagine", headers=headers, json=payload, timeout=self.timeout) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()

                            if data.get("status") == "FAILURE":
                                fail_reason = data.get("fail_reason", "Unknown failure reason")
                                error_message = f"Midjourney task failed: {fail_reason}"
                                print(error_message)
                                raise Exception(error_message)
                                
                            return data["result"]
                        except aiohttp.client_exceptions.ContentTypeError:
                            text_response = await response.text()
                            
                            try:
                                import json
                                data = json.loads(text_response)

                                if data.get("status") == "FAILURE":
                                    fail_reason = data.get("fail_reason", "Unknown failure reason")
                                    error_message = f"Midjourney task failed: {fail_reason}"
                                    print(error_message)
                                    raise Exception(error_message)
                                    
                                return data["result"]
                            except (json.JSONDecodeError, KeyError):
                                if text_response and len(text_response) < 100:
                                    return text_response.strip()
                                raise Exception(f"Server returned invalid response: {text_response}")
                    else:
                        error_message = f"Error submitting Midjourney task: {response.status}"
                        try:
                            error_details = await response.text()
                            error_message += f" - {error_details}"
                        except:
                            pass
                        raise Exception(error_message)
        except asyncio.TimeoutError:
            error_message = f"Timeout error: Request to submit imagine task timed out after {self.timeout} seconds"
            raise Exception(error_message)
        except Exception as e:
            if "Midjourney task failed" in str(e):
                raise  
            print(f"Exception in midjourney_submit_imagine_task: {str(e)}")
            raise e


    async def midjourney_fetch_task_result(self, taskId):
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.midjourney_api_url[self.speed]}/mj/task/{taskId}/fetch", headers=headers, timeout=self.timeout) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()

                            return data
                        except aiohttp.client_exceptions.ContentTypeError:
                            text_response = await response.text()
                            try:
                                import json
                                data = json.loads(text_response)
                                return data
                            except json.JSONDecodeError:
                                if text_response and len(text_response) < 100:
                                    return {"status": "SUCCESS", "progress": "100%", "imageUrl": text_response.strip()}
                                raise Exception(f"Server returned invalid response: {text_response}")
                    else:
                        error_message = f"Error fetching Midjourney task result: {response.status}"
                        try:
                            error_details = await response.text()
                            error_message += f" - {error_details}"
                        except:
                            pass
                        raise Exception(error_message)
        except asyncio.TimeoutError:
            error_message = f"Timeout error: Request to fetch task result timed out after {self.timeout} seconds"
            raise Exception(error_message)


class Comfly_Mjv(ComflyBaseNode):
    class MidjourneyError(Exception):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "taskId": ("STRING", {"default": "", "forceInput": True}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "upsample_v6_2x_subtle": ("BOOLEAN", {"default": False}),
                "upsample_v6_2x_creative": ("BOOLEAN", {"default": False}),
                "costume_zoom": ("BOOLEAN", {"default": False}),
                "zoom": ("FLOAT", {"default": 1.0, "min": 1.0, "max": 2.0, "step": 0.1}),
                "pan_left": ("BOOLEAN", {"default": False}),
                "pan_right": ("BOOLEAN", {"default": False}),
                "pan_up": ("BOOLEAN", {"default": False}),
                "pan_down": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("IMAGE",) 
    RETURN_NAMES = ("image",) 
    FUNCTION = "run"
    CATEGORY = "Comfly-v2/Midjourney"

    def run(self, taskId, upsample_v6_2x_subtle=False, upsample_v6_2x_creative=False, costume_zoom=False, zoom=1.0, pan_left=False, pan_right=False, pan_up=False, pan_down=False, api_key=""):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
        
        try:
            try:
                current_loop = asyncio.get_running_loop()
            
                def run_async():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(self.process_input(taskId, upsample_v6_2x_subtle, upsample_v6_2x_creative, costume_zoom, zoom, pan_left, pan_right, pan_up, pan_down))
                    finally:
                        new_loop.close()

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_async)
                    result = future.result()

                    if isinstance(result, tuple) and len(result) > 0:
                        return result
                    else:
                        blank_image = Image.new('RGB', (512, 512), color='white')
                        blank_tensor = pil2tensor(blank_image)
                        return (blank_tensor,)
                    
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(self.process_input(taskId, upsample_v6_2x_subtle, upsample_v6_2x_creative, costume_zoom, zoom, pan_left, pan_right, pan_up, pan_down))

                    if isinstance(result, tuple) and len(result) > 0:
                        return result
                    else:
                        blank_image = Image.new('RGB', (512, 512), color='white')
                        blank_tensor = pil2tensor(blank_image)
                        return (blank_tensor,)
                finally:
                    loop.close()
                
        except Exception as e:
            print(f"Error in run method: {str(e)}")
            blank_image = Image.new('RGB', (512, 512), color='white')
            blank_tensor = pil2tensor(blank_image)
            return (blank_tensor,)

    async def process_input(self, taskId, upsample_v6_2x_subtle=False, upsample_v6_2x_creative=False, costume_zoom=False, zoom=1.0, pan_left=False, pan_right=False, pan_up=False, pan_down=False):
        if taskId:
            try:
                task_result = await self.midjourney_fetch_task_result(taskId)
    
                if task_result.get("status") == "FAILURE":
                    fail_reason = task_result.get("fail_reason", "Unknown failure reason")
                    error_message = f"Original task failed: {fail_reason}"
                    print(error_message)
                    raise Exception(error_message)

                messageId = None
                properties = {}
                if "properties" in task_result:
                    if isinstance(task_result["properties"], str):
                        try:
                            properties = json.loads(task_result["properties"])
                        except json.JSONDecodeError as e:
                            error_message = f"Failed to parse properties JSON: {e}"
                            print(error_message)
                            raise Exception(error_message)
                    else:
                        properties = task_result["properties"]
                    
                    messageId = properties.get("messageId")

                if not messageId and "buttons" in task_result and task_result["buttons"]:
                    try:
                        buttons = task_result["buttons"]
                        if isinstance(buttons, str):
                            buttons = json.loads(buttons)
                        elif isinstance(buttons, list):
                            pass
                        else:
                            print(f"Unexpected buttons type: {type(buttons)}")
                            buttons = []
                        
                        if buttons and len(buttons) > 0 and isinstance(buttons[0], dict):
                            first_button_id = buttons[0].get("customId", "")
                            parts = first_button_id.split("::")
                            if len(parts) >= 5:
                                messageId = parts[4]
                    except Exception as e:
                        print(f"Failed to extract messageId from buttons: {e}")

                if not messageId:
                    error_message = "Could not find messageId in task result"
                    print(error_message)
                    raise Exception(error_message)
                
                prompt = task_result.get("prompt", "")

                customId = None
                if upsample_v6_2x_subtle:
                    customId = f"MJ::JOB::upsample_v6_2x_subtle::2::{messageId}::SOLO"
                elif upsample_v6_2x_creative:
                    customId = f"MJ::JOB::upsample_v6_2x_creative::2::{messageId}::SOLO"
                elif costume_zoom:
                    customId = f"MJ::CustomZoom::{messageId}::2"
                elif pan_left:
                    customId = f"MJ::JOB::pan_left::2::{messageId}::SOLO"
                elif pan_right:
                    customId = f"MJ::JOB::pan_right::2::{messageId}::SOLO"
                elif pan_up:
                    customId = f"MJ::JOB::pan_up::2::{messageId}::SOLO"
                elif pan_down:
                    customId = f"MJ::JOB::pan_down::2::{messageId}::SOLO"
                else:
                    raise Exception("No action selected")
                
                print(f"Generated customId: {customId}")

                if costume_zoom and zoom > 1.0:
                    zoom_param = f" --zoom {zoom}"
                    final_prompt = prompt + zoom_param
 
                    action_response = await self.submit_action(customId, taskId)
                    new_task_id = action_response.get("result", "")
                    
                    if not new_task_id:
                        raise Exception("Failed to get new task ID from action response")

                    modal_response = await self.submit_modal(final_prompt, new_task_id)
                    final_task_id = modal_response.get("result", "")
                    
                    if not final_task_id:
                        raise Exception("Failed to get task ID from modal response")

                    image_url = await self.process_task(final_task_id)
                    
                else:  
                    action_response = await self.submit_action(customId, taskId)
                    new_task_id = action_response.get("result", "")
                    
                    if not new_task_id:
                        raise Exception("Failed to get new task ID from action response")

                    image_url = await self.process_task(new_task_id)

                if image_url:
                    response = requests.get(image_url)
                    image = Image.open(BytesIO(response.content))
                    tensor_image = pil2tensor(image)
                    return (tensor_image,)
                else:
                    blank_image = Image.new('RGB', (512, 512), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor,)

            except Exception as e:
                error_message = f"Error processing action: {str(e)}"
                print(error_message)
                blank_image = Image.new('RGB', (512, 512), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor,)
        else:
            print("No taskId provided.")
            blank_image = Image.new('RGB', (512, 512), color='white')
            blank_tensor = pil2tensor(blank_image)
            return (blank_tensor,)

    async def process_task(self, taskId):
        while True:
            await asyncio.sleep(1)
            try:
                task_result = await self.midjourney_fetch_task_result(taskId)

                if task_result.get("status") == "FAILURE":
                    fail_reason = task_result.get("fail_reason", "Unknown failure reason")
                    error_message = f"Task failed: {fail_reason}"
                    print(error_message)
                    raise Exception(error_message)

                if task_result.get("status") == "SUCCESS":
                    return task_result.get("imageUrl", task_result.get("image_url", ""))
                    
            except Exception as e:
                if "Task failed:" in str(e):
                    raise  
                error_message = f"Error fetching task result: {str(e)}"
                print(error_message)
                raise Exception(error_message)

    async def submit_action(self, customId, taskId):
        headers = self.get_headers()
        payload = {
            "customId": customId,
            "taskId": taskId
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.midjourney_api_url[self.speed]}/mj/submit/action", headers=headers, json=payload) as response: 
                if response.status == 200:
                    try:
                        data = await response.json()
                        return data
                    except aiohttp.client_exceptions.ContentTypeError:
                        text_response = await response.text()
                        print(f"API returned non-JSON response: {text_response}")
                        try:
                            import json
                            data = json.loads(text_response)
                            return data
                        except json.JSONDecodeError:
                            if text_response and len(text_response) < 100:
                                return {"result": text_response.strip()}
                            raise Exception(f"Invalid response format: {text_response}")
                else:
                    error_message = f"Error submitting Midjourney action: {response.status}"
                    print(error_message)
                    try:
                        error_details = await response.text()
                        error_message += f" - {error_details}"
                    except:
                        pass
                    raise Exception(error_message)
    
    async def submit_modal(self, prompt, taskId, maskBase64=None):
        headers = self.get_headers()
        payload = {
            "prompt": prompt,
            "taskId": taskId
        }
        
        if maskBase64:
            payload["maskBase64"] = maskBase64

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.midjourney_api_url[self.speed]}/mj/submit/modal", headers=headers, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    error_message = f"Error submitting Midjourney modal: {response.status}"
                    print(error_message)
                    raise Exception(error_message)

    async def midjourney_fetch_task_result(self, taskId):
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.midjourney_api_url[self.speed]}/mj/task/{taskId}/fetch", headers=headers, timeout=self.timeout) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            return data
                        except aiohttp.client_exceptions.ContentTypeError:
                            text_response = await response.text()
                            try:
                                import json
                                data = json.loads(text_response)
                                return data
                            except json.JSONDecodeError:
                                if text_response and len(text_response) < 100:
                                    return {"status": "SUCCESS", "progress": "100%", "imageUrl": text_response.strip()}
                                raise Exception(f"Server returned invalid response: {text_response}")
                    else:
                        error_message = f"Error fetching Midjourney task result: {response.status}"
                        try:
                            error_details = await response.text()
                            error_message += f" - {error_details}"
                        except:
                            pass
                        raise Exception(error_message)
        except asyncio.TimeoutError:
            error_message = f"Timeout error: Request to fetch task result timed out after {self.timeout} seconds"
            raise Exception(error_message)


class Comfly_Mj_swap_face(ComflyBaseNode):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_image": ("IMAGE",),
                "target_image": ("IMAGE",),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647})
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "image_url")
    FUNCTION = "swap_face"
    CATEGORY = "Comfly-v2/Midjourney"

    def __init__(self):
        super().__init__()
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300
        self.poll_interval = 3 

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key
        }
        
    def image_to_base64(self, image_tensor):
        """Convert tensor to base64 string with data URI prefix"""
        if image_tensor is None:
            return None
            
        pil_image = tensor2pil(image_tensor)[0]
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        base64_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{base64_str}"

    def fetch_task_result(self, task_id):
        """Fetch task result by task_id"""
        try:
            response = requests.get(
                f"{baseurl}/mj/task/{task_id}/fetch",
                headers=self.get_headers(),
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                return None, f"API Error: {response.status_code} - {response.text}"
                
            result = response.json()
            return result, None
            
        except Exception as e:
            return None, f"Error fetching task result: {str(e)}"

    def swap_face(self, source_image, target_image, api_key="", seed=0):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        if not self.api_key:
            return (source_image, "API key not provided or not found in config")
            
        try:
            source_base64 = self.image_to_base64(source_image)
            target_base64 = self.image_to_base64(target_image)
            
            if not source_base64 or not target_base64:
                return (source_image, "Failed to convert images to base64 format")
            
            payload = {
                "sourceBase64": source_base64,
                "targetBase64": target_base64
            }

            if seed > 0:
                payload["seed"] = seed
            
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(5)

            print("Sending request to face swap API...")
            response = requests.post(
                f"{baseurl}/mj/insight-face/swap",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            pbar.update_absolute(10)
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                return (source_image, error_message)
                
            result = response.json()

            if "result" not in result:
                error_message = "No task ID (result field) in API response"
                print(error_message)
                return (source_image, error_message)
                
            task_id = result["result"]
            print(f"Got task ID: {task_id}")

            start_time = time.time()
            last_progress = 0
            
            while time.time() - start_time < self.timeout:
                task_result, error = self.fetch_task_result(task_id)
                
                if error:
                    print(f"Error fetching task result: {error}")
                    time.sleep(self.poll_interval)
                    continue
                
                status = task_result.get("status")
                progress_str = task_result.get("progress", "0%").rstrip("%")
                
                try:
                    progress = int(progress_str)
                except ValueError:
                    progress = last_progress
                
                if progress > last_progress:
                    last_progress = progress
                    pbar.update_absolute(10 + int(progress * 0.8))
                
                if status == "SUCCESS":
                    image_url = None
                    for field in ["imageUrl", "image_url", "url"]:
                        if field in task_result:
                            image_url = task_result.get(field)
                            break
                    
                    if not image_url:
                        error_message = "No image URL in completed task result"
                        print(error_message)
                        return (source_image, error_message)
                    
                    print(f"Found image URL: {image_url}")
                    
                    try:
                        img_response = requests.get(image_url, timeout=self.timeout)
                        img_response.raise_for_status()
                        
                        swapped_image = Image.open(BytesIO(img_response.content))
                        swapped_tensor = pil2tensor(swapped_image)
                        
                        pbar.update_absolute(100)
                        print(f"Face swap completed successfully")
                        return (swapped_tensor, image_url)
                        
                    except Exception as e:
                        error_message = f"Error downloading swapped face image: {str(e)}"
                        print(error_message)
                        return (source_image, error_message)
                
                elif status == "FAILURE":
                    fail_reason = task_result.get("fail_reason", "Unknown failure")
                    error_message = f"Task failed: {fail_reason}"
                    print(error_message)
                    return (source_image, error_message)
                
                time.sleep(self.poll_interval)
            
            error_message = f"Task timed out after {self.timeout} seconds"
            print(error_message)
            return (source_image, error_message)
            
        except Exception as e:
            error_message = f"Error in face swapping: {str(e)}"
            print(error_message)
            import traceback
            traceback.print_exc()
            return (source_image, error_message)


class Comfly_mjstyle:
    styleAll = {}

    def __init__(self):
        dir = os.path.join(os.path.dirname(__file__), "docs", "mjstyle")
        if not os.path.exists(dir):
            os.mkdir(dir)
        for root, dirs, files in os.walk(dir):
            for file in files:
                if file.endswith(".json"):
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for d in data:
                            Comfly_mjstyle.styleAll[d['name']] = d

    @classmethod
    def INPUT_TYPES(cls):
        dir = os.path.join(os.path.dirname(__file__), "docs", "mjstyle")
        files_name = []
        for root, dirs, files in os.walk(dir):
            for file in files:
                if file.endswith(".json"):
                    files_name.append(file.split(".")[0])

        return {
            "required": {
                "styles_type": (files_name,),
            },
            "optional": {
                "positive": ("STRING", {"forceInput": True}),
                "negative": ("STRING", {"forceInput": True}),
            },
            "hidden": {"extra_pnginfo": "EXTRA_PNGINFO", "unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("STRING", "STRING",)
    RETURN_NAMES = ("style_positive", "style_negative",)

    FUNCTION = "run"

    OUTPUT_NODE = True

    CATEGORY = "Comfly-v2/Midjourney"

    def replace_repeat(self, prompt):
        prompt = prompt.replace("，", ",")
        arr = prompt.split(",")
        if len(arr) != len(set(arr)):
            all_weight_prompt = re.findall(re.compile(r'[(](.*?)[)]', re.S), prompt)
            if len(all_weight_prompt) > 0:
                return prompt
            else:
                arr = [item.strip() for item in arr]
                arr = list(set(arr))
                return ", ".join(arr)
        else:
            return prompt

    def run(self, extra_pnginfo, unique_id, styles_type, positive="", negative=""):
        values = []
        for node in extra_pnginfo["workflow"]["nodes"]:
            if node["id"] == int(unique_id):
                values = node["properties"]["values"]
                break

        style_positive = ""
        style_negative = ""
        has_prompt = False

        for val in values:
            if "prompt" in Comfly_mjstyle.styleAll[val]:
                if "{positive}" in Comfly_mjstyle.styleAll[val]["prompt"] and not has_prompt:
                    style_positive = Comfly_mjstyle.styleAll[val]["prompt"].format(positive=positive)
                    has_prompt = True
                else:
                    style_positive += ", " + Comfly_mjstyle.styleAll[val]["prompt"].replace(", {positive}", "").replace("{positive}", "")
            if "negative_prompt" in Comfly_mjstyle.styleAll[val]:
                style_negative += ', ' + Comfly_mjstyle.styleAll[val]['negative_prompt'] if negative else Comfly_mjstyle.styleAll[val]['negative_prompt']

        style_positive = self.replace_repeat(style_positive) if style_positive else ""
        style_negative = self.replace_repeat(style_negative) if style_negative else ""

        return (style_positive, style_negative)


class Comfly_mj_video(ComflyBaseNode):
    """
    Comfly_mj_video node
    Generates videos using Midjourney's video API based on text prompts or text+image combination.
    """
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "motion": (["Low", "high"], {"default": "Low"}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "image": ("IMAGE",),
                "notify_hook": ("STRING", {"default": ""}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
            }
        }
    
    RETURN_TYPES = (IO.VIDEO, IO.VIDEO, IO.VIDEO, IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video1", "video2", "video3", "video4", "task_id", "response")
    FUNCTION = "generate_video"
    CATEGORY = "Comfly-v2/Midjourney"

    def __init__(self):
        super().__init__()
        self.api_key = get_config().get('api_key', '')

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def image_to_base64(self, image_tensor):
        """Convert tensor to base64 string with data URI prefix"""
        if image_tensor is None:
            return None
            
        pil_image = tensor2pil(image_tensor)[0]
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        base64_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return base64_str  

    def extract_video_urls(self, response_data):
        video_urls = []
 
        if "video_urls" in response_data and response_data["video_urls"]:
            print(f"Found video_urls field: {response_data['video_urls']}")
            try:
                if isinstance(response_data["video_urls"], str):
                    video_urls_json = json.loads(response_data["video_urls"])
                    print(f"Parsed video_urls JSON: {json.dumps(video_urls_json, indent=2)}")
                    
                    if isinstance(video_urls_json, list):
                        urls = [item["url"] for item in video_urls_json if "url" in item]
                        if urls:
                            video_urls = urls
                            print(f"Extracted {len(urls)} URLs from video_urls list")
                        else:
                            print("No 'url' keys found in video_urls items")
                    else:
                        print(f"video_urls_json is not a list: {type(video_urls_json)}")
                elif isinstance(response_data["video_urls"], list):
                    urls = [item["url"] for item in response_data["video_urls"] if "url" in item]
                    if urls:
                        video_urls = urls
                        print(f"Extracted {len(urls)} URLs directly from video_urls list")
                    else:
                        print("No 'url' keys found in video_urls items")
                else:
                    print(f"video_urls is neither string nor list: {type(response_data['video_urls'])}")
            except json.JSONDecodeError as e:
                print(f"JSONDecodeError when parsing video_urls: {str(e)}")

                if isinstance(response_data["video_urls"], str) and response_data["video_urls"].startswith("http"):
                    video_urls = [response_data["video_urls"]]
                    print(f"Using video_urls as a direct URL: {response_data['video_urls']}")
            except Exception as e:
                print(f"Unexpected error when processing video_urls: {str(e)}")

        if not video_urls:
            if "videoUrl" in response_data and response_data["videoUrl"]:
                video_urls = [response_data["videoUrl"]]
                print(f"Using videoUrl field: {response_data['videoUrl']}")
            elif "video_url" in response_data and response_data["video_url"]:
                video_urls = [response_data["video_url"]]
                print(f"Using video_url field: {response_data['video_url']}")

            if "properties" in response_data and response_data["properties"]:
                try:
                    if isinstance(response_data["properties"], str):
                        props = json.loads(response_data["properties"])
                        if "messageHash" in props:
                            msg_hash = props["messageHash"]
                            print(f"Found messageHash in properties: {msg_hash}")
                except Exception as e:
                    print(f"Error processing properties field: {str(e)}")

        if not video_urls:
            response_str = json.dumps(response_data)
            video_url_pattern = r'https?://\S+\.mp4'
            found_urls = re.findall(video_url_pattern, response_str)
            if found_urls:
                video_urls = found_urls
                print(f"Found {len(found_urls)} video URLs using regex: {found_urls}")
        
        print(f"Final extracted video URLs: {video_urls}")
        return video_urls

    def generate_video(self, prompt, motion="Low", api_key="", image=None, notify_hook="", seed=0):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        if not self.api_key:
            error_response = json.dumps({
                "status": "error",
                "message": "API key not provided. Please set your API key."
            })
            empty_adapters = [ComflyVideoAdapter("") for _ in range(4)]
            return (*empty_adapters, "", error_response)
            
        pbar = comfy.utils.ProgressBar(100)
        pbar.update_absolute(10)
        
        try:
            payload = {
                "prompt": prompt,
                "motion": motion,
                "notifyHook": notify_hook
            }

            if seed > 0:
                payload["seed"] = seed
 
            if image is not None:
                pbar.update_absolute(20)
                print("Processing input image...")
                image_base64 = self.image_to_base64(image)
                if image_base64:
                    payload["image"] = image_base64
                else:
                    print("Warning: Failed to convert image to base64")

            print("Submitting video generation request...")
            try:
                response = requests.post(
                    f"{baseurl}/mj/submit/video", 
                    headers=self.get_headers(),
                    json=payload,
                    timeout=(30, 90)  
                )
                response.raise_for_status()
            except requests.exceptions.Timeout:
                error_message = "API request timed out during submission"
                print(error_message)
                error_response = json.dumps({"status": "error", "message": error_message})
                empty_adapters = [ComflyVideoAdapter("") for _ in range(4)]
                return (*empty_adapters, "", error_response)
            except requests.exceptions.RequestException as e:
                error_message = f"API request error during submission: {str(e)}"
                print(error_message)
                error_response = json.dumps({"status": "error", "message": error_message})
                empty_adapters = [ComflyVideoAdapter("") for _ in range(4)]
                return (*empty_adapters, "", error_response)
            
            result = response.json()
            
            if "result" not in result:
                error_message = f"No task ID in response: {result}"
                print(error_message)
                error_response = json.dumps({
                    "status": "error", 
                    "message": error_message
                })
                empty_adapters = [ComflyVideoAdapter("") for _ in range(4)]
                return (*empty_adapters, "", error_response)
                
            task_id = result["result"]
            print(f"Video generation task submitted successfully. Task ID: {task_id}")
            
            pbar.update_absolute(40)
            print("Waiting for video generation to complete...")

            task_result = {"status": "PENDING", "progress": "0%"}
            max_retries = 120  
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    status_response = requests.get(
                        f"{baseurl}/mj/task/{task_id}/fetch",
                        headers=self.get_headers(),
                        timeout=(10, 30)  
                    )
                    status_response.raise_for_status()
                    
                    task_result = status_response.json()

                    if task_result.get("status") == "FAILURE":
                        fail_reason = task_result.get("fail_reason", "Unknown failure reason")
                        error_message = f"Video generation failed: {fail_reason}"
                        print(error_message)
                        error_response = json.dumps({
                            "status": "error", 
                            "message": error_message
                        })
                        empty_adapters = [ComflyVideoAdapter("") for _ in range(4)]
                        return (*empty_adapters, task_id, error_response)

                    progress = task_result.get("progress", "0%")
                    try:
                        if isinstance(progress, str) and progress.endswith('%'):
                            progress_int = int(progress[:-1])  
                            pbar.update_absolute(progress_int)
                    except (ValueError, TypeError):

                        progress_estimate = min(80, 40 + (retry_count * 40 // max_retries))
                        pbar.update_absolute(progress_estimate)
                    
                    if task_result.get("status") == "SUCCESS":
                        print("Video generation completed. Processing results...")
                        break
                        
                except requests.exceptions.Timeout:
                    print(f"Timeout while checking task status (retry {retry_count+1}/{max_retries})")
                except requests.exceptions.RequestException as e:
                    print(f"Error checking task status (retry {retry_count+1}/{max_retries}): {str(e)}")
                except Exception as e:
                    print(f"Unexpected error (retry {retry_count+1}/{max_retries}): {str(e)}")
                
                time.sleep(5)  
                retry_count += 1

            if retry_count >= max_retries and task_result.get("status") != "SUCCESS":
                print(f"Warning: Maximum retries ({max_retries}) reached. Proceeding with current result.")
            
            pbar.update_absolute(90)
            video_urls = self.extract_video_urls(task_result)
        
            if not video_urls:
                error_message = "No video URLs found in response"
                print(error_message)
                error_response = json.dumps({
                    "status": "error",
                    "message": error_message,
                    "task_id": task_id,
                    "response_data": task_result
                })
                empty_adapters = [ComflyVideoAdapter("") for _ in range(4)]
                return (*empty_adapters, task_id, error_response)

            video_adapters = []
            for url in video_urls:
                video_adapters.append(ComflyVideoAdapter(url))

            while len(video_adapters) < 4:
                video_adapters.append(ComflyVideoAdapter(""))

            success_response = json.dumps({
                "status": "success",
                "message": f"Generated {len(video_urls)} videos successfully",
                "task_id": task_id,
                "video_urls": video_urls
            })

            pbar.update_absolute(100)
            return (video_adapters[0], video_adapters[1], video_adapters[2], video_adapters[3], 
                   task_id, success_response)
                
        except Exception as e:
            error_message = f"Error in video generation: {str(e)}"
            print(error_message)
            error_response = json.dumps({
                "status": "error",
                "message": error_message
            })

            empty_adapters = [ComflyVideoAdapter("") for _ in range(4)]
            return (*empty_adapters, "", error_response)


class Comfly_mj_video_extend(ComflyBaseNode):
    """
    Comfly_mj_video_extend node
    Extends a Midjourney video based on a task ID.
    """
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {"default": "", "multiline": False, "forceInput": True}),
                "index": ([0, 1, 2, 3], {"default": 0}),   
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
            }
        }
    
    RETURN_TYPES = (IO.VIDEO, IO.VIDEO, IO.VIDEO, IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video1", "video2", "video3", "video4", "task_id", "response")
    FUNCTION = "extend_video"
    CATEGORY = "Comfly-v2/Midjourney"

    def __init__(self):
        super().__init__()
        self.api_key = get_config().get('api_key', '')

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def extend_video(self, task_id, index=0, api_key=""):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        if not self.api_key:
            error_message = "API key not provided. Please set your API key."
            print(error_message)
            empty_adapters = [ComflyVideoAdapter("") for _ in range(4)]
            return (*empty_adapters, "", error_message)
            
        pbar = comfy.utils.ProgressBar(100)
        pbar.update_absolute(10)
        
        try:
            payload = {
                "action": "extend",
                "index": index,
                "taskId": task_id
            }
                
            pbar.update_absolute(30)
            print("Submitting video extension request...")

            response = requests.post(
                f"{baseurl}/mj/submit/video",
                headers=self.get_headers(),
                json=payload
            )
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                empty_adapters = [ComflyVideoAdapter("") for _ in range(4)]
                return (*empty_adapters, "", error_message)
                
            result = response.json()
            if result.get("code") != 1:
                error_message = f"API Error: {result.get('description', 'Unknown error')}"
                print(error_message)
                empty_adapters = [ComflyVideoAdapter("") for _ in range(4)]
                return (*empty_adapters, "", error_message)
            
            new_task_id = result["result"]
            print(f"Video extension task submitted successfully. Task ID: {new_task_id}")
            
            pbar.update_absolute(40)
            print("Waiting for video extension to complete...")

            video_urls = []
            
            while True:
                try:
                    status_response = requests.get(
                        f"{baseurl}/mj/task/{new_task_id}/fetch",
                        headers=self.get_headers()
                    )
                    
                    if status_response.status_code != 200:
                        time.sleep(2)
                        continue
                        
                    status_result = status_response.json()

                    if status_result.get("status") == "FAILURE":
                        fail_reason = status_result.get("fail_reason", "Unknown failure reason")
                        error_message = f"Video extension failed: {fail_reason}"
                        print(error_message)
                        empty_adapters = [ComflyVideoAdapter("") for _ in range(4)]
                        return (*empty_adapters, new_task_id, error_message)

                    progress = status_result.get("progress", "0%")
                    try:
                        progress_int = int(progress[:-1])  
                        pbar.update_absolute(progress_int)
                    except (ValueError, TypeError):

                        pass
                    
                    if status_result.get("status") == "SUCCESS":
                        if "video_urls" in status_result:
                            try:
                                if isinstance(status_result["video_urls"], str):
                                    video_urls_data = json.loads(status_result["video_urls"])
                                    if isinstance(video_urls_data, list):
                                        for item in video_urls_data:
                                            if isinstance(item, dict) and "url" in item:
                                                video_urls.append(item["url"])
                                elif isinstance(status_result["video_urls"], list):
                                    # Direct list
                                    for item in status_result["video_urls"]:
                                        if isinstance(item, dict) and "url" in item:
                                            video_urls.append(item["url"])
                            except Exception as e:
                                print(f"Error parsing video_urls: {str(e)}")

                        if not video_urls:
                            if "videoUrl" in status_result and status_result["videoUrl"]:
                                video_urls.append(status_result["videoUrl"])
                            elif "video_url" in status_result and status_result["video_url"]:
                                video_urls.append(status_result["video_url"])

                        if video_urls:
                            break

                        if "properties" in status_result:
                            try:
                                props = status_result["properties"]
                                if isinstance(props, str):
                                    props_data = json.loads(props)
                                    if "videoUrl" in props_data:
                                        video_urls.append(props_data["videoUrl"])
                                elif isinstance(props, dict) and "videoUrl" in props:
                                    video_urls.append(props["videoUrl"])
                            except Exception as e:
                                print(f"Error parsing properties: {str(e)}")

                        if video_urls:
                            break

                        response_str = json.dumps(status_result)
                        video_url_pattern = r'https?://\S+\.mp4'
                        found_urls = re.findall(video_url_pattern, response_str)
                        if found_urls:
                            video_urls.extend(found_urls)
                            break

                        if status_result.get("status") == "SUCCESS":
                            print("Task completed successfully but no video URLs found in response")
                            break
                            
                    time.sleep(2) 
                    
                except Exception as e:
                    print(f"Error checking task status: {str(e)}")
                    time.sleep(2)
            
            if not video_urls:
                error_message = "Failed to retrieve video URLs from the response"
                print(error_message)
                empty_adapters = [ComflyVideoAdapter("") for _ in range(4)]
                return (*empty_adapters, new_task_id, error_message)

            video_adapters = []
            for url in video_urls:
                video_adapters.append(ComflyVideoAdapter(url))

            while len(video_adapters) < 4:
                video_adapters.append(ComflyVideoAdapter(""))
                
            pbar.update_absolute(100)
            
            success_response = json.dumps({
                "status": "success",
                "message": f"Extended {len(video_urls)} videos successfully",
                "task_id": new_task_id,
                "video_urls": video_urls
            })
            
            return (video_adapters[0], video_adapters[1], video_adapters[2], video_adapters[3], 
                   new_task_id, success_response)
            
        except Exception as e:
            error_message = f"Error in video extension: {str(e)}"
            print(error_message)
            empty_adapters = [ComflyVideoAdapter("") for _ in range(4)]
            return (*empty_adapters, "", error_message)



############################# Kling ###########################

class Comfly_kling_text2video:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "model_name": (["kling-v2-1-master", "kling-v2-master", "kling-v1-6", "kling-v1-5", "kling-v1"], {"default": "kling-v1-6"}),
                "imagination": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05}),
                "aspect_ratio": (["1:1", "16:9", "9:16"], {"default": "1:1"}),
                "mode": (["std", "pro"], {"default": "std"}),
                "duration": (["5", "10"], {"default": "5"}),
                "num_videos": ("INT", {"default": 1, "min": 1, "max": 4}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647})
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "camera": (["none", "horizontal", "vertical", "zoom", "vertical_shake", "horizontal_shake", 
                          "rotate", "master_down_zoom", "master_zoom_up", "master_right_rotate_zoom", 
                          "master_left_rotate_zoom"], {"default": "none"}),
                "camera_value": ("FLOAT", {"default": 0, "min": -10, "max": 10, "step": 0.1})
            }
        }

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "video_id", "response")
    FUNCTION = "generate_video"
    CATEGORY = "Comfly-v2/Comfly_kling"

    def __init__(self):
        super().__init__()
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300
        self.model_capabilities = {
            "kling-v1": {
                "std": {
                    "5": {"video": True, "camera": True},
                    "10": {"video": True, "camera": False}
                },
                "pro": {
                    "5": {"video": True, "camera": False},
                    "10": {"video": True, "camera": False}
                }
            },
            "kling-v1-5": {
                "std": {
                    "5": {"video": False, "camera": False},
                    "10": {"video": False, "camera": False}
                },
                "pro": {
                    "5": {"video": False, "camera": True},
                    "10": {"video": False, "camera": False}
                }
            },
            "kling-v1-6": {
                "std": {
                    "5": {"video": True, "camera": False},
                    "10": {"video": True, "camera": False}
                },
                "pro": {
                    "5": {"video": False, "camera": False},
                    "10": {"video": False, "camera": False}
                }
            },
            "kling-v2-master": {
                "std": {
                    "5": {"video": False, "camera": False},
                    "10": {"video": False, "camera": False}
                },
                "pro": {
                    "5": {"video": False, "camera": False},
                    "10": {"video": False, "camera": False}
                }
            }
        }

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
    def get_camera_json(self, camera, camera_value=0):
        camera_mappings = {
            "none": {"type":"empty","horizontal":0,"vertical":0,"zoom":0,"tilt":0,"pan":0,"roll":0},
            "horizontal": {"type":"horizontal","horizontal":camera_value,"vertical":0,"zoom":0,"tilt":0,"pan":0,"roll":0}, 
            "vertical": {"type":"vertical","horizontal":0,"vertical":camera_value,"zoom":0,"tilt":0,"pan":0,"roll":0},
            "zoom": {"type":"zoom","horizontal":0,"vertical":0,"zoom":camera_value,"tilt":0,"pan":0,"roll":0},
            "vertical_shake": {"type":"vertical_shake","horizontal":0,"vertical":camera_value,"zoom":0.5,"tilt":0,"pan":0,"roll":0},
            "horizontal_shake": {"type":"horizontal_shake","horizontal":camera_value,"vertical":0,"zoom":0.5,"tilt":0,"pan":0,"roll":0}, 
            "rotate": {"type":"rotate","horizontal":0,"vertical":0,"zoom":0,"tilt":0,"pan":camera_value,"roll":0},
            "master_down_zoom": {"type":"zoom","horizontal":0,"vertical":0,"zoom":camera_value,"tilt":camera_value,"pan":0,"roll":0},
            "master_zoom_up": {"type":"zoom","horizontal":0.2,"vertical":0,"zoom":camera_value,"tilt":0,"pan":0,"roll":0},
            "master_right_rotate_zoom": {"type":"rotate","horizontal":0,"vertical":0,"zoom":camera_value,"tilt":0,"pan":0,"roll":camera_value},
            "master_left_rotate_zoom": {"type":"rotate","horizontal":0,"vertical":0,"zoom":camera_value,"tilt":0,"pan":camera_value,"roll":0},
        }
        return json.dumps(camera_mappings.get(camera, camera_mappings["none"]))

    def generate_video(self, prompt, model_name, imagination, aspect_ratio, mode, duration, num_videos, 
                  negative_prompt="", camera="none", camera_value=0, seed=0, api_key=""):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        if not self.api_key:
            error_response = {"task_status": "failed", "task_status_msg": "API key not found in Comflyapi.json"}
            return ("", "", "", "", json.dumps(error_response))
            
        camera_json = {}
        if model_name == "kling-v1":  
            camera_json = self.get_camera_json(camera, camera_value)
        else:
            camera_json = self.get_camera_json("none", 0)
            
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "image": "",
            "image_tail": "",
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "model_name": model_name,
            "imagination": imagination,
            "num_videos": num_videos,
            "camera_json": camera_json,
            "seed": seed
        }

        if model_name != "kling-v2-master":
            payload["mode"] = mode
        else:
            print("Note: kling-v2-master model doesn't use mode parameter")
            
        try:
            pbar = comfy.utils.ProgressBar(100)  
            response = requests.post(
                f"{baseurl}/kling/v1/videos/text2video",
                headers=self.get_headers(),
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            if result["code"] != 0:
                error_response = {"task_status": "failed", "task_status_msg": f"API Error: {result['message']}"}
                return ("", "", "", "", json.dumps(error_response))
                
            task_id = result["data"]["task_id"]
            pbar.update_absolute(5)  
            
            last_status = {}
            while True:
                time.sleep(2)
                status_response = requests.get(
                    f"{baseurl}/kling/v1/videos/text2video/{task_id}",
                    headers=self.get_headers()
                )
                status_response.raise_for_status()
                status_result = status_response.json()
                last_status = status_result["data"]
                
                progress = status_result["data"].get("progress", 0)
                pbar.update_absolute(progress)
                
                if status_result["data"]["task_status"] == "succeed":
                    pbar.update_absolute(100) 
                    video_url = status_result["data"]["task_result"]["videos"][0]["url"]
                    video_id = status_result["data"]["task_result"]["videos"][0]["id"]

                    response_data = {
                        "task_status": "succeed",
                        "task_status_msg": "Video generated successfully",
                        "progress": 100,
                        "video_url": video_url  
                    }
                    
                    video_adapter = ComflyVideoAdapter(video_url)
                    return (video_adapter, video_url, task_id, video_id, json.dumps(response_data))
                
                elif status_result["data"]["task_status"] == "failed":
                    error_msg = status_result["data"].get("task_status_msg", "Unknown error")
                    error_response = {
                        "task_status": "failed", 
                        "task_status_msg": error_msg,
                    }
                    print(f"Task failed: {error_msg}")
                    return ("", "", task_id, "", json.dumps(error_response))
        except Exception as e:
            error_response = {"task_status": "failed", "task_status_msg": f"Error generating video: {str(e)}"}
            print(f"Error generating video: {str(e)}")
            return ("", "", "", "", json.dumps(error_response))



class Comfly_kling_image2video:
    @classmethod 
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "prompt": ("STRING", {"multiline": True}),
                "model_name": (["kling-v2-1", "kling-v2-1-master", "kling-v2-master", "kling-v1-6", "kling-v1-5", "kling-v1"], {"default": "kling-v1-6"}),
                "imagination": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05}),
                "aspect_ratio": (["1:1", "16:9", "9:16"], {"default": "1:1"}),
                "mode": (["std", "pro"], {"default": "std"}),
                "duration": (["5", "10"], {"default": "5"}),
                "num_videos": ("INT", {"default": 1, "min": 1, "max": 4}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647})
            },
            "optional": {
                "image_tail": ("IMAGE",),
                "api_key": ("STRING", {"default": ""}),
                "camera": (["none", "horizontal", "vertical", "zoom", "vertical_shake", "horizontal_shake", 
                          "rotate", "master_down_zoom", "master_zoom_up", "master_right_rotate_zoom", 
                          "master_left_rotate_zoom"], {"default": "none"}),
                "camera_value": ("FLOAT", {"default": 0, "min": -10, "max": 10, "step": 0.1}),      
            }
        }

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "video_id", "response")
    FUNCTION = "generate_video"
    CATEGORY = "Comfly-v2/Comfly_kling"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300
        self.model_compatibility = {
            "kling-v1": {
                "std": {"5": True, "10": True},  
                "pro": {"5": True, "10": True}
            },
            "kling-v1-5": {
                "std": {"5": False, "10": False},  
                "pro": {"5": True, "10": True}
            },
            "kling-v1-6": {
                "std": {"5": False, "10": False},  
                "pro": {"5": True, "10": True}
            },
            "kling-v2-master": {
                "std": {"5": False, "10": False},
                "pro": {"5": False, "10": False}
            },
            "kling-v2-1": {
                "std": {"5": False, "10": False},  
                "pro": {"5": True, "10": True}  
            }
        }

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
    def check_tail_image_compatibility(self, model_name, mode, duration):
        try:
            if model_name == "kling-v2-1":
                return mode == "pro"
            
            return self.model_compatibility.get(model_name, {}).get(mode, {}).get(duration, False)
        except:
            return False

    def generate_video(self, image, prompt, model_name, imagination, aspect_ratio, mode, duration, 
                  num_videos, negative_prompt="", camera="none", camera_value=0, seed=0, image_tail=None, api_key=""):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        if not self.api_key:
            error_response = {"task_status": "failed", "task_status_msg": "API key not found in Comflyapi.json"}
            return ("", "", "", "", json.dumps(error_response))

        has_tail_image = image_tail is not None

        if has_tail_image:
            check_mode = "std" if model_name == "kling-v2-master" else mode
            tail_compatible = self.check_tail_image_compatibility(model_name, check_mode, duration)
            if not tail_compatible:
                warning_message = f"Warning: model/mode/duration({model_name}/{mode if model_name != 'kling-v2-master' else 'N/A'}/{duration}) does not support using both image and image_tail."
                print(warning_message)

                if model_name == "kling-v1-5" or model_name == "kling-v1-6":
                    if mode == "std":
                        suggestion = "\nSuggestion: Try switching to 'pro' mode which supports tail images."
                        warning_message += suggestion
                
                error_response = {
                    "task_status": "failed", 
                    "task_status_msg": warning_message
                }
                return ("", "", "", "", json.dumps(error_response))
        
        camera_json = {}
        if model_name in ["kling-v1-5", "kling-v1-6"] and mode == "pro" and camera != "none": 
            camera_json = self.get_camera_json(camera, camera_value)
        else:
            camera_json = self.get_camera_json("none", 0)
            
        try:
            pil_image = tensor2pil(image)[0]
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
            buffered = BytesIO()
            pil_image.save(buffered, format="JPEG", quality=95)
            image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            image_tail_base64 = ""
            if has_tail_image:
                pil_tail = tensor2pil(image_tail)[0]
                if pil_tail.mode != 'RGB':
                    pil_tail = pil_tail.convert('RGB')
                tail_buffered = BytesIO()
                pil_tail.save(tail_buffered, format="JPEG", quality=95)
                image_tail_base64 = base64.b64encode(tail_buffered.getvalue()).decode('utf-8')

            payload = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "image": image_base64,
                "image_tail": image_tail_base64,
                "aspect_ratio": aspect_ratio,
                "duration": duration,
                "model_name": model_name,
                "imagination": imagination,  
                "num_videos": num_videos,
                "camera_json": camera_json if isinstance(camera_json, str) else json.dumps(camera_json),
                "seed": seed
            }
            
            if model_name != "kling-v2-master":
                payload["mode"] = mode

            print(f"Sending request with parameters: model={model_name}, duration={duration}, aspect_ratio={aspect_ratio}")
            if model_name != "kling-v2-master":
                print(f"Mode: {mode}")
            else:
                print("Note: kling-v2-master model doesn't use mode parameter")
                
            print(f"Image base64 length: {len(image_base64)}")
            if has_tail_image:
                print(f"Image tail base64 length: {len(image_tail_base64)}")
            
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(5)  
            response = requests.post(
                f"{baseurl}/kling/v1/videos/image2video",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )

            print(f"Response status: {response.status_code}")
            if response.status_code != 200:
                error_message = f"Error: {response.status_code} {response.reason} - {response.text}"
                print(error_message)
                error_response = {"task_status": "failed", "task_status_msg": error_message}
                return ("", "", "", "", json.dumps(error_response))
            
            result = response.json()
            if result["code"] != 0:
                error_response = {"task_status": "failed", "task_status_msg": f"API Error: {result['message']}"}
                return ("", "", "", "", json.dumps(error_response))
                
            task_id = result["data"]["task_id"]
            pbar.update_absolute(10) 
            
            last_status = {}
            while True:
                time.sleep(2)
                status_response = requests.get(
                    f"{baseurl}/kling/v1/videos/image2video/{task_id}",
                    headers=self.get_headers(),
                    timeout=self.timeout
                )
                status_response.raise_for_status()
                status_result = status_response.json()
                last_status = status_result["data"]

                progress = 0
                if status_result["data"]["task_status"] == "processing":
                    progress = status_result["data"].get("progress", 50)
                elif status_result["data"]["task_status"] == "succeed":
                    progress = 100
                
                pbar.update_absolute(progress)
                
                if status_result["data"]["task_status"] == "succeed":
                    pbar.update_absolute(100) 
                    video_url = status_result["data"]["task_result"]["videos"][0]["url"]
                    video_id = status_result["data"]["task_result"]["videos"][0]["id"]
                    
                    response_data = {
                        "task_status": "succeed",
                        "task_status_msg": "Video generated successfully",
                        "progress": 100,
                        "video_url": video_url
                    }
                    
                    video_adapter = ComflyVideoAdapter(video_url)
                    return (video_adapter, video_url, task_id, video_id, json.dumps(response_data))
                
                elif status_result["data"]["task_status"] == "failed":
                    error_msg = status_result["data"].get("task_status_msg", "Unknown error")
                    error_response = {
                        "task_status": "failed", 
                        "task_status_msg": error_msg,
                    }
                    print(f"Task failed: {error_msg}")
                    return ("", "", task_id, "", json.dumps(error_response))
        except Exception as e:
            error_response = {"task_status": "failed", "task_status_msg": f"Error generating video: {str(e)}"}
            print(f"Error generating video: {str(e)}")
            return ("", "", "", "", json.dumps(error_response))

    def get_camera_json(self, camera, camera_value=0):
        camera_mappings = {
            "none": {"type":"empty","horizontal":0,"vertical":0,"zoom":0,"tilt":0,"pan":0,"roll":0},
            "horizontal": {"type":"horizontal","horizontal":camera_value,"vertical":0,"zoom":0,"tilt":0,"pan":0,"roll":0}, 
            "vertical": {"type":"vertical","horizontal":0,"vertical":camera_value,"zoom":0,"tilt":0,"pan":0,"roll":0},
            "zoom": {"type":"zoom","horizontal":0,"vertical":0,"zoom":camera_value,"tilt":0,"pan":0,"roll":0},
            "vertical_shake": {"type":"vertical_shake","horizontal":0,"vertical":camera_value,"zoom":0.5,"tilt":0,"pan":0,"roll":0},
            "horizontal_shake": {"type":"horizontal_shake","horizontal":camera_value,"vertical":0,"zoom":0.5,"tilt":0,"pan":0,"roll":0}, 
            "rotate": {"type":"rotate","horizontal":0,"vertical":0,"zoom":0,"tilt":0,"pan":camera_value,"roll":0},
            "master_down_zoom": {"type":"zoom","horizontal":0,"vertical":0,"zoom":camera_value,"tilt":camera_value,"pan":0,"roll":0},
            "master_zoom_up": {"type":"zoom","horizontal":0.2,"vertical":0,"zoom":camera_value,"tilt":0,"pan":0,"roll":0},
            "master_right_rotate_zoom": {"type":"rotate","horizontal":0,"vertical":0,"zoom":camera_value,"tilt":0,"pan":0,"roll":camera_value},
            "master_left_rotate_zoom": {"type":"rotate","horizontal":0,"vertical":0,"zoom":camera_value,"tilt":0,"pan":camera_value,"roll":0},
        }
        return json.dumps(camera_mappings.get(camera, camera_mappings["none"]))


class Comfly_kling_multi_image2video:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "model_name": (["kling-v1-6"], {"default": "kling-v1-6"}),
                "mode": (["std", "pro"], {"default": "std"}),
                "duration": (["5", "10"], {"default": "5"}),
                "aspect_ratio": (["16:9", "9:16", "1:1"], {"default": "16:9"}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
            },
            "optional": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "image3": ("IMAGE",),
                "image4": ("IMAGE",),
                "api_key": ("STRING", {"default": ""}),
                "max_retries": ("INT", {"default": 10, "min": 1, "max": 30}),
                "initial_timeout": ("INT", {"default": 600, "min": 30, "max": 900}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647})
            }
        }

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "video_id", "response")
    FUNCTION = "generate_video"
    CATEGORY = "Comfly-v2/Comfly_kling"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300
        self.session = requests.Session()
        retry_strategy = requests.packages.urllib3.util.retry.Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def image_to_base64(self, image_tensor):
        """Convert tensor to base64 string without data URI prefix"""
        if image_tensor is None:
            return None
            
        try:
            pil_image = tensor2pil(image_tensor)[0]
            buffered = BytesIO()
            pil_image.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
        except Exception as e:
            print(f"Error converting image to base64: {str(e)}")
            return None
    
    def make_request_with_retry(self, method, url, **kwargs):
        max_retries = kwargs.pop('max_retries', 10)
        initial_timeout = kwargs.pop('initial_timeout', self.timeout)
        
        for attempt in range(1, max_retries + 1):
            current_timeout = min(initial_timeout * (2 ** (attempt - 1)), 900)  
            
            try:
                kwargs['timeout'] = current_timeout
                
                if method.lower() == 'get':
                    response = self.session.get(url, **kwargs)
                else:
                    response = self.session.post(url, **kwargs)
                
                response.raise_for_status()
                return response
            
            except requests.exceptions.Timeout as e:
                if attempt == max_retries:
                    raise
                wait_time = min(2 ** (attempt - 1), 60)  
                time.sleep(wait_time)
            
            except requests.exceptions.ConnectionError as e:
                if attempt == max_retries:
                    raise
                wait_time = min(2 ** (attempt - 1), 60)
                time.sleep(wait_time)
            
            except requests.exceptions.HTTPError as e:
                if e.response.status_code in (400, 401, 403):
                    print(f"Client error: {str(e)}")
                    raise
                if attempt == max_retries:
                    raise
                wait_time = min(2 ** (attempt - 1), 60)
                time.sleep(wait_time)
            
            except Exception as e:
                if attempt == max_retries:
                    raise
                wait_time = min(2 ** (attempt - 1), 60)
                time.sleep(wait_time)
    
    def poll_task_status(self, task_id, max_attempts=100, initial_interval=2, max_interval=60, headers=None, pbar=None):
        attempt = 0
        interval = initial_interval
        last_status = None
        
        while attempt < max_attempts:
            attempt += 1
            
            try:
                status_response = self.make_request_with_retry(
                    'get',
                    f"{baseurl}/kling/v1/videos/multi-image2video/{task_id}",
                    headers=headers
                )
                
                status_result = status_response.json()
                
                if status_result["code"] != 0:
                    print(f"API returned error code: {status_result['code']} - {status_result['message']}")
                    if status_result["code"] in (400, 401, 403): 
                        return {"task_status": "failed", "task_status_msg": status_result["message"]}
                    time.sleep(interval)
                    interval = min(interval * 1.5, max_interval)
                    continue
                
                last_status = status_result["data"]

                if pbar:
                    progress = 0
                    if last_status["task_status"] == "processing":
                        progress = 50
                    elif last_status["task_status"] == "succeed":
                        progress = 100
                    pbar.update_absolute(progress)

                if last_status["task_status"] == "succeed":
                    return last_status
                elif last_status["task_status"] == "failed":
                    return last_status

                if last_status["task_status"] == "processing":
                    interval = min(interval * 1.2, max_interval) 
                else:
                    interval = max(interval * 0.8, initial_interval)  
                    
                time.sleep(interval)
                
            except Exception as e:
                time.sleep(interval)
                interval = min(interval * 2, max_interval)

        if last_status:
            return last_status
        else:
            return {"task_status": "failed", "task_status_msg": "Maximum polling attempts reached without getting a valid status"}
    
    def generate_video(self, prompt, model_name, mode, duration, aspect_ratio, negative_prompt="", 
                  image1=None, image2=None, image3=None, image4=None, api_key="", 
                  max_retries=10, initial_timeout=300, seed=0):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        if not self.api_key:
            error_response = {"task_status": "failed", "task_status_msg": "API key not found in Comflyapi.json"}
            return ("", "", "", "", json.dumps(error_response))
            
        pbar = comfy.utils.ProgressBar(100)
        pbar.update_absolute(10)
        
        try:
            image_list = []
            for idx, img in enumerate([image1, image2, image3, image4], 1):
                if img is not None:
                    base64_str = self.image_to_base64(img)
                    if base64_str:
                        image_list.append({"image": base64_str})
                    
            if not image_list:
                error_response = {"task_status": "failed", "task_status_msg": "No valid images provided"}
                return ("", "", "", "", json.dumps(error_response))

            payload = {
                "model_name": model_name,
                "image_list": image_list,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "mode": mode,
                "duration": duration,
                "aspect_ratio": aspect_ratio
            }
            
            if seed > 0:
                payload["seed"] = seed

            headers = self.get_headers()
            pbar.update_absolute(30)
            
            print("Submitting multi-image video generation request...")
            response = self.make_request_with_retry(
                'post',
                f"{baseurl}/kling/v1/videos/multi-image2video",
                headers=headers,
                json=payload,
                max_retries=max_retries,
                initial_timeout=initial_timeout
            )
            
            result = response.json()
            
            if result["code"] != 0:
                error_message = f"API Error: {result['message']}"
                print(error_message)
                error_response = {"task_status": "failed", "task_status_msg": error_message}
                return ("", "", "", "", json.dumps(error_response))
                
            task_id = result["data"]["task_id"]
            pbar.update_absolute(40)
            print(f"Multi-image video generation task submitted. Task ID: {task_id}")

            print("Waiting for video generation to complete...")
            last_status = self.poll_task_status(
                task_id, 
                max_attempts=100,
                initial_interval=2, 
                max_interval=60,
                headers=headers,
                pbar=pbar
            )
            
            if last_status["task_status"] == "succeed":
                pbar.update_absolute(100)
                video_url = last_status["task_result"]["videos"][0]["url"]
                video_id = last_status["task_result"]["videos"][0]["id"]
                
                response_data = {
                    "task_status": "succeed",
                    "task_status_msg": "Video generated successfully",
                    "progress": 100,
                    "video_url": video_url
                }
                
                video_adapter = ComflyVideoAdapter(video_url)
                return (video_adapter, video_url, task_id, video_id, json.dumps(response_data))
            
            elif last_status["task_status"] == "failed":
                error_msg = last_status.get("task_status_msg", "Unknown error")
                error_response = {
                    "task_status": "failed", 
                    "task_status_msg": error_msg,
                }
                print(f"Task failed: {error_msg}")
                return ("", "", task_id, "", json.dumps(error_response))
            
            else:
                error_msg = f"Unexpected task status: {last_status.get('task_status', 'unknown')}"
                error_response = {
                    "task_status": "failed", 
                    "task_status_msg": error_msg,
                }
                print(f"Task error: {error_msg}")
                return ("", "", task_id, "", json.dumps(error_response))
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            error_response = {"task_status": "failed", "task_status_msg": f"Error generating video: {str(e)}"}
            print(f"Error generating video: {str(e)}")
            return ("", "", "", "", json.dumps(error_response))


class Comfly_video_extend:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_id": ("STRING", {"default": "", "multiline": False, "forceInput": True}),
                "prompt": ("STRING", {"default": "", "multiline": True}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""})
            }
        }

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video", "video_id", "response")
    FUNCTION = "extend_video"
    CATEGORY = "Comfly-v2/Comfly_kling"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def extend_video(self, video_id, prompt="", api_key=""):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        if not self.api_key:
            error_response = {"task_status": "failed", "task_status_msg": "API key not found in Comflyapi.json"}
            return ("", "", json.dumps(error_response))
            
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "video_id": video_id,
            "prompt": prompt
        }
        try:
            response = requests.post(
                f"{baseurl}/kling/v1/videos/video-extend",
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            if result["code"] != 0:
                error_response = {"task_status": "failed", "task_status_msg": f"API Error: {result['message']}"}
                return ("", "", json.dumps(error_response))
                
            task_id = result["data"]["task_id"]
            pbar = comfy.utils.ProgressBar(100)
            
            last_status = {}
            while True:
                time.sleep(2)
                status_response = requests.get(
                    f"{baseurl}/kling/v1/videos/video-extend/{task_id}",
                    headers=headers,
                    timeout=self.timeout
                )
                status_response.raise_for_status()
                status_result = status_response.json()
                last_status = status_result["data"]
                
                progress = 0
                if status_result["data"]["task_status"] == "processing":
                    progress = 50
                elif status_result["data"]["task_status"] == "succeed":
                    progress = 100
                pbar.update_absolute(progress)
                
                if status_result["data"]["task_status"] == "succeed":
                    video_url = status_result["data"]["task_result"]["videos"][0]["url"]
                    new_video_id = status_result["data"]["task_result"]["videos"][0]["id"]
                    
                    response_data = {
                        "task_status": "succeed",
                        "task_status_msg": "Video extended successfully",
                        "progress": 100,
                        "video_url": video_url
                    }
                    
                    video_adapter = ComflyVideoAdapter(video_url)
                    return (video_adapter, new_video_id, json.dumps(response_data))
                
                elif status_result["data"]["task_status"] == "failed":
                    error_msg = status_result["data"].get("task_status_msg", "Unknown error")
                    error_response = {
                        "task_status": "failed", 
                        "task_status_msg": error_msg,
                    }
                    print(f"Task failed: {error_msg}")
                    return ("", "", json.dumps(error_response))
                    
        except Exception as e:
            error_response = {"task_status": "failed", "task_status_msg": f"Error extending video: {str(e)}"}
            print(f"Error extending video: {str(e)}")
            return ("", "", json.dumps(error_response))


class Comfly_lip_sync:
    @classmethod
    def INPUT_TYPES(cls):
        cls.zh_voices = [
            ["阳光少年", "genshin_vindi2"],
            ["懂事小弟", "zhinen_xuesheng"],
            ["运动少年", "tiyuxi_xuedi"],
            ["青春少女", "ai_shatang"],
            ["温柔小妹", "genshin_klee2"],
            ["元气少女", "genshin_kirara"],
            ["阳光男生", "ai_kaiya"],
            ["幽默小哥", "tiexin_nanyou"],
            ["文艺小哥", "ai_chenjiahao_712"],
            ["甜美邻家", "girlfriend_1_speech02"],
            ["温柔姐姐", "chat1_female_new-3"],
            ["职场女青", "girlfriend_2_speech02"],
            ["活泼男童", "cartoon-boy-07"],
            ["俏皮女童", "cartoon-girl-01"],
            ["稳重老爸", "ai_huangyaoshi_712"],
            ["温柔妈妈", "you_pingjing"],
            ["严肃上司", "ai_laoguowang_712"],
            ["优雅贵妇", "chengshu_jiejie"],
            ["慈祥爷爷", "zhuxi_speech02"],
            ["唠叨爷爷", "uk_oldman3"],
            ["唠叨奶奶", "laopopo_speech02"],
            ["和蔼奶奶", "heainainai_speech02"],
            ["东北老铁", "dongbeilaotie_speech02"],
            ["重庆小伙", "chongqingxiaohuo_speech02"],
            ["四川妹子", "chuanmeizi_speech02"],
            ["潮汕大叔", "chaoshandashu_speech02"],
            ["台湾男生", "ai_taiwan_man2_speech02"],
            ["西安掌柜", "xianzhanggui_speech02"],
            ["天津姐姐", "tianjinjiejie_speech02"],
            ["新闻播报男", "diyinnansang_DB_CN_M_04-v2"],
            ["译制片男", "yizhipiannan-v1"],
            ["元气少女", "guanxiaofang-v2"],
            ["撒娇女友", "tianmeixuemei-v1"],
            ["刀片烟嗓", "daopianyansang-v1"],
            ["乖巧正太", "mengwa-v1"]
        ]
        
        cls.en_voices = [
            ["Sunny", "genshin_vindi2"],
            ["Sage", "zhinen_xuesheng"],
            ["Ace", "AOT"],
            ["Blossom", "ai_shatang"],
            ["Peppy", "genshin_klee2"],
            ["Dove", "genshin_kirara"],
            ["Shine", "ai_kaiya"],
            ["Anchor", "oversea_male1"],
            ["Lyric", "ai_chenjiahao_712"],
            ["Melody", "girlfriend_4_speech02"],
            ["Tender", "chat1_female_new-3"],
            ["Siren", "chat_0407_5-1"],
            ["Zippy", "cartoon-boy-07"],
            ["Bud", "uk_boy1"],
            ["Sprite", "cartoon-girl-01"],
            ["Candy", "PeppaPig_platform"],
            ["Beacon", "ai_huangzhong_712"],
            ["Rock", "ai_huangyaoshi_712"],
            ["Titan", "ai_laoguowang_712"],
            ["Grace", "chengshu_jiejie"],
            ["Helen", "you_pingjing"],
            ["Lore", "calm_story1"],
            ["Crag", "uk_man2"],
            ["Prattle", "laopopo_speech02"],
            ["Hearth", "heainainai_speech02"],
            ["The Reader", "reader_en_m-v1"],
            ["Commercial Lady", "commercial_lady_en_f-v1"]
        ]
        
        return {
            "required": {
                "video_id": ("STRING", {"default": "", "multiline": False, "forceInput": True}),
                "task_id": ("STRING", {"default": "", "multiline": False, "forceInput": True}),
                "mode": (["text2video", "audio2video"], {"default": "text2video"}),
                "text": ("STRING", {"multiline": True, "default": ""}),
                "voice_language": (["zh", "en"], {"default": "zh"}),
                "zh_voice": ([name for name, _ in cls.zh_voices], {"default": cls.zh_voices[0][0]}),
                "en_voice": ([name for name, _ in cls.en_voices], {"default": cls.en_voices[0][0]}),
                "voice_speed": ("FLOAT", {"default": 1.0, "min": 0.8, "max": 2.0, "step": 0.1}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647})
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "video_url": ("STRING", {"default": ""}),
                "audio_type": (["file", "url"], {"default": "file"}),
                "audio_file": ("STRING", {"default": ""}),
                "audio_url": ("STRING", {"default": ""})
            }
        }

    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "process_lip_sync"
    CATEGORY = "Comfly-v2/Comfly_kling"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300
        self.zh_voice_map = {name: voice_id for name, voice_id in self.__class__.zh_voices}
        self.en_voice_map = {name: voice_id for name, voice_id in self.__class__.en_voices}
        
    def process_lip_sync(self, video_id, task_id, mode, text, voice_language, zh_voice, en_voice, voice_speed, seed=0,
                    video_url="", audio_type="file", audio_file="", audio_url="", api_key=""):
    
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        if not self.api_key:
            error_response = {"task_status": "failed", "task_status_msg": "API key not found in Comflyapi.json"}
            return ("", "", "", json.dumps(error_response))
        
        if voice_language == "zh":
            voice_id = self.zh_voice_map.get(zh_voice, "")
        else:
            voice_id = self.en_voice_map.get(en_voice, "")
                
        headers = {
            "Content-Type": "application/json", 
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "input": {
                "task_id": task_id,
                "mode": mode,
                "video_id": video_id if video_id else None,
                "video_url": video_url if video_url else None,
                "text": text if mode == "text2video" else None,
                "voice_id": voice_id if mode == "text2video" else None,
                "voice_language": voice_language if mode == "text2video" else None,
                "voice_speed": voice_speed if mode == "text2video" else None,
                "audio_type": audio_type if mode == "audio2video" else None,
                "audio_file": audio_file if mode == "audio2video" and audio_type == "file" else None,
                "audio_url": audio_url if mode == "audio2video" and audio_type == "url" else None,
                "seed": seed
            }
        }
        try:
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(5)  
            response = requests.post(
                f"{baseurl}/kling/v1/videos/lip-sync",
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            if result["code"] != 0:
                error_response = {"task_status": "failed", "task_status_msg": f"API Error: {result['message']}"}
                return ("", "", "", json.dumps(error_response))
                    
            task_id = result["data"]["task_id"]
            pbar.update_absolute(10) 
                
            last_status = {}
            while True:
                time.sleep(2)
                status_response = requests.get(
                    f"{baseurl}/kling/v1/videos/lip-sync/{task_id}",
                    headers=headers,
                    timeout=self.timeout
                )
                status_response.raise_for_status()
                status_result = status_response.json()
                last_status = status_result["data"]
                    
                if status_result["data"]["task_status"] == "processing":
                    progress = status_result["data"].get("progress", 50)  
                    pbar.update_absolute(progress)
                elif status_result["data"]["task_status"] == "succeed":
                    pbar.update_absolute(100)  
                    video_url = status_result["data"]["task_result"]["videos"][0]["url"]

                    response_data = {
                        "task_status": "succeed",
                        "task_status_msg": "Lip sync completed successfully",
                        "progress": 100,
                        "video_url": video_url
                    }
                    
                    video_adapter = ComflyVideoAdapter(video_url)
                    return (video_adapter, video_url, task_id, json.dumps(response_data))
                        
                elif status_result["data"]["task_status"] == "failed":
                    error_msg = status_result["data"].get("task_status_msg", "Unknown error")
                    error_response = {
                        "task_status": "failed", 
                        "task_status_msg": error_msg,
                    }
                    print(f"Task failed: {error_msg}")
                    return ("", "", task_id, json.dumps(error_response))
                        
        except Exception as e:
            error_response = {"task_status": "failed", "task_status_msg": f"Error in lip sync process: {str(e)}"}
            print(f"Error in lip sync process: {str(e)}")
            return ("", "", "", json.dumps(error_response))
   


############################# Gemini ###########################

class ComflyGeminiAPI:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "model": ("STRING", {"default": "gemini-2.0-flash-exp-image", "placeholder": "Enter model name"}),
                "resolution": (
                    [
                        "512x512", 
                        "768x768", 
                        "1024x1024", 
                        "1280x1280", 
                        "1536x1536", 
                        "2048x2048",
                        "object_image size",
                        "subject_image size",
                        "scene_image size"
                    ], 
                    {"default": "1024x1024"}
                ),
                "num_images": ("INT", {"default": 1, "min": 1, "max": 4, "step": 1}),
                "temperature": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "top_p": ("FLOAT", {"default": 0.95, "min": 0.0, "max": 1.0, "step": 0.01}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
                "timeout": ("INT", {"default": 120, "min": 10, "max": 600, "step": 10}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "object_image": ("IMAGE",),  
                "subject_image": ("IMAGE",),
                "scene_image": ("IMAGE",),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("generated_images", "response", "image_url")
    FUNCTION = "process"
    CATEGORY = "Comfly-v2/Google"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 120 

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def image_to_base64(self, image):
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def extract_image_urls(self, response_text):
        image_pattern = r'!\[.*?\]\((.*?)\)'
        matches = re.findall(image_pattern, response_text)

        if not matches:
            url_pattern = r'https?://\S+\.(?:jpg|jpeg|png|gif|webp)'
            matches = re.findall(url_pattern, response_text)
            
        return matches if matches else []

    def resize_to_target_size(self, image, target_size):
        """Resize image to target size while preserving aspect ratio with padding"""

        img_width, img_height = image.size
        target_width, target_height = target_size

        width_ratio = target_width / img_width
        height_ratio = target_height / img_height
        scale = min(width_ratio, height_ratio)

        new_width = int(img_width * scale)
        new_height = int(img_height * scale)

        resized_img = image.resize((new_width, new_height), Image.LANCZOS)

        new_img = Image.new("RGB", (target_width, target_height), (255, 255, 255))

        paste_x = (target_width - new_width) // 2
        paste_y = (target_height - new_height) // 2
 
        new_img.paste(resized_img, (paste_x, paste_y))
        
        return new_img

    def parse_resolution(self, resolution_str):
        """Parse resolution string (e.g., '1024x1024') to width and height"""
        width, height = map(int, resolution_str.split('x'))
        return (width, height)

    def process(self, prompt, model, resolution, num_images, temperature, top_p, seed, timeout=120, 
                object_image=None, subject_image=None, scene_image=None, api_key=""):

        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)

        self.timeout = timeout
        
        try:

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

            target_size = None

            if resolution == "object_image size" and object_image is not None:
                pil_image = tensor2pil(object_image)[0]
                target_size = pil_image.size
            elif resolution == "subject_image size" and subject_image is not None:
                pil_image = tensor2pil(subject_image)[0]
                target_size = pil_image.size
            elif resolution == "scene_image size" and scene_image is not None:
                pil_image = tensor2pil(scene_image)[0]
                target_size = pil_image.size
            else:
                target_size = self.parse_resolution(resolution)

            has_images = object_image is not None or subject_image is not None or scene_image is not None

            content = []

            if has_images:
                content.append({"type": "text", "text": prompt})
 
                image_descriptions = {
                    "object_image": "an object or item",
                    "subject_image": "a subject or character",
                    "scene_image": "a scene or environment"
                }
 
                for image_var, image_tensor in [("object_image", object_image), 
                                             ("subject_image", subject_image), 
                                             ("scene_image", scene_image)]:
                    if image_tensor is not None:
                        pil_image = tensor2pil(image_tensor)[0]
                        image_base64 = self.image_to_base64(pil_image)
                        content.append({
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"}
                        })
            else:

                dimensions = f"{target_size[0]}x{target_size[1]}"
                aspect_ratio = "1:1" if target_size[0] == target_size[1] else f"{target_size[0]}:{target_size[1]}"
                
                if num_images == 1:
                    enhanced_prompt = f"Generate a high-quality, detailed image with dimensions {dimensions} and aspect ratio {aspect_ratio}. Based on this description: {prompt}"
                else:
                    enhanced_prompt = f"Generate {num_images} DIFFERENT high-quality images with VARIED content, each with unique and distinct visual elements, all having the exact same dimensions of {dimensions} and aspect ratio {aspect_ratio}. Important: make sure each image has different content but maintains the same technical dimensions. Based on this description: {prompt}"
                
                content.append({"type": "text", "text": enhanced_prompt})

            messages = [{
                "role": "user",
                "content": content
            }]

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "top_p": top_p,
                "seed": seed if seed > 0 else None,
                "max_tokens": 8192
            }

            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            try:
                response = requests.post(
                    f"{baseurl}/v1/chat/completions",
                    headers=self.get_headers(),
                    json=payload,
                    timeout=self.timeout
                )
                response.raise_for_status()
                result = response.json()
            except requests.exceptions.Timeout:
                raise TimeoutError(f"API request timed out after {self.timeout} seconds")
            except requests.exceptions.RequestException as e:
                raise Exception(f"API request failed: {str(e)}")
            
            pbar.update_absolute(40)

            response_text = result["choices"][0]["message"]["content"]

            formatted_response = f"**User prompt**: {prompt}\n\n**Response** ({timestamp}):\n{response_text}"

            image_urls = self.extract_image_urls(response_text)
            
            if image_urls:
                try:
                    images = []
                    first_image_url = ""  
                    
                    for i, url in enumerate(image_urls):
                        pbar.update_absolute(40 + (i+1) * 50 // len(image_urls))
                        
                        if i == 0:
                            first_image_url = url  
                        
                        try:
                            img_response = requests.get(url, timeout=self.timeout)
                            img_response.raise_for_status()
                            pil_image = Image.open(BytesIO(img_response.content))

                            resized_image = self.resize_to_target_size(pil_image, target_size)

                            img_tensor = pil2tensor(resized_image)
                            images.append(img_tensor)
                            
                        except Exception as img_error:
                            print(f"Error processing image URL {i+1}: {str(img_error)}")
                            continue
                    
                    if images:
                        try:
                            combined_tensor = torch.cat(images, dim=0)
                        except RuntimeError:
                            print("Warning: Images have different sizes, returning first image")
                            combined_tensor = images[0] if images else None
                            
                        pbar.update_absolute(100)
                        return (combined_tensor, formatted_response, first_image_url)
                    else:
                        raise Exception("No images could be processed successfully")
                    
                except Exception as e:
                    print(f"Error processing image URLs: {str(e)}")

            pbar.update_absolute(100)

            reference_image = None
            if object_image is not None:
                reference_image = object_image
            elif subject_image is not None:
                reference_image = subject_image
            elif scene_image is not None:
                reference_image = scene_image
                
            if reference_image is not None:
                return (reference_image, formatted_response, "")
            else:
                default_image = Image.new('RGB', target_size, color='white')
                default_tensor = pil2tensor(default_image)
                return (default_tensor, formatted_response, "")
            
        except TimeoutError as e:
            error_message = f"API timeout error: {str(e)}"
            print(error_message)
            return self.handle_error(object_image, subject_image, scene_image, error_message, resolution)
            
        except Exception as e:
            error_message = f"Error calling Gemini API: {str(e)}"
            print(error_message)
            return self.handle_error(object_image, subject_image, scene_image, error_message, resolution)
    
    def handle_error(self, object_image, subject_image, scene_image, error_message, resolution="1024x1024"):
        """Handle errors with appropriate image output"""
        if object_image is not None:
            return (object_image, error_message, "")
        elif subject_image is not None:
            return (subject_image, error_message, "")
        elif scene_image is not None:
            return (scene_image, error_message, "")
        else:
            if resolution in ["object_image size", "subject_image size", "scene_image size"]:
                target_size = (1024, 1024)  
            else:
                target_size = self.parse_resolution(resolution)
                
            default_image = Image.new('RGB', target_size, color='white')
            default_tensor = pil2tensor(default_image)
            return (default_tensor, error_message, "")



############################# Doubao ###########################

class Comfly_Doubao_Seedream:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "model": ("STRING", {"default": "doubao-seedream-3-0-t2i-250415"}),
                "response_format": (["url", "b64_json"], {"default": "url"}),
                "size": (["1024x1024", "864x1152", "1152x864", "1280x720", "720x1280", "832x1248", 
                         "1248x832", "1512x648", "Custom"], {"default": "1024x1024"}),
                "Custom_size": ("STRING", {"default": "1536x1024", "multiline": False}),
                "guidance_scale": ("FLOAT", {"default": 2.5, "min": 1.0, "max": 10.0, "step": 0.1}),
            },
            "optional": {
                "apikey": ("STRING", {"default": ""}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
                "watermark": ("BOOLEAN", {"default": True})
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "response")
    FUNCTION = "generate_image"
    CATEGORY = "Comfly-v2/Doubao"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def validate_custom_size(self, size_str):
        """Validate a custom size string to ensure it's in the correct format and within allowed range."""
        try:
            if 'x' not in size_str:
                return False, "Custom size must be in format 'widthxheight'"
            
            width, height = map(int, size_str.split('x'))

            if width < 512 or width > 2048 or height < 512 or height > 2048:
                return False, f"Custom size dimensions must be between 512 and 2048 pixels. Got {width}x{height}."
            
            return True, f"{width}x{height}"
        except ValueError:
            return False, "Custom size must contain valid integers in format 'widthxheight'"
    
    def generate_image(self, prompt, model, response_format="url", size="1024x1024", 
                       Custom_size="1536x1024", guidance_scale=2.5, apikey="", 
                       seed=-1, watermark=True):
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)
            
        if not self.api_key:
            error_message = "API key not found in Comflyapi.json"
            print(error_message)
            blank_image = Image.new('RGB', (1024, 1024), color='white')
            blank_tensor = pil2tensor(blank_image)
            return (blank_tensor, error_message)
            
        try:
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            final_size = size
            if size == "Custom":
                is_valid, result = self.validate_custom_size(Custom_size)
                if not is_valid:
                    error_message = result
                    print(error_message)
                    blank_image = Image.new('RGB', (1024, 1024), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, error_message)
                final_size = result
            
            payload = {
                "model": model,
                "prompt": prompt,
                "response_format": response_format,
                "size": final_size,
                "guidance_scale": guidance_scale,
                "watermark": watermark
            }
            
            if seed != -1:
                payload["seed"] = seed
            
            response = requests.post(
                f"{baseurl}/v1/images/generations",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            pbar.update_absolute(30)
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, error_message)
                
            result = response.json()
            
            pbar.update_absolute(50)
            
            if "data" not in result or not result["data"]:
                error_message = "No image data in response"
                print(error_message)
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, error_message)
            
            image_url = None
            image_data = None

            if response_format == "url":
                image_url = result["data"][0].get("url")
                if not image_url:
                    error_message = "No image URL in response"
                    print(error_message)
                    blank_image = Image.new('RGB', (1024, 1024), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, error_message)
                    
                try:
                    img_response = requests.get(image_url, timeout=self.timeout)
                    img_response.raise_for_status()
                    image_data = BytesIO(img_response.content)
                except Exception as e:
                    error_message = f"Error downloading image: {str(e)}"
                    print(error_message)
                    blank_image = Image.new('RGB', (1024, 1024), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, error_message)
            else:
                b64_data = result["data"][0].get("b64_json")
                if not b64_data:
                    error_message = "No base64 data in response"
                    print(error_message)
                    blank_image = Image.new('RGB', (1024, 1024), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, error_message)
                    
                image_data = BytesIO(base64.b64decode(b64_data))
            
            pbar.update_absolute(80)

            try:
                pil_image = Image.open(image_data)
                tensor_image = pil2tensor(pil_image)

                response_info = {
                    "prompt": prompt,
                    "model": model,
                    "size": final_size,
                    "guidance_scale": guidance_scale,
                    "seed": seed if seed != -1 else "auto",
                    "url": image_url if image_url else "base64 data"
                }
                
                pbar.update_absolute(100)
                return (tensor_image, json.dumps(response_info, indent=2))
                
            except Exception as e:
                error_message = f"Error processing image: {str(e)}"
                print(error_message)
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, error_message)
                
        except Exception as e:
            error_message = f"Error generating image: {str(e)}"
            print(error_message)
            blank_image = Image.new('RGB', (1024, 1024), color='white')
            blank_tensor = pil2tensor(blank_image)
            return (blank_tensor, error_message)


class Comfly_Doubao_Seedream_4:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "model": ("STRING", {"default": "doubao-seedream-4-0-250828"}),
                "response_format": (["url", "b64_json"], {"default": "url"}),
                "resolution": (["1K", "2K", "4K"], {"default": "1K"}),
            },
            "optional": {
                "aspect_ratio": (["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9", "9:21", "Custom"], {"default": "1:1"}),
                "width": ("INT", {"default": 1024, "min": 64, "max": 8192, "step": 1}),
                "height": ("INT", {"default": 1024, "min": 64, "max": 8192, "step": 1}),
                "apikey": ("STRING", {"default": ""}),
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "image3": ("IMAGE",),
                "image4": ("IMAGE",),
                "image5": ("IMAGE",),
                "sequential_image_generation": (["disabled", "auto"], {"default": "disabled"}),
                "max_images": ("INT", {"default": 1, "min": 1, "max": 15, "step": 1}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
                "watermark": ("BOOLEAN", {"default": True}),
                "stream": ("BOOLEAN", {"default": False}),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "response", "image_url")
    FUNCTION = "generate_image"
    CATEGORY = "Comfly-v2/Doubao"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 900
        self.size_mapping = {
            
            "1K": {
                "1:1": "1024x1024",
                "4:3": "1152x864",
                "3:4": "864x1152",
                "16:9": "1280x720",
                "9:16": "720x1280",
                "2:3": "832x1248",
                "3:2": "1248x832",
                "21:9": "1512x648",
                "9:21": "648x1512"
            },

            "2K": {
                "1:1": "2048x2048",
                "4:3": "2048x1536",
                "3:4": "1536x2048",
                "16:9": "2048x1152",
                "9:16": "1152x2048",
                "2:3": "1536x2048",
                "3:2": "2048x1536",
                "21:9": "2048x864",
                "9:21": "864x2048"
            },

            "4K": {
                "1:1": "4096x4096",
                "4:3": "4096x3072",
                "3:4": "3072x4096",
                "16:9": "4096x2304",
                "9:16": "2304x4096",
                "2:3": "3072x4096",
                "3:2": "4096x3072",
                "21:9": "4096x1728",
                "9:21": "1728x4096"
            }
        }

        self.resolution_factors = {
            "1K": 1,
            "2K": 2,
            "4K": 4
        }

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def image_to_base64(self, image_tensor):
        """Convert tensor to base64 string"""
        if image_tensor is None:
            return None
            
        pil_image = tensor2pil(image_tensor)[0]
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{image_base64}"
    
    def generate_image(self, prompt, model, response_format="url", resolution="1K", 
                  aspect_ratio="1:1", width=1024, height=1024, apikey="", 
                  image1=None, image2=None, image3=None, image4=None, image5=None, 
                  sequential_image_generation="disabled", max_images=1, seed=-1, 
                  watermark=True, stream=False):
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)
            
        if not self.api_key:
            error_message = "API key not found in Comflyapi.json"
            print(error_message)
            blank_image = Image.new('RGB', (1024, 1024), color='white')
            blank_tensor = pil2tensor(blank_image)
            return (blank_tensor, error_message, "")
            
        try:
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            if aspect_ratio == "Custom":

                scale_factor = self.resolution_factors.get(resolution, 1)
                scaled_width = int(width * scale_factor)
                scaled_height = int(height * scale_factor)
    
                final_size = f"{scaled_width}x{scaled_height}"
                print(f"Using custom dimensions with {resolution} scaling: {final_size}")
            else:
                if resolution in self.size_mapping and aspect_ratio in self.size_mapping[resolution]:
                    final_size = self.size_mapping[resolution][aspect_ratio]
                else:
                    final_size = "1024x1024"
                    print(f"Warning: Combination of {resolution} resolution and {aspect_ratio} aspect ratio not found. Using {final_size}.")
            
            payload = {
                "model": model,
                "prompt": prompt,
                "response_format": response_format,
                "size": final_size,
                "watermark": watermark,
                "stream": stream
            }

            if sequential_image_generation == "auto":
                payload["sequential_image_generation"] = sequential_image_generation
                payload["n"] = max_images
                
            if seed != -1:
                payload["seed"] = seed

            image_urls = []
            for img in [image1, image2, image3, image4, image5]:
                if img is not None:
                    batch_size = img.shape[0]
                    for i in range(batch_size):
                        single_image = img[i:i+1]
                        image_base64 = self.image_to_base64(single_image)
                        if image_base64:
                            image_urls.append(image_base64)
            
            if image_urls:
                payload["image"] = image_urls
            
            response = requests.post(
                f"{baseurl}/v1/images/generations",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            pbar.update_absolute(30)
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, error_message, "")
                
            result = response.json()
            
            pbar.update_absolute(50)
            
            if "data" not in result or not result["data"]:
                error_message = "No image data in response"
                print(error_message)
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, error_message, "")
            
            image_url = None
            image_data = None
            generated_images = []
            image_urls = []
            for item in result["data"]:
                if response_format == "url":
                    image_url = item.get("url")
                    if not image_url:
                        continue
                    
                    image_urls.append(image_url)
                    
                    try:
                        img_response = requests.get(image_url, timeout=self.timeout)
                        img_response.raise_for_status()
                        image_data = BytesIO(img_response.content)
                        
                        pil_image = Image.open(image_data)
                        tensor_image = pil2tensor(pil_image)
                        generated_images.append(tensor_image)
                    except Exception as e:
                        print(f"Error downloading image: {str(e)}")
                else:
                    b64_data = item.get("b64_json")
                    if not b64_data:
                        continue
                        
                    image_data = BytesIO(base64.b64decode(b64_data))
                    
                    pil_image = Image.open(image_data)
                    tensor_image = pil2tensor(pil_image)
                    generated_images.append(tensor_image)
            
            pbar.update_absolute(80)
            if not generated_images:
                error_message = "Failed to process any images"
                print(error_message)
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, error_message, "")
            
            combined_tensor = torch.cat(generated_images, dim=0)
                
            response_info = {
                "prompt": prompt,
                "model": model,
                "resolution": resolution,
                "size": final_size,
                "seed": seed if seed != -1 else "auto",
                "urls": image_urls if image_urls else [],
                "sequential_image_generation": sequential_image_generation,
                "aspect_ratio": aspect_ratio
            }

            if aspect_ratio == "Custom":
                response_info["original_dimensions"] = f"{width}x{height}"
                response_info["scaled_dimensions"] = final_size
            
            if sequential_image_generation == "auto":
                response_info["max_images"] = max_images
            
            response_info["images_generated"] = len(generated_images)
            
            pbar.update_absolute(100)
            first_image_url = image_urls[0] if image_urls else ""
            return (combined_tensor, json.dumps(response_info, indent=2), first_image_url)
                
        except Exception as e:
            error_message = f"Error generating image: {str(e)}"
            print(error_message)
            blank_image = Image.new('RGB', (1024, 1024), color='white')
            blank_tensor = pil2tensor(blank_image)
            return (blank_tensor, error_message, "")


class Comfly_Doubao_Seededit:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "prompt": ("STRING", {"multiline": True}),
                "model": ("STRING", {"default": "doubao-seededit-3-0-i2i-250628"}),
                "response_format": (["url", "b64_json"], {"default": "url"}),
                "size": ("STRING", {"default": "adaptive"}),
                "guidance_scale": ("FLOAT", {"default": 5.5, "min": 1.0, "max": 10.0, "step": 0.1}),
            },
            "optional": {
                "apikey": ("STRING", {"default": ""}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
                "watermark": ("BOOLEAN", {"default": True})
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "response")
    FUNCTION = "edit_image"
    CATEGORY = "Comfly-v2/Doubao"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def edit_image(self, image, prompt, model, response_format="url", size="adaptive", 
                guidance_scale=5.5, apikey="", seed=-1, watermark=True):
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)
            
        if not self.api_key:
            error_message = "API key not found in Comflyapi.json"
            print(error_message)
            return (image, error_message)
            
        try:
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            pil_image = tensor2pil(image)[0]

            buffered = BytesIO()
            pil_image.save(buffered, format="PNG")
            img_base64 = f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"
            
            payload = {
                "model": model,
                "prompt": prompt,
                "image": img_base64,
                "response_format": response_format,
                "size": size,
                "guidance_scale": guidance_scale,
                "watermark": watermark
            }
            
            if seed != -1:
                payload["seed"] = seed
            
            response = requests.post(
                f"{baseurl}/v1/images/generations",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            pbar.update_absolute(30)
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                return (image, error_message)
                
            result = response.json()
            
            pbar.update_absolute(50)
            
            if "data" not in result or not result["data"]:
                error_message = "No image data in response"
                print(error_message)
                return (image, error_message)
            
            image_url = None
            image_data = None

            if response_format == "url":
                image_url = result["data"][0].get("url")
                if not image_url:
                    error_message = "No image URL in response"
                    print(error_message)
                    return (image, error_message)
                    
                try:
                    img_response = requests.get(image_url, timeout=self.timeout)
                    img_response.raise_for_status()
                    image_data = BytesIO(img_response.content)
                except Exception as e:
                    error_message = f"Error downloading image: {str(e)}"
                    print(error_message)
                    return (image, error_message)
            else:
                b64_data = result["data"][0].get("b64_json")
                if not b64_data:
                    error_message = "No base64 data in response"
                    print(error_message)
                    return (image, error_message)
                    
                image_data = BytesIO(base64.b64decode(b64_data))
            
            pbar.update_absolute(80)

            try:
                edited_pil_image = Image.open(image_data)
                edited_tensor = pil2tensor(edited_pil_image)

                response_info = {
                    "prompt": prompt,
                    "model": model,
                    "size": size,
                    "guidance_scale": guidance_scale,
                    "seed": seed if seed != -1 else "auto",
                    "url": image_url if image_url else "base64 data"
                }
                
                pbar.update_absolute(100)
                return (edited_tensor, json.dumps(response_info, indent=2))
                
            except Exception as e:
                error_message = f"Error processing edited image: {str(e)}"
                print(error_message)
                return (image, error_message)
                
        except Exception as e:
            error_message = f"Error editing image: {str(e)}"
            print(error_message)
            return (image, error_message)


class ComflyJimengApi:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "scale": ("FLOAT", {"default": 2.5, "min": 1.0, "max": 10.0, "step": 0.1}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647, "step": 1}),
                "width": ("INT", {"default": 1328, "min": 512, "max": 2048, "step": 8}),
                "height": ("INT", {"default": 1328, "min": 512, "max": 2048, "step": 8}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "use_pre_llm": ("BOOLEAN", {"default": False}),
                "add_logo": ("BOOLEAN", {"default": False}),
                "logo_position": (["右下角", "左下角", "左上角", "右上角"], {"default": "右下角"}),
                "logo_language": (["中文", "英文"], {"default": "中文"}),
                "logo_text": ("STRING", {"default": "", "multiline": False}),
                "logo_opacity": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.1}),
                "image": ("IMAGE",),  
                "image_url": ("STRING", {"default": "", "multiline": False}),  
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("generated_image", "response", "image_url")
    FUNCTION = "generate_image"
    CATEGORY = "Comfly-v2/Doubao"
    
    def __init__(self):
        super().__init__()
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
    def get_logo_position_value(self, position_str):
        position_map = {
            "右下角": 0,
            "左下角": 1,
            "左上角": 2,
            "右上角": 3
        }
        return position_map.get(position_str, 0)
        
    def get_logo_language_value(self, language_str):
        language_map = {
            "中文": 0,
            "英文": 1
        }
        return language_map.get(language_str, 0)
    
    def upload_image(self, image_tensor):
        """Upload image to the file endpoint and return the URL"""
        try:
            pil_image = tensor2pil(image_tensor)[0]

            buffered = BytesIO()
            pil_image.save(buffered, format="PNG")
            file_content = buffered.getvalue()

            files = {'file': ('image.png', file_content, 'image/png')}

            response = requests.post(
                f"{baseurl}/v1/files",
                headers={"Authorization": f"Bearer {self.api_key}"},
                files=files,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            result = response.json()
            
            if 'url' in result:
                return result['url']
            else:
                print(f"Unexpected response from file upload API: {result}")
                return None
                
        except Exception as e:
            print(f"Error uploading image: {str(e)}")
            return None
    
    def generate_image(self, prompt, scale=2.5, seed=-1, width=1328, height=1328, use_pre_llm=False, 
                      add_logo=False, logo_position="右下角", logo_language="中文", 
                      logo_text="", logo_opacity=0.3, api_key="", image=None, image_url=""):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        try:
            if not self.api_key:
                error_message = "API key not found in Comflyapi.json"
                print(error_message)

                blank_image = Image.new('RGB', (width, height), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, error_message, "")

            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            uploaded_image_url = None
            if image is not None:
                pbar.update_absolute(20)
                print("Uploading image...")
                uploaded_image_url = self.upload_image(image)
                if uploaded_image_url:
                    if not prompt.strip():
                        prompt = "Generate a 3D style version of this image"
                else:
                    print("Image upload failed, proceeding without image")

            final_image_url = uploaded_image_url if uploaded_image_url else image_url

            model_name = "seedream-3.0"  
            
            position_value = self.get_logo_position_value(logo_position)
            language_value = self.get_logo_language_value(logo_language)
            
            logo_info = {
                "add_logo": add_logo,
                "position": position_value,
                "language": language_value,
                "opacity": logo_opacity
            }
 
            if logo_text:
                logo_info["logo_text_content"] = logo_text

            payload = {
                "req_key": "high_aes_general_v30l_zt2i",
                "prompt": prompt,
                "scale": scale,
                "seed": seed,
                "width": width,
                "height": height,
                "use_pre_llm": use_pre_llm,
                "return_url": True,
                "logo_info": logo_info
            }

            if final_image_url:
                combined_prompt = f"{final_image_url} {prompt}"
                
                messages = [
                    {
                        "role": "user",
                        "content": combined_prompt
                    }
                ]
                
                chat_payload = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": 0.5,
                    "top_p": 1,
                    "presence_penalty": 0,
                    "max_tokens": 8192,
                    "stream": True
                }

                api_url = f"{baseurl}/v1/chat/completions"
                headers = self.get_headers()

                pbar.update_absolute(30)

                response = requests.post(
                    api_url,
                    headers=headers,
                    json=chat_payload,
                    timeout=self.timeout,
                    stream=True
                )

                full_response = ""
                for line in response.iter_lines():
                    if line:
                        line_text = line.decode('utf-8')
                        if line_text.startswith('data: '):
                            data = line_text[6:]
                            if data == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data)
                                if 'choices' in chunk and chunk['choices']:
                                    delta = chunk['choices'][0].get('delta', {})
                                    if 'content' in delta:
                                        content = delta['content']
                                        full_response += content
                            except json.JSONDecodeError:
                                continue

                image_url = ""
                image_urls = self.extract_image_urls(full_response)
                if image_urls:
                    image_url = image_urls[0]
                    print(f"Found image URL in response: {image_url}")

                if image_url:
                    response_info = f"**Image Generation with {model_name}**\n\n"
                    response_info += f"Prompt: {prompt}\n"
                    response_info += f"Generated image URL: {image_url}\n\n"
                    response_info += f"Model response: {full_response}"

                    try:
                        img_response = requests.get(image_url, timeout=self.timeout)
                        img_response.raise_for_status()
                        generated_image = Image.open(BytesIO(img_response.content))
                        generated_tensor = pil2tensor(generated_image)
                        pbar.update_absolute(100)
                        return (generated_tensor, response_info, image_url)
                    except Exception as e:
                        error_message = f"Error downloading result image: {str(e)}"
                        print(error_message)
                        if image is not None:
                            return (image, response_info + f"\n\nError: {error_message}", image_url)
                        else:
                            blank_image = Image.new('RGB', (width, height), color='white')
                            blank_tensor = pil2tensor(blank_image)
                            return (blank_tensor, response_info + f"\n\nError: {error_message}", image_url)
                else:
                    error_message = "No image URL found in response"
                    print(error_message)
                    response_info = f"**Error: {error_message}**\n\nFull response: {full_response}"
                    if image is not None:
                        return (image, response_info, "")
                    else:
                        blank_image = Image.new('RGB', (width, height), color='white')
                        blank_tensor = pil2tensor(blank_image)
                        return (blank_tensor, response_info, "")
            
            else:
                api_url = f"{baseurl}/volcv/v1?Action=CVProcess&Version=2022-08-31"
                
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                response_info = f"**Jimeng Image Generation Request**\n\n"
                response_info += f"Prompt: {prompt}\n"
                response_info += f"Scale: {scale}\n"
                response_info += f"Seed: {seed}\n"
                response_info += f"Dimensions: {width}x{height}\n"
                response_info += f"Time: {timestamp}\n\n"
                
                try:
                    response = requests.post(
                        api_url,
                        headers=self.get_headers(),
                        json=payload,
                        timeout=self.timeout
                    )
                except requests.exceptions.Timeout:
                    error_message = f"API request timed out after {self.timeout} seconds"
                    print(error_message)
                    response_info += f"Error: {error_message}"
                    blank_image = Image.new('RGB', (width, height), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, response_info, "")

                if response.status_code != 200:
                    error_message = f"API Error: Status {response.status_code}\nResponse: {response.text}"
                    print(error_message)
                    response_info += f"Error: {error_message}"
                    blank_image = Image.new('RGB', (width, height), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, response_info, "")
                    
                result = response.json()
                
                pbar.update_absolute(70)

                if result.get("code") != 10000:
                    error_message = f"API Error: {result.get('message', 'Unknown error')}\nDetails: {json.dumps(result, indent=2)}"
                    print(error_message)
                    response_info += f"Error: {error_message}"
                    blank_image = Image.new('RGB', (width, height), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, response_info, "")

                image_url = ""
                if "image_urls" in result["data"] and result["data"]["image_urls"]:
                    image_url = result["data"]["image_urls"][0]
                    response_info += f"Success!\n\nImage URL: {image_url}\n\n"
                    
                    if "vlm_result" in result["data"] and result["data"]["vlm_result"]:
                        response_info += f"VLM Description: {result['data']['vlm_result']}\n"
                else:
                    error_message = "No image URL found in response"
                    print(error_message)
                    response_info += f"Error: {error_message}\nFull response: {json.dumps(result, indent=2)}"
                    blank_image = Image.new('RGB', (width, height), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, response_info, "")
                
                print(f"Found image URL: {image_url}")

                try:
                    img_response = requests.get(image_url, timeout=self.timeout)
                    img_response.raise_for_status()
                except requests.exceptions.Timeout:
                    error_message = f"Timeout while downloading result image after {self.timeout} seconds"
                    print(error_message)
                    response_info += f"Error: {error_message}"
                    blank_image = Image.new('RGB', (width, height), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, response_info, image_url)  
                except Exception as e:
                    error_message = f"Error downloading result image: {str(e)}"
                    print(error_message)
                    response_info += f"Error: {error_message}"
                    blank_image = Image.new('RGB', (width, height), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, response_info, image_url)  
                    
                generated_image = Image.open(BytesIO(img_response.content))
                
                generated_tensor = pil2tensor(generated_image)
                
                pbar.update_absolute(100)
            
                if "request_id" in result:
                    response_info += f"Request ID: {result['request_id']}\n"
                
                if "time_elapsed" in result:
                    response_info += f"Processing Time: {result['time_elapsed']}\n"
                
                return (generated_tensor, response_info, image_url)
                
        except Exception as e:
            error_message = f"Error in image generation: {str(e)}"
            print(error_message)
            blank_image = Image.new('RGB', (width, height), color='white')
            blank_tensor = pil2tensor(blank_image)
            return (blank_tensor, error_message, "")
            
    def extract_image_urls(self, response_text):
        """Extract image URLs from markdown format in response"""
        image_pattern = r'!\[.*?\]\((.*?)\)'
        matches = re.findall(image_pattern, response_text)

        if not matches:
            url_pattern = r'https?://\S+\.(?:jpg|jpeg|png|gif|webp)'
            matches = re.findall(url_pattern, response_text)
            
        return matches if matches else []


class ComflyJimengVideoApi:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "duration": ([5, 10], {"default": 5}),
                "aspect_ratio": (["1:1", "21:9", "16:9", "9:16", "4:3", "3:4"], {"default": "16:9"}),
                "cfg_scale": ("FLOAT", {"default": 0.5, "min": 0.1, "max": 1.0, "step": 0.1}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "image": ("IMAGE",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647})
            }
        }
    
    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "task_id", "response", "video_url")
    FUNCTION = "generate_video"
    CATEGORY = "Comfly-v2/Doubao"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def upload_image(self, image_tensor):
        """Upload image to the file endpoint and return the URL"""
        try:
            pil_image = tensor2pil(image_tensor)[0]

            buffered = BytesIO()
            pil_image.save(buffered, format="PNG")
            file_content = buffered.getvalue()

            files = {'file': ('image.png', file_content, 'image/png')}

            response = requests.post(
                f"{baseurl}/v1/files",
                headers={"Authorization": f"Bearer {self.api_key}"},
                files=files,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            result = response.json()
            
            if 'url' in result:
                return result['url']
            else:
                print(f"Unexpected response from file upload API: {result}")
                return None
                
        except Exception as e:
            print(f"Error uploading image: {str(e)}")
            return None
    
    def generate_video(self, prompt, duration, aspect_ratio, cfg_scale, api_key="", image=None, seed=0):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        if not self.api_key:
            error_response = {"code": "error", "message": "API key not found in Comflyapi.json"}
            return ("", "", json.dumps(error_response), "")
            
        try:
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            payload = {
                "prompt": prompt,
                "duration": int(duration),
                "aspect_ratio": aspect_ratio,
                "cfg_scale": cfg_scale
            }

            if seed > 0:
                payload["seed"] = seed

            image_url = None
            if image is not None:
                pbar.update_absolute(20)
                image_url = self.upload_image(image)
                if image_url:
                    payload["image_url"] = image_url
                else:
                    error_message = "Failed to upload image. Please check your image and try again."
                    print(error_message)
                    return ("", "", json.dumps({"code": "error", "message": error_message}), "")

            pbar.update_absolute(30)
            response = requests.post(
                f"{baseurl}/jimeng/submit/videos",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                error_message = f"API error: {response.status_code} - {response.text}"
                print(error_message)
                return ("", "", json.dumps({"code": "error", "message": error_message}), "")
                
            result = response.json()
            
            if result.get("code") != "success":
                error_message = f"API returned error: {result.get('message', 'Unknown error')}"
                print(error_message)
                return ("", "", json.dumps({"code": "error", "message": error_message}), "")
                
            task_id = result.get("data")
            if not task_id:
                error_message = "No task ID returned from API"
                print(error_message)
                return ("", "", json.dumps({"code": "error", "message": error_message}), "")
            
            pbar.update_absolute(40)
            video_url = None
            attempts = 0
            max_attempts = 18  
            start_time = time.time()
            max_wait_time = 300 
        
            while attempts < max_attempts:
                current_time = time.time()
                elapsed_time = current_time - start_time

                if elapsed_time > max_wait_time:
                    error_message = f"Video generation timeout after {elapsed_time:.1f} seconds (max: {max_wait_time}s)"
                    print(error_message)
                    return ("", task_id, json.dumps({"code": "error", "message": error_message}), "")
                
                time.sleep(5)  
                attempts += 1
                
                try:
                    status_response = requests.get(
                        f"{baseurl}/jimeng/fetch/{task_id}",
                        headers=self.get_headers(),
                        timeout=30
                    )
                    
                    if status_response.status_code != 200:
                        continue
                        
                    status_result = status_response.json()

                    if status_result.get("code") != "success":
                        continue

                    data = status_result.get("data", {})
                    progress = data.get("progress", "0%")
                    status = data.get("status", "")

                    try:
                        if progress.endswith('%'):
                            progress_num = int(progress.rstrip('%'))
                            pbar_value = min(90, 40 + progress_num * 50 / 100)
                            pbar.update_absolute(pbar_value)
                    except (ValueError, AttributeError):
                        progress_value = min(80, 40 + (attempts * 40 // max_attempts))
                        pbar.update_absolute(progress_value)

                    if status == "SUCCESS":
                        video_url = None

                        if "video" in data:
                            video_url = data["video"]

                        elif "data" in data and isinstance(data["data"], dict):
                            nested_data = data["data"]
                            if "video" in nested_data:
                                video_url = nested_data["video"]
                            elif "videos" in nested_data and isinstance(nested_data["videos"], list) and len(nested_data["videos"]) > 0:
                                if "url" in nested_data["videos"][0]:
                                    video_url = nested_data["videos"][0]["url"]

                        elif "task_result" in data:
                            task_result = data["task_result"]
                            if "videos" in task_result and isinstance(task_result["videos"], list) and len(task_result["videos"]) > 0:
                                if "url" in task_result["videos"][0]:
                                    video_url = task_result["videos"][0]["url"]
                        
                        if video_url:
                            break
                        else:
                            continue

                    elif status == "FAILED":
                        fail_reason = data.get("fail_reason", "Unknown error")
                        error_message = f"Video generation failed: {fail_reason}"
                        print(error_message)
                        return ("", task_id, json.dumps({"code": "error", "message": error_message}), "")
                    
                    elif status in ["PENDING", "PROCESSING", "RUNNING"]:
                        continue
                    else:
                        continue
                    
                except requests.exceptions.Timeout:
                    continue
                except Exception as e:
                    continue
            
            if not video_url:
                error_message = f"Video generation timeout or failed to retrieve video URL after {attempts} attempts, elapsed time: {elapsed_time:.1f}s"
                print(error_message)
                return ("", task_id, json.dumps({"code": "error", "message": error_message}), "")

            if video_url:
                pbar.update_absolute(95)
                print(f"Video generation completed, URL: {video_url}")            
                
                video_adapter = ComflyVideoAdapter(video_url)
                return (video_adapter, task_id, json.dumps({"code": "success", "url": video_url}), video_url)
            
        except Exception as e:
            error_message = f"Error generating video: {str(e)}"
            print(error_message)
            import traceback
            traceback.print_exc()
            return ("", "", json.dumps({"code": "error", "message": error_message}), "")



class ComflySeededit:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "prompt": ("STRING", {"multiline": True}),
                "scale": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647, "step": 1}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "add_logo": ("BOOLEAN", {"default": False}),
                "logo_position": (["右下角", "左下角", "左上角", "右上角"], {"default": "右下角"}),
                "logo_language": (["中文", "英文"], {"default": "中文"}),
                "logo_text": ("STRING", {"default": "", "multiline": False}),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("edited_image", "response", "image_url")
    FUNCTION = "edit_image"
    CATEGORY = "Comfly-v2/Doubao"
    
    def __init__(self):
        super().__init__()
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
    def get_logo_position_value(self, position_str):
        position_map = {
            "右下角": 0,
            "左下角": 1,
            "左上角": 2,
            "右上角": 3
        }
        return position_map.get(position_str, 0)
        
    def get_logo_language_value(self, language_str):
        language_map = {
            "中文": 0,
            "英文": 1
        }
        return language_map.get(language_str, 0)
    
    def edit_image(self, image, prompt, scale=0.5, seed=-1, add_logo=False, logo_position="右下角", 
                   logo_language="中文", logo_text="", api_key=""):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        try:
            if not self.api_key:
                error_message = "API key not found in Comflyapi.json"
                print(error_message)
                return (image, error_message, "")
                
            # Convert tensor to PIL image
            pil_image = tensor2pil(image)[0]
            
            # Convert image to base64
            buffered = BytesIO()
            pil_image.save(buffered, format="JPEG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            # Initialize progress bar
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            
            position_value = self.get_logo_position_value(logo_position)
            language_value = self.get_logo_language_value(logo_language)
            
            logo_info = {
                "add_logo": add_logo,
                "position": position_value,
                "language": language_value
            }
 
            if logo_text:
                logo_info["logo_text_content"] = logo_text
            
            # Prepare the API request
            payload = {
                "req_key": "byteedit_v2.0",
                "binary_data_base64": [img_base64],
                "prompt": prompt,
                "scale": scale,
                "seed": seed,
                "return_url": True,
                "logo_info": logo_info
            }
            
            # Call the API
            api_url = f"{baseurl}/volcv/v1?Action=CVProcess&Version=2022-08-31"
            
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            response_info = f"**SeedEdit Request**\n\n"
            response_info += f"Prompt: {prompt}\n"
            response_info += f"Scale: {scale}\n"
            response_info += f"Seed: {seed}\n"
            response_info += f"Time: {timestamp}\n\n"
            
            try:
                response = requests.post(
                    api_url,
                    headers=self.get_headers(),
                    json=payload,
                    timeout=self.timeout
                )
            except requests.exceptions.Timeout:
                error_message = f"API request timed out after {self.timeout} seconds"
                print(error_message)
                response_info += f"Error: {error_message}"
                return (image, response_info, "")
            
            # Check for status code
            if response.status_code != 200:
                error_message = f"API Error: Status {response.status_code}\nResponse: {response.text}"
                print(error_message)
                response_info += f"Error: {error_message}"
                return (image, response_info, "")
                
            result = response.json()
            
            pbar.update_absolute(70)
            
            # Check for API errors
            if result.get("code") != 10000:
                error_message = f"API Error: {result.get('message', 'Unknown error')}\nDetails: {json.dumps(result, indent=2)}"
                print(error_message)
                response_info += f"Error: {error_message}"
                return (image, response_info, "")
            
            # Get the result image URL
            image_url = ""
            if "image_urls" in result["data"] and result["data"]["image_urls"]:
                image_url = result["data"]["image_urls"][0]
                response_info += f"Success!\n\nImage URL: {image_url}\n\n"
                
                if "vlm_result" in result["data"] and result["data"]["vlm_result"]:
                    response_info += f"VLM Description: {result['data']['vlm_result']}\n"
            else:
                error_message = "No image URL found in response"
                print(error_message)
                response_info += f"Error: {error_message}\nFull response: {json.dumps(result, indent=2)}"
                return (image, response_info, "")
            
            print(f"Found image URL: {image_url}")
            
            # Download the image
            try:
                img_response = requests.get(image_url, timeout=self.timeout)
                img_response.raise_for_status()
            except requests.exceptions.Timeout:
                error_message = f"Timeout while downloading result image after {self.timeout} seconds"
                print(error_message)
                response_info += f"Error: {error_message}"
                return (image, response_info, image_url)  # Return the URL even though download failed
            except Exception as e:
                error_message = f"Error downloading result image: {str(e)}"
                print(error_message)
                response_info += f"Error: {error_message}"
                return (image, response_info, image_url)  # Return the URL even though download failed
                
            edited_image = Image.open(BytesIO(img_response.content))
            
            # Convert back to tensor
            edited_tensor = pil2tensor(edited_image)
            
            pbar.update_absolute(100)
        
            if "request_id" in result:
                response_info += f"Request ID: {result['request_id']}\n"
            
            if "time_elapsed" in result:
                response_info += f"Processing Time: {result['time_elapsed']}\n"
            
            return (edited_tensor, response_info, image_url)
            
        except Exception as e:
            error_message = f"Error in image editing: {str(e)}"
            print(error_message)
            # Return original image on error with error message
            return (image, error_message, "")



############################# Chatgpt ###########################

# reference: OpenAIGPTImage1 node from comfyui node
def downscale_input(image):
    samples = image.movedim(-1,1)

    total = int(1536 * 1024)
    scale_by = math.sqrt(total / (samples.shape[3] * samples.shape[2]))
    if scale_by >= 1:
        return image
    width = round(samples.shape[3] * scale_by)
    height = round(samples.shape[2] * scale_by)

    s = common_upscale(samples, width, height, "lanczos", "disabled")
    s = s.movedim(1,-1)
    return s


class Comfly_gpt_image_1_edit:

    _last_edited_image = None
    _conversation_history = []
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "prompt": ("STRING", {"multiline": True}),
            },
            "optional": {
                "mask": ("MASK",),
                "api_key": ("STRING", {"default": ""}),
                "model": ("STRING", {"default": "gpt-image-1"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 10}),
                "quality": (["auto", "high", "medium", "low"], {"default": "auto"}),
                "size": (["auto", "1024x1024", "1536x1024", "1024x1536"], {"default": "auto"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "clear_chats": ("BOOLEAN", {"default": True}),
                "background": (["auto", "transparent", "opaque"], {"default": "auto"}),
                "output_compression": ("INT", {"default": 100, "min": 0, "max": 100}),
                "output_format": (["png", "jpeg", "webp"], {"default": "png"}),
                "max_retries": ("INT", {"default": 5, "min": 1, "max": 10}),
                "initial_timeout": ("INT", {"default": 900, "min": 60, "max": 1200}),
                "input_fidelity": (["low", "high"], {"default": "low"}),
                "partial_images": ([0, 1, 2, 3], {"default": 0}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("edited_image", "response", "chats")
    FUNCTION = "edit_image"
    CATEGORY = "Comfly-v2/Openai"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 900
        self.session = requests.Session()
        retry_strategy = requests.packages.urllib3.util.retry.Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def format_conversation_history(self):
        """Format the conversation history for display"""
        if not Comfly_gpt_image_1_edit._conversation_history:
            return ""
        formatted_history = ""
        for entry in Comfly_gpt_image_1_edit._conversation_history:
            formatted_history += f"**User**: {entry['user']}\n\n"
            formatted_history += f"**AI**: {entry['ai']}\n\n"
            formatted_history += "---\n\n"
        return formatted_history.strip()
    
    def make_request_with_retry(self, url, data=None, files=None, max_retries=5, initial_timeout=300):
        """Make a request with automatic retries and exponential backoff"""
        for attempt in range(1, max_retries + 1):
            current_timeout = min(initial_timeout * (1.5 ** (attempt - 1)), 1200)  
            
            try:
                if files:
                    response = self.session.post(
                        url,
                        headers=self.get_headers(),
                        data=data,
                        files=files,
                        timeout=current_timeout
                    )
                else:
                    response = self.session.post(
                        url,
                        headers=self.get_headers(),
                        json=data,
                        timeout=current_timeout
                    )
                
                response.raise_for_status()
                return response
            
            except requests.exceptions.Timeout as e:
                if attempt == max_retries:
                    raise TimeoutError(f"Request timed out after {max_retries} attempts. Last timeout: {current_timeout}s")
                wait_time = min(2 ** (attempt - 1), 60)  
                time.sleep(wait_time)
            
            except requests.exceptions.ConnectionError as e:
                if attempt == max_retries:
                    raise ConnectionError(f"Connection error after {max_retries} attempts: {str(e)}")
                wait_time = min(2 ** (attempt - 1), 60)
                time.sleep(wait_time)
            
            except requests.exceptions.HTTPError as e:
                if e.response.status_code in (400, 401, 403):
                    print(f"Client error: {str(e)}")
                    raise
                if attempt == max_retries:
                    raise
                wait_time = min(2 ** (attempt - 1), 60)
                time.sleep(wait_time)
            
            except Exception as e:
                if attempt == max_retries:
                    raise
                wait_time = min(2 ** (attempt - 1), 60)
                time.sleep(wait_time)
    
    def edit_image(self, image, prompt, model="gpt-image-1", n=1, quality="auto", 
              seed=0, mask=None, api_key="", size="auto", clear_chats=True,
              background="auto", output_compression=100, output_format="png",
              max_retries=5, initial_timeout=300, input_fidelity="low", partial_images=0):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
 
        original_image = image
        original_batch_size = image.shape[0]
        use_saved_image = False

        if not clear_chats and Comfly_gpt_image_1_edit._last_edited_image is not None:
            if original_batch_size > 1:
                last_batch_size = Comfly_gpt_image_1_edit._last_edited_image.shape[0]
                last_image_first = Comfly_gpt_image_1_edit._last_edited_image[0:1]
                if last_image_first.shape[1:] == original_image.shape[1:]:
                    image = torch.cat([last_image_first, original_image[1:]], dim=0)
                    use_saved_image = True
            else:
                image = Comfly_gpt_image_1_edit._last_edited_image
                use_saved_image = True

        if clear_chats:
            Comfly_gpt_image_1_edit._conversation_history = []

            
        try:
            if not self.api_key:
                error_message = "API key not found in Comflyapi.json"
                print(error_message)
                return (original_image, error_message, self.format_conversation_history())
          
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            
            files = {}
 
            if image is not None:
                batch_size = image.shape[0]
                for i in range(batch_size):
                    single_image = image[i:i+1]
                    scaled_image = downscale_input(single_image).squeeze()
                    
                    image_np = (scaled_image.numpy() * 255).astype(np.uint8)
                    img = Image.fromarray(image_np)
                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='PNG')
                    img_byte_arr.seek(0)
                    
                    if batch_size == 1:
                        files['image'] = ('image.png', img_byte_arr, 'image/png')
                    else:
                        if 'image[]' not in files:
                            files['image[]'] = []
                        files['image[]'].append(('image_{}.png'.format(i), img_byte_arr, 'image/png'))
            
            if mask is not None:
                if image.shape[0] != 1:
                    raise Exception("Cannot use a mask with multiple images")
                if image is None:
                    raise Exception("Cannot use a mask without an input image")
                if mask.shape[1:] != image.shape[1:-1]:
                    raise Exception("Mask and Image must be the same size")
                
                batch, height, width = mask.shape
                rgba_mask = torch.zeros(height, width, 4, device="cpu")
                rgba_mask[:,:,3] = (1-mask.squeeze().cpu())
                scaled_mask = downscale_input(rgba_mask.unsqueeze(0)).squeeze()
                mask_np = (scaled_mask.numpy() * 255).astype(np.uint8)
                mask_img = Image.fromarray(mask_np)
                mask_byte_arr = io.BytesIO()
                mask_img.save(mask_byte_arr, format='PNG')
                mask_byte_arr.seek(0)
                files['mask'] = ('mask.png', mask_byte_arr, 'image/png')

            data = {
                'prompt': prompt,
                'model': model,
                'n': str(n),
                'quality': quality
            }
            
            if size != "auto":
                data['size'] = size
                
            if background != "auto":
                data['background'] = background
                
            if output_compression != 100:
                data['output_compression'] = str(output_compression)
                
            if output_format != "png":
                data['output_format'] = output_format

            if input_fidelity != "low":
                data['input_fidelity'] = input_fidelity
                
            if partial_images > 0:
                data['partial_images'] = str(partial_images)

            pbar.update_absolute(30)

            try:
                if 'image[]' in files:
                    image_files = []
                    for file_tuple in files['image[]']:
                        image_files.append(('image', file_tuple))

                    if 'mask' in files:
                        image_files.append(('mask', files['mask']))

                    response = self.make_request_with_retry(
                        f"{baseurl}/v1/images/edits",
                        data=data,
                        files=image_files,
                        max_retries=max_retries,
                        initial_timeout=initial_timeout
                    )
                else:
                    request_files = []
                    if 'image' in files:
                        request_files.append(('image', files['image']))
                    if 'mask' in files:
                        request_files.append(('mask', files['mask']))

                    response = self.make_request_with_retry(
                        f"{baseurl}/v1/images/edits",
                        data=data,
                        files=request_files,
                        max_retries=max_retries,
                        initial_timeout=initial_timeout
                    )

            except TimeoutError as e:
                error_message = f"API timeout error: {str(e)}"
                print(error_message)
                return (original_image, error_message, self.format_conversation_history())
            except Exception as e:
                error_message = f"API request error: {str(e)}"
                print(error_message)
                return (original_image, error_message, self.format_conversation_history())

            pbar.update_absolute(50)
            result = response.json()
            
            if "data" not in result or not result["data"]:
                error_message = "No image data in response"
                print(error_message)
                return (original_image, error_message, self.format_conversation_history())

            edited_images = []
            image_urls = []

            for item in result["data"]:
                if "b64_json" in item:
                    b64_data = item["b64_json"]
                    if b64_data.startswith("data:image/png;base64,"):
                        b64_data = b64_data[len("data:image/png;base64,"):]    
                    image_data = base64.b64decode(b64_data)
                    edited_image = Image.open(BytesIO(image_data))
                    edited_tensor = pil2tensor(edited_image)
                    edited_images.append(edited_tensor)
                elif "url" in item:
                    image_urls.append(item["url"])
                    try:
                        for download_attempt in range(1, max_retries + 1):
                            try:
                                img_response = requests.get(
                                    item["url"], 
                                    timeout=min(initial_timeout * (1.5 ** (download_attempt - 1)), 900)
                                )
                                img_response.raise_for_status()
                                
                                edited_image = Image.open(BytesIO(img_response.content))
                                edited_tensor = pil2tensor(edited_image)
                                edited_images.append(edited_tensor)
                                break
                            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                                if download_attempt == max_retries:
                                    print(f"Failed to download image after {max_retries} attempts: {str(e)}")
                                    continue
                                wait_time = min(2 ** (download_attempt - 1), 60)
                                print(f"Image download error (attempt {download_attempt}/{max_retries}). Retrying in {wait_time} seconds...")
                                time.sleep(wait_time)
                            except Exception as e:
                                print(f"Error downloading image from URL: {str(e)}")
                                break
                    except Exception as e:
                        print(f"Error processing image URL: {str(e)}")

            pbar.update_absolute(90)

            if edited_images:
                combined_tensor = torch.cat(edited_images, dim=0)
                response_info = f"Successfully edited {len(edited_images)} image(s)\n"
                response_info += f"Prompt: {prompt}\n"
                response_info += f"Model: {model}\n"
                response_info += f"Quality: {quality}\n"
                
                if use_saved_image:
                    response_info += "[Using previous edited image as input]\n"
                    
                if size != "auto":
                    response_info += f"Size: {size}\n"
                    
                if background != "auto":
                    response_info += f"Background: {background}\n"
                    
                if output_compression != 100:
                    response_info += f"Output Compression: {output_compression}%\n"
                    
                if output_format != "png":
                    response_info += f"Output Format: {output_format}\n"

                if input_fidelity != "low":
                    response_info += f"Input Fidelity: {input_fidelity}\n"
                
                if partial_images > 0:
                    response_info += f"Partial Images: {partial_images}\n"

                Comfly_gpt_image_1_edit._conversation_history.append({
                    "user": f"Edit image with prompt: {prompt}",
                    "ai": f"Generated edited image with {model}"
                })
 
                Comfly_gpt_image_1_edit._last_edited_image = combined_tensor
                
                pbar.update_absolute(100)
                return (combined_tensor, response_info, self.format_conversation_history())
            else:
                error_message = "No edited images in response"
                print(error_message)
                return (original_image, error_message, self.format_conversation_history())
            
        except Exception as e:
            error_message = f"Error in image editing: {str(e)}"
            import traceback
            print(traceback.format_exc())  
            print(error_message)
            return (original_image, error_message, self.format_conversation_history())
        

class Comfly_gpt_image_1:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "model": ("STRING", {"default": "gpt-image-1"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 10}),
                "quality": (["auto", "high", "medium", "low"], {"default": "auto"}),
                "size": (["auto", "1024x1024", "1536x1024", "1024x1536"], {"default": "auto"}),
                "background": (["auto", "transparent", "opaque"], {"default": "auto"}),
                "output_format": (["png", "jpeg", "webp"], {"default": "png"}),
                "moderation": (["auto", "low"], {"default": "auto"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("generated_image", "response")
    FUNCTION = "generate_image"
    CATEGORY = "Comfly-v2/Openai"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def generate_image(self, prompt, model="gpt-image-1", n=1, quality="auto", 
                size="auto", background="auto", output_format="png", 
                moderation="auto", seed=0, api_key=""):
        
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        try:
            if not self.api_key:
                error_message = "API key not found in Comflyapi.json"
                print(error_message)
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, error_message)
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            payload = {
                "prompt": prompt,
                "model": model,
                "n": n,
                "quality": quality,
                "background": background,
                "output_format": output_format,
                "moderation": moderation,
            }

            if size != "auto":
                payload["size"] = size
            
            response = requests.post(
                f"{baseurl}/v1/images/generations",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            pbar.update_absolute(50)
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, error_message)

            result = response.json()

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            response_info = f"**GPT-image-1 Generation ({timestamp})**\n\n"
            response_info += f"Prompt: {prompt}\n"
            response_info += f"Model: {model}\n"
            response_info += f"Quality: {quality}\n"
            if size != "auto":
                response_info += f"Size: {size}\n"
            response_info += f"Background: {background}\n"
            response_info += f"Seed: {seed} (Note: Seed not used by API)\n\n"

            generated_images = []
            image_urls = []
            
            if "data" in result and result["data"]:
                for i, item in enumerate(result["data"]):
                    pbar.update_absolute(50 + (i+1) * 50 // len(result["data"]))
                    
                    if "b64_json" in item:
                        b64_data = item["b64_json"]
                        if b64_data.startswith("data:image/png;base64,"):
                            b64_data = b64_data[len("data:image/png;base64,"):]    
                        image_data = base64.b64decode(b64_data)
                        generated_image = Image.open(BytesIO(image_data))
                        generated_tensor = pil2tensor(generated_image)
                        generated_images.append(generated_tensor)
                    elif "url" in item:
                        image_urls.append(item["url"])
                        try:
                            img_response = requests.get(item["url"])
                            if img_response.status_code == 200:
                                generated_image = Image.open(BytesIO(img_response.content))
                                generated_tensor = pil2tensor(generated_image)
                                generated_images.append(generated_tensor)
                        except Exception as e:
                            print(f"Error downloading image from URL: {str(e)}")
            else:
                error_message = "No generated images in response"
                print(error_message)
                response_info += f"Error: {error_message}\n"
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, response_info)

            if "usage" in result:
                response_info += "Usage Information:\n"
                if "total_tokens" in result["usage"]:
                    response_info += f"Total Tokens: {result['usage']['total_tokens']}\n"
                if "input_tokens" in result["usage"]:
                    response_info += f"Input Tokens: {result['usage']['input_tokens']}\n"
                if "output_tokens" in result["usage"]:
                    response_info += f"Output Tokens: {result['usage']['output_tokens']}\n"

                if "input_tokens_details" in result["usage"]:
                    response_info += "Input Token Details:\n"
                    details = result["usage"]["input_tokens_details"]
                    if "text_tokens" in details:
                        response_info += f"  Text Tokens: {details['text_tokens']}\n"
                    if "image_tokens" in details:
                        response_info += f"  Image Tokens: {details['image_tokens']}\n"
            
            if generated_images:
                combined_tensor = torch.cat(generated_images, dim=0)
                
                pbar.update_absolute(100)
                return (combined_tensor, response_info)
            else:
                error_message = "No images were successfully processed"
                print(error_message)
                response_info += f"Error: {error_message}\n"
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, response_info)
                
        except Exception as e:
            error_message = f"Error in image generation: {str(e)}"
            print(error_message)
            blank_image = Image.new('RGB', (1024, 1024), color='white')
            blank_tensor = pil2tensor(blank_image)
            return (blank_tensor, error_message)


class ComflyChatGPTApi:
 
    _last_generated_image_urls = ""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "model": ("STRING", {"default": "gpt-4o-image", "multiline": False}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "files": ("FILES",), 
                "image_url": ("STRING", {"multiline": False, "default": ""}),
                "images": ("IMAGE", {"default": None}),  
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.01}),
                "max_tokens": ("INT", {"default": 4096, "min": 1, "max": 16384, "step": 1}),
                "top_p": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "frequency_penalty": ("FLOAT", {"default": -2.0, "min": -2.0, "max": 2.0, "step": 0.01}),
                "presence_penalty": ("FLOAT", {"default": 0.0, "min": -2.0, "max": 2.0, "step": 0.01}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
                "image_download_timeout": ("INT", {"default": 600, "min": 300, "max": 1200, "step": 10}),
                "clear_chats": ("BOOLEAN", {"default": True}),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("images", "response", "image_urls", "chats")
    FUNCTION = "process"
    CATEGORY = "Comfly-v2/Openai"
    
    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 800
        self.image_download_timeout = 600
        self.api_endpoint = f"{baseurl}/v1/chat/completions"
        self.conversation_history = []
 
    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def image_to_base64(self, image):
        """Convert PIL image to base64 string"""
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def file_to_base64(self, file_path):
        """Convert file to base64 string and return appropriate MIME type"""
        try:
            with open(file_path, "rb") as file:
                file_content = file.read()
                encoded_content = base64.b64encode(file_content).decode('utf-8')
                mime_type, _ = mimetypes.guess_type(file_path)
                if not mime_type:
                    mime_type = "application/octet-stream"
                return encoded_content, mime_type
        except Exception as e:
            print(f"Error encoding file: {str(e)}")
            return None, None

    def extract_image_urls(self, response_text):
        """Extract image URLs from markdown format in response"""
      
        image_pattern = r'!\[.*?\]\((.*?)\)'
        matches = re.findall(image_pattern, response_text)
      
        if not matches:
            url_pattern = r'https?://\S+\.(?:jpg|jpeg|png|gif|webp)'
            matches = re.findall(url_pattern, response_text)
        
        if not matches:
            all_urls_pattern = r'https?://\S+'
            matches = re.findall(all_urls_pattern, response_text)
        return matches if matches else []

    def download_image(self, url, timeout=30):
        """Download image from URL and convert to tensor with improved error handling"""
        try:
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://comfyui.com/'
            }
           
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
          
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                print(f"Warning: URL doesn't point to an image. Content-Type: {content_type}")
               
            image = Image.open(BytesIO(response.content))
            return pil2tensor(image)
        except requests.exceptions.Timeout:
            print(f"Timeout error downloading image from {url} (timeout: {timeout}s)")
            return None
        except requests.exceptions.SSLError as e:
            print(f"SSL Error downloading image from {url}: {str(e)}")
            return None
        except requests.exceptions.ConnectionError:
            print(f"Connection error downloading image from {url}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Request error downloading image from {url}: {str(e)}")
            return None
        except Exception as e:
            print(f"Error downloading image from {url}: {str(e)}")
            return None

    def format_conversation_history(self):
        """Format the conversation history for display"""
        if not self.conversation_history:
            return ""
        formatted_history = ""
        for entry in self.conversation_history:
            formatted_history += f"**User**: {entry['user']}\n\n"
            formatted_history += f"**AI**: {entry['ai']}\n\n"
            formatted_history += "---\n\n"
        return formatted_history.strip()

    def send_request_synchronous(self, payload, pbar):
        """Send a synchronous streaming request to the API"""
        full_response = ""
        session = requests.Session()
        
        try:
            response = session.post(
                self.api_endpoint,
                headers=self.get_headers(),
                json=payload, 
                stream=True,
                timeout=self.timeout
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    line_text = line.decode('utf-8').strip()
                    if line_text.startswith('data: '):
                        data = line_text[6:]  
                        if data == '[DONE]':
                            break
                        try:
                            chunk = json.loads(data)
                            if 'choices' in chunk and chunk['choices']:
                                delta = chunk['choices'][0].get('delta', {})
                                if 'content' in delta:
                                    content = delta['content']
                                    full_response += content

                                    pbar.update_absolute(min(40, 20 + len(full_response) // 100))
                        except json.JSONDecodeError:
                            continue
            
            return full_response
            
        except requests.exceptions.Timeout:
            raise TimeoutError(f"API request timed out after {self.timeout} seconds")
        except Exception as e:
            raise Exception(f"Error in streaming response: {str(e)}")

    def process(self, prompt, model, clear_chats=True, files=None, image_url="", images=None, temperature=0.7, 
           max_tokens=4096, top_p=1.0, frequency_penalty=0.0, presence_penalty=0.0, seed=-1,
           image_download_timeout=100, api_key=""):

        if model.lower() == "gpt-image-1":
            error_message = "不支持此模型，请使用 gpt-4o-image，gpt-4o-image-vip，sora_image，sora_image-vip 这4个模型。"
            print(error_message)

            if images is not None:
                return (images, error_message, "", self.format_conversation_history())
            else:
                blank_img = Image.new('RGB', (512, 512), color='white')
                return (pil2tensor(blank_img), error_message, "", self.format_conversation_history())
            
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)

        try:
            self.image_download_timeout = image_download_timeout
          
            if clear_chats:
                self.conversation_history = []
                
            if not self.api_key:
                error_message = "API key not found in Comflyapi.json"
                print(error_message)
               
                blank_img = Image.new('RGB', (512, 512), color='white')
                return (pil2tensor(blank_img), error_message, "", self.format_conversation_history()) 
            
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
           
            if seed < 0:
                seed = random.randint(0, 2147483647)
                print(f"Using random seed: {seed}")
           
            content = []
            
            content.append({"type": "text", "text": prompt})
            
           
            if not clear_chats and ComflyChatGPTApi._last_generated_image_urls:
                prev_image_url = ComflyChatGPTApi._last_generated_image_urls.split('\n')[0].strip()
                if prev_image_url:
                    print(f"Using previous image URL: {prev_image_url}")
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": prev_image_url}
                    })
            
            elif clear_chats:
                if images is not None:
                    batch_size = images.shape[0]
                    max_images = min(batch_size, 4)  
                    for i in range(max_images):
                        pil_image = tensor2pil(images)[i]
                        image_base64 = self.image_to_base64(pil_image)
                        content.append({
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"}
                        })
                    if batch_size > max_images:
                        content.append({
                            "type": "text",
                            "text": f"\n(Note: {batch_size-max_images} additional images were omitted due to API limitations)"
                        })
                
                elif image_url:
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": image_url}
                    })
        
            elif image_url:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
            
            if files:
                file_paths = files if isinstance(files, list) else [files]
                for file_path in file_paths:
                    encoded_content, mime_type = self.file_to_base64(file_path)
                    if encoded_content and mime_type:
                       
                        if mime_type.startswith('image/'):
                           
                            content.append({
                                "type": "image_url", 
                                "image_url": {"url": f"data:{mime_type};base64,{encoded_content}"}
                            })
                        else:
                            
                            content.append({
                                "type": "text", 
                                "text": f"\n\nI've attached a file ({os.path.basename(file_path)}) for analysis."
                            })
                            content.append({
                                "type": "file_url",
                                "file_url": {
                                    "url": f"data:{mime_type};base64,{encoded_content}",
                                    "name": os.path.basename(file_path)
                                }
                            })
        
            messages = []
        
            messages.append({
                "role": "user",
                "content": content
            })
        
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": top_p,
                "frequency_penalty": frequency_penalty,
                "presence_penalty": presence_penalty,
                "seed": seed,
                "stream": True  
            }

            response_text = self.send_request_synchronous(payload, pbar)
        
            self.conversation_history.append({
                "user": prompt,
                "ai": response_text
            })
        
            technical_response = f"**Model**: {model}\n**Temperature**: {temperature}\n**Seed**: {seed}\n**Time**: {timestamp}"
        
            image_urls = self.extract_image_urls(response_text)
            image_urls_string = "\n".join(image_urls) if image_urls else ""
            
            if image_urls:
                ComflyChatGPTApi._last_generated_image_urls = image_urls_string
     
            chat_history = self.format_conversation_history()
            if image_urls:
                try:
                    
                    img_tensors = []
                    successful_downloads = 0
                    for i, url in enumerate(image_urls):
                        print(f"Attempting to download image {i+1}/{len(image_urls)} from: {url}")
                
                        pbar.update_absolute(min(80, 40 + (i+1) * 40 // len(image_urls)))
                        img_tensor = self.download_image(url, self.image_download_timeout)
                        if img_tensor is not None:
                            img_tensors.append(img_tensor)
                            successful_downloads += 1
                    print(f"Successfully downloaded {successful_downloads} out of {len(image_urls)} images")
                    if img_tensors:
                
                        combined_tensor = torch.cat(img_tensors, dim=0)
                        pbar.update_absolute(100)
                        return (combined_tensor, technical_response, image_urls_string, chat_history)
                except Exception as e:
                    print(f"Error processing image URLs: {str(e)}")
        
            if images is not None:
                pbar.update_absolute(100)
                return (images, technical_response, image_urls_string, chat_history)  
            else:
                blank_img = Image.new('RGB', (512, 512), color='white')
                blank_tensor = pil2tensor(blank_img)
                pbar.update_absolute(100)
                return (blank_tensor, technical_response, image_urls_string, chat_history)  
                
        except Exception as e:
            error_message = f"Error calling ChatGPT API: {str(e)}"
            print(error_message)
        
            if images is not None:
                return (images, error_message, "", self.format_conversation_history())  
            else:
                blank_img = Image.new('RGB', (512, 512), color='white')
                blank_tensor = pil2tensor(blank_img)
                return (blank_tensor, error_message, "", self.format_conversation_history())

class Comfly_sora2_openai:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "model": (["sora-2", "sora-2-pro"], {"default": "sora-2"}),
            },
            "optional": {
                "apikey": ("STRING", {"default": ""}),
                "seconds": (["10", "15", "25"], {"default": "15"}),
                "size": (["1280x720", "720x1280", "1792x1024", "1024x1792"], {"default": "1280x720"}),
                "image": ("IMAGE",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
                "private": ("BOOLEAN", {"default": True})
            }
        }
    
    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "response", "video_url", "seed")
    FUNCTION = "process"
    CATEGORY = "Comfly-v2/Openai"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 900

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def image_to_base64(self, image_tensor):
        """Convert tensor to base64 string"""
        if image_tensor is None:
            return None
            
        pil_image = tensor2pil(image_tensor)[0]
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    def process(self, prompt, model, apikey="", seconds="15", size="1280x720", image=None, seed=0, private=True):
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)
            
        if not self.api_key:
            error_response = {"status": "error", "message": "API key not provided or not found in config"}
            return ("", json.dumps(error_response), "", "0")

        if model == "sora-2":
            if seconds == "25":  
                error_message = "The sora-2 model does not support 25 second videos. Please use sora-2-pro for 25 second videos."
                print(error_message)
                return ("", json.dumps({"status": "error", "message": error_message}), "", "0")
            if size in ["1792x1024", "1024x1792"]:
                error_message = "The sora-2 model does not support 1080P resolution. Please use sora-2-pro for 1080P videos."
                print(error_message)
                return ("", json.dumps({"status": "error", "message": error_message}), "", "0")
      
        pbar = comfy.utils.ProgressBar(100)
        pbar.update_absolute(10)
        
        try:
            data = {
                "model": model,
                "prompt": prompt,
                "seconds": seconds,
                "size": size,
                "private": private
            }
            
            if seed > 0:
                data["seed"] = str(seed)
                
            files = []

            if image is not None:
                pil_image = tensor2pil(image)[0]
                buffered = BytesIO()
                pil_image.save(buffered, format="PNG")
                buffered.seek(0)
                files.append(('input_reference', ('image.png', buffered, 'image/png')))
            
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            pbar.update_absolute(20)

            response = requests.post(
                "https://ai.t8star.cn/v1/videos",
                headers=headers,
                data=data,
                files=files,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                return ("", json.dumps({"status": "error", "message": error_message}), "", "0")
                
            result = response.json()
            
            if "id" not in result:
                error_message = "No task ID in API response"
                print(error_message)
                return ("", json.dumps({"status": "error", "message": error_message}), "", "0")
            
            task_id = result["id"]
            print(f"Task ID: {task_id}")
            
            pbar.update_absolute(30)

            max_attempts = 120  
            attempts = 0
            video_url = None
            actual_seed = str(seed) if seed > 0 else "0"
            
            while attempts < max_attempts:
                time.sleep(10)
                attempts += 1
                
                try:
                    status_response = requests.get(
                        f"https://ai.t8star.cn/v1/videos/{task_id}",
                        headers=self.get_headers(),
                        timeout=self.timeout
                    )
                    
                    if status_response.status_code != 200:
                        continue
                        
                    status_data = status_response.json()

                    progress = status_data.get("progress", 0)
                    try:
                        progress_int = int(progress)
                        pbar_value = min(90, 30 + int(progress_int * 0.6))
                        pbar.update_absolute(pbar_value)
                    except (ValueError, TypeError):
                        progress_value = min(80, 30 + (attempts * 50 // max_attempts))
                        pbar.update_absolute(progress_value)
                    
                    status = status_data.get("status", "")
                    
                    if status == "completed":
                        video_url = status_data.get("video_url")
                        if not video_url and "url" in status_data:
                            video_url = status_data.get("url")

                        if "seed" in status_data:
                            actual_seed = str(status_data.get("seed", "0"))
                        
                        break
                    elif status == "failed":
                        fail_reason = status_data.get("fail_reason", "Unknown error")
                        error_message = f"Video generation failed: {fail_reason}"
                        print(error_message)
                        return ("", json.dumps({"status": "error", "message": error_message, "task_id": task_id}), "", actual_seed)
                        
                except Exception as e:
                    print(f"Error checking task status: {str(e)}")
            
            if not video_url:
                error_message = f"Failed to get video URL after {max_attempts} attempts"
                print(error_message)
                return ("", json.dumps({"status": "error", "message": error_message, "task_id": task_id}), "", actual_seed)
            
            video_adapter = ComflyVideoAdapter(video_url)
            
            pbar.update_absolute(100)
            
            response_data = {
                "status": "success",
                "task_id": task_id,
                "prompt": prompt,
                "model": model,
                "size": size,
                "seconds": seconds,
                "private": private,
                "video_url": video_url,
                "seed": actual_seed
            }
            
            return (video_adapter, json.dumps(response_data), video_url, actual_seed)
            
        except Exception as e:
            error_message = f"Error in video generation: {str(e)}"
            print(error_message)
            import traceback
            traceback.print_exc()
            return ("", json.dumps({"status": "error", "message": error_message}), "", "0")
           

class Comfly_sora2:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "model": (["sora-2", "sora-2-pro"], {"default": "sora-2"}),
                "aspect_ratio": (["16:9", "9:16"], {"default": "16:9"}),
                "duration": (["10", "15", "25"], {"default": "15"}),
                "hd": ("BOOLEAN", {"default": False}),
                "apikey": ("STRING", {"default": ""})
            },
            "optional": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "image3": ("IMAGE",),
                "image4": ("IMAGE",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
                "private": ("BOOLEAN", {"default": True})
            }
        }
    
    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "response")
    FUNCTION = "process"
    CATEGORY = "Comfly-v2/Openai"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 900

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def image_to_base64(self, image_tensor):
        """Convert tensor to base64 string with data URI prefix"""
        if image_tensor is None:
            return None
            
        pil_image = tensor2pil(image_tensor)[0]
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        base64_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{base64_str}"
    
    def process(self, prompt, model, aspect_ratio="16:9", duration="10", hd=False, apikey="", 
                image1=None, image2=None, image3=None, image4=None, seed=0, private=True):
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)
            
        if not self.api_key:
            error_response = {"status": "error", "message": "API key not provided or not found in config"}
            return ("", "", json.dumps(error_response))

        if duration == "25" and hd == True:
            error_message = "25s and hd parameters cannot be used together. Please choose only one of them."
            print(error_message)
            return ("", "", json.dumps({"status": "error", "message": error_message}))
            
        if model == "sora-2":
            if duration == "25":  
                error_message = "The sora-2 model does not support 25 second videos. Please use sora-2-pro for 25 second videos."
                print(error_message)
                return ("", "", json.dumps({"status": "error", "message": error_message}))
            if hd:
                error_message = "The sora-2 model does not support HD mode. Please use sora-2-pro for HD videos or disable HD."
                print(error_message)
                return ("", "", json.dumps({"status": "error", "message": error_message}))
      
        pbar = comfy.utils.ProgressBar(100)
        pbar.update_absolute(10)
        
        try:
            has_image = any(img is not None for img in [image1, image2, image3, image4])
            
            if has_image:
                images = []
                for img in [image1, image2, image3, image4]:
                    if img is not None:
                        img_base64 = self.image_to_base64(img)
                        if img_base64:
                            images.append(img_base64)
                
                if not images:
                    error_message = "Failed to process any of the input images"
                    print(error_message)
                    return ("", "", json.dumps({"status": "error", "message": error_message}))
                
                payload = {
                    "prompt": prompt,
                    "model": model,
                    "images": images,
                    "aspect_ratio": aspect_ratio,
                    "duration": duration,
                    "hd": hd,
                    "private": private
                }
                
                if seed > 0:
                    payload["seed"] = seed
                
                endpoint = f"{baseurl}/v2/videos/generations"
            else:
                payload = {
                    "prompt": prompt,
                    "model": model,
                    "aspect_ratio": aspect_ratio,
                    "duration": duration,
                    "hd": hd,
                    "private": private
                }
                
                if seed > 0:
                    payload["seed"] = seed
                    
                endpoint = f"{baseurl}/v2/videos/generations"
            
            pbar.update_absolute(20)
            
            response = requests.post(
                endpoint,
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                return ("", "", json.dumps({"status": "error", "message": error_message}))
                
            result = response.json()
            
            if "task_id" not in result:
                error_message = "No task ID in API response"
                print(error_message)
                return ("", "", json.dumps({"status": "error", "message": error_message}))
            
            task_id = result["task_id"]
            print(f"Task ID: {task_id}")
            
            pbar.update_absolute(30)

            max_attempts = 300  
            attempts = 0
            video_url = None
            
            while attempts < max_attempts:
                time.sleep(10)
                attempts += 1
                
                try:
                    status_response = requests.get(
                        f"{baseurl}/v2/videos/generations/{task_id}",
                        headers=self.get_headers(),
                        timeout=self.timeout
                    )
                    
                    if status_response.status_code != 200:
                        continue
                        
                    status_data = status_response.json()

                    progress_text = status_data.get("progress", "0%")
                    try:
                        if progress_text.endswith('%'):
                            progress_value = int(progress_text[:-1])
                            pbar_value = min(90, 30 + int(progress_value * 0.6))
                            pbar.update_absolute(pbar_value)
                    except (ValueError, AttributeError):
                        progress_value = min(80, 30 + (attempts * 50 // max_attempts))
                        pbar.update_absolute(progress_value)
                    
                    status = status_data.get("status", "")
                    
                    if status == "SUCCESS":
                        if "data" in status_data and "output" in status_data["data"]:
                            video_url = status_data["data"]["output"]
                            break
                            
                    elif status == "FAILURE":
                        fail_reason = status_data.get("fail_reason", "Unknown error")
                        error_message = f"Video generation failed: {fail_reason}"
                        print(error_message)
                        return ("", "", json.dumps({"status": "error", "message": error_message, "task_id": task_id}))
                        
                except Exception as e:
                    print(f"Error checking task status: {str(e)}")
            
            if not video_url:
                error_message = f"Failed to get video URL after {max_attempts} attempts"
                print(error_message)
                return ("", "", json.dumps({"status": "error", "message": error_message, "task_id": task_id}))
            
            video_adapter = ComflyVideoAdapter(video_url)
            
            pbar.update_absolute(100)
            
            response_data = {
                "status": "success",
                "task_id": task_id,
                "prompt": prompt,
                "model": model,
                "aspect_ratio": aspect_ratio,
                "duration": duration,
                "hd": hd,
                "private": private,
                "video_url": video_url
            }
            
            return (video_adapter, video_url, json.dumps(response_data))
            
        except Exception as e:
            error_message = f"Error in video generation: {str(e)}"
            print(error_message)
            import traceback
            traceback.print_exc()
            return ("", "", json.dumps({"status": "error", "message": error_message}))


class Comfly_sora2_chat:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "model": (["sora-2", "sora-2-pro"], {"default": "sora-2"}),
                "duration": (["10", "15", "25"], {"default": "15"}),
                "orientation": (["portrait", "landscape"], {"default": "portrait"})
            },
            "optional": {
                "image": ("IMAGE",),
                "hd": ("BOOLEAN", {"default": False}),
                "apikey": ("STRING", {"default": ""}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647})
            }
        }
    
    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "gif_url", "response")
    FUNCTION = "generate_video"
    CATEGORY = "Comfly-v2/Openai"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 900

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def image_to_base64(self, image_tensor):
        """Convert tensor to base64 string with data URI prefix"""
        if image_tensor is None:
            return None
            
        pil_image = tensor2pil(image_tensor)[0]
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        base64_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{base64_str}"
    
    def generate_video(self, prompt, model="sora-2", duration="15", orientation="portrait", 
                      image=None, hd=False, apikey="", seed=0):
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)
            
        if not self.api_key:
            error_response = {"status": "error", "message": "API key not provided or not found in config"}
            return ("", "", "", json.dumps(error_response))

        if duration == "25" and hd:
            error_message = "25s and hd parameters cannot be used together. Please choose only one of them."
            print(error_message)
            return ("", "", "", json.dumps({"status": "error", "message": error_message}))
 
        if model == "sora-2":
            if duration == "25":
                error_message = "The sora-2 model does not support 25 second videos. Please use sora-2-pro for 25 second videos."
                print(error_message)
                return ("", "", "", json.dumps({"status": "error", "message": error_message}))
            if hd:
                error_message = "The sora-2 model does not support HD mode. Please use sora-2-pro for HD videos or disable HD."
                print(error_message)
                return ("", "", "", json.dumps({"status": "error", "message": error_message}))
      
        pbar = comfy.utils.ProgressBar(100)
        pbar.update_absolute(10)
        
        try:
            final_prompt = f"高清，{prompt}" if hd else prompt

            content = [
                {"type": "text", "text": final_prompt}
            ]

            if image is not None:
                image_base64 = self.image_to_base64(image)
                if image_base64:
                    content.append({
                        "type": "image_url", 
                        "image_url": {"url": image_base64}
                    })
            
            messages = [{"role": "user", "content": content}]
            
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": 8192,
                "temperature": 0.5,
                "top_p": 1,
                "presence_penalty": 0,
                "stream": True
            }

            if seed > 0:
                payload["seed"] = seed
            
            pbar.update_absolute(20)

            response = requests.post(
                f"{baseurl}/v1/chat/completions",
                headers=self.get_headers(),
                json=payload,
                stream=True,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                return ("", "", "", json.dumps({"status": "error", "message": error_message}))

            full_response = ""
            task_id = None
            data_preview_url = None
            
            for line in response.iter_lines():
                if line:
                    line_text = line.decode("utf-8")
                    if line_text.startswith("data: "):
                        data_str = line_text[6:]
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            if 'choices' in data and data['choices']:
                                delta = data['choices'][0].get('delta', {})
                                if 'content' in delta:
                                    content = delta['content']
                                    full_response += content

                                    if not task_id:
                                        task_id_match = re.search(r"ID: `(task_[a-zA-Z0-9]+)`", full_response)
                                        if task_id_match:
                                            task_id = task_id_match.group(1)
                                            print(f"Found task ID: {task_id}")

                                    if not data_preview_url and task_id:
                                        preview_match = re.search(r"\[数据预览\]\((https://asyncdata.net/web/[^)]+)\)", full_response)
                                        if preview_match:
                                            data_preview_url = preview_match.group(1)
                                            print(f"Found data preview URL: {data_preview_url}")
                                            pbar.update_absolute(30)
                                            break  
                        except json.JSONDecodeError:
                            continue
            
            if not task_id:
                error_message = "Failed to obtain task ID from the response"
                print(error_message)
                return ("", "", "", json.dumps({"status": "error", "message": error_message, "response": full_response}))
            
            pbar.update_absolute(40)

            max_attempts = 120  
            attempts = 0
            video_url = None
            gif_url = None
            
            while attempts < max_attempts:
                time.sleep(10)
                attempts += 1
                
                try:
                    status_response = requests.get(
                        f"https://asyncdata.net/api/share/{task_id}",
                        timeout=self.timeout
                    )
                    
                    if status_response.status_code != 200:
                        continue
                        
                    status_data = status_response.json()

                    content_data = status_data.get("content", {})
                    progress = content_data.get("progress", 0)
                    status = content_data.get("status", "")

                    if progress > 0:
                        pbar_value = min(90, 40 + int(progress * 0.5))
                        pbar.update_absolute(pbar_value)
                    else:
                        progress_value = min(80, 40 + (attempts * 40 // max_attempts))
                        pbar.update_absolute(progress_value)

                    if status == "completed" and "url" in content_data:
                        video_url = content_data.get("url")
                        gif_url = content_data.get("gif_url", "")
                        break
                        
                except Exception as e:
                    print(f"Error checking task status: {str(e)}")
            
            if not video_url:
                error_message = f"Failed to get video URL after {max_attempts} attempts"
                print(error_message)
                return ("", "", "", json.dumps({"status": "error", "message": error_message, "task_id": task_id}))

            video_adapter = ComflyVideoAdapter(video_url)
            
            pbar.update_absolute(100)

            response_data = {
                "status": "success",
                "task_id": task_id,
                "prompt": prompt,
                "model": model,
                "duration": duration,
                "orientation": orientation,
                "hd": hd,
                "seed": seed if seed > 0 else "auto",
                "video_url": video_url,
                "gif_url": gif_url
            }
            
            return (video_adapter, video_url, gif_url, json.dumps(response_data))
            
        except Exception as e:
            error_message = f"Error in video generation: {str(e)}"
            print(error_message)
            import traceback
            traceback.print_exc()
            return ("", "", "", json.dumps({"status": "error", "message": error_message}))




############################# Flux ###########################

class Comfly_Flux_Kontext:
    _last_image_url = ""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
            },
            "optional": {
                "input_image": ("IMAGE",),
                "model": (["flux-kontext-dev", "flux-kontext-pro", "flux-kontext-max"], {"default": "flux-kontext-pro"}),
                "apikey": ("STRING", {"default": ""}),
                "aspect_ratio": (["Default", "21:9", "16:9", "4:3", "3:2", "1:1", "2:3", "3:4", "9:16", "9:21"], 
                         {"default": "Default"}),
                "guidance": ("FLOAT", {"default": 3.5, "min": 1.0, "max": 20.0, "step": 0.5}),
                "num_of_images": ("INT", {"default": 1, "min": 1, "max": 4}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
                "clear_image": ("BOOLEAN", {"default": True})
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "image_url")
    FUNCTION = "generate_image"
    CATEGORY = "Comfly-v2/Flux"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def upload_image(self, image_tensor):
        """Upload image to the file endpoint and return the URL"""
        try:
            pil_image = tensor2pil(image_tensor)[0]
            buffered = BytesIO()
            pil_image.save(buffered, format="PNG")
            file_content = buffered.getvalue()
            
            files = {'file': ('image.png', file_content, 'image/png')}
            
            response = requests.post(
                f"{baseurl}/v1/files",
                headers={"Authorization": f"Bearer {self.api_key}"},
                files=files,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            result = response.json()
            
            if 'url' in result:
                return result['url']
            else:
                print(f"Unexpected response from file upload API: {result}")
                return None
                
        except Exception as e:
            print(f"Error uploading image: {str(e)}")
            return None
    
    def generate_image(self, prompt, input_image=None, model="flux-kontext-pro", 
                  apikey="", aspect_ratio="Default", guidance=3.5, num_of_images=1,
                  seed=-1, clear_image=True):
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)
            
        if not self.api_key:
            error_message = "API key not found in Comflyapi.json"
            print(error_message)

            if input_image is None:
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, "")
            return (input_image, "")
        
        try:
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            final_prompt = prompt
            custom_dimensions = None

            if input_image is not None:
                batch_size = input_image.shape[0]
                all_image_urls = []
                
                for i in range(batch_size):
                    single_image = input_image[i:i+1]
                    pbar.update_absolute(10 + (i * 10) // batch_size)
                    image_url = self.upload_image(single_image)
                    if image_url:
                        all_image_urls.append(image_url)

                if all_image_urls:
                    image_urls_text = " ".join(all_image_urls)
                    final_prompt = f"{image_urls_text} {prompt}"
                    if aspect_ratio == "match_input_image" and batch_size > 0:
                        pil_image = tensor2pil(input_image)[0]
                        width, height = pil_image.size
                        custom_dimensions = {"width": width, "height": height}
                else:
                    print("Failed to upload any images")
                    if input_image is None:
                        blank_image = Image.new('RGB', (1024, 1024), color='white')
                        blank_tensor = pil2tensor(blank_image)
                        return (blank_tensor, "")
                    return (input_image, "")
 
            elif not clear_image and Comfly_Flux_Kontext._last_image_url:
                final_prompt = f"{Comfly_Flux_Kontext._last_image_url} {prompt}"

            payload = {
                "prompt": final_prompt,
                "model": model,
                "n": num_of_images,  
                "guidance_scale": guidance  
            }

            if custom_dimensions and aspect_ratio == "match_input_image":
                payload.update(custom_dimensions)
            else:
                payload["aspect_ratio"] = aspect_ratio

            if seed != -1:
                payload["seed"] = seed

            response = requests.post(
                f"{baseurl}/v1/images/generations",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            pbar.update_absolute(50)
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                if input_image is None:
                    blank_image = Image.new('RGB', (1024, 1024), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, "")
                return (input_image, "")
                
            result = response.json()

            if not result.get("data") or not result["data"]:
                error_message = "No image data in response"
                print(error_message)
                if input_image is None:
                    blank_image = Image.new('RGB', (1024, 1024), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, "")
                return (input_image, "")

            generated_tensors = []
            image_urls = []
            
            for i, item in enumerate(result["data"]):
                pbar.update_absolute(50 + (i+1) * 40 // len(result["data"]))
                
                if "url" in item:
                    image_url = item["url"]
                    image_urls.append(image_url)
                    
                    try:
                        img_response = requests.get(image_url, timeout=self.timeout)
                        img_response.raise_for_status()
                        generated_image = Image.open(BytesIO(img_response.content))
                        generated_tensor = pil2tensor(generated_image)
                        generated_tensors.append(generated_tensor)
                    except Exception as e:
                        print(f"Error downloading image from URL: {str(e)}")
                        
                elif "b64_json" in item:
                    image_data = base64.b64decode(item["b64_json"])
                    generated_image = Image.open(BytesIO(image_data))
                    generated_tensor = pil2tensor(generated_image)
                    generated_tensors.append(generated_tensor)
            
            pbar.update_absolute(100)
            
            if generated_tensors:
                combined_tensor = torch.cat(generated_tensors, dim=0)

                if image_urls:
                    Comfly_Flux_Kontext._last_image_url = image_urls[0]
                
                return (combined_tensor, "\n".join(image_urls))
            else:
                error_message = "Failed to process any images"
                print(error_message)
                if input_image is None:
                    blank_image = Image.new('RGB', (1024, 1024), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, "")
                return (input_image, "")
            
        except Exception as e:
            error_message = f"Error in image generation: {str(e)}"
            print(error_message)
            if input_image is None:
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, "")
            return (input_image, "")
         
        
class Comfly_Flux_Kontext_Edit:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
            },
            "optional": {
                "image": ("IMAGE",),
                "model": (["flux-kontext-dev", "flux-kontext-pro", "flux-kontext-max"], {"default": "flux-kontext-pro"}),
                "apikey": ("STRING", {"default": ""}),
                "aspect_ratio": (["21:9", "16:9", "4:3", "3:2", "1:1", "2:3", "3:4", "9:16", "9:21"], 
                         {"default": "1:1"}),
                "num_of_images": ("INT", {"default": 1, "min": 1, "max": 4}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647})
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "image_url")
    FUNCTION = "generate_image"
    CATEGORY = "Comfly-v2/Flux"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def generate_image(self, prompt, image=None, model="flux-kontext-pro", 
                  apikey="", aspect_ratio="1:1", num_of_images=1,
                  seed=-1):
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)
            
        if not self.api_key:
            error_message = "API key not found in Comflyapi.json"
            print(error_message)

            if image is None:
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, "")
            return (image, "")
        
        try:
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            if image is not None:
                pil_image = tensor2pil(image)[0]

                buffered = BytesIO()
                pil_image.save(buffered, format="PNG")
                buffered.seek(0)

                files = {
                    'image': ('image.png', buffered, 'image/png')
                }
                
                data = {
                    'prompt': prompt,
                    'model': model
                }

                if aspect_ratio != "Default":
                    data["aspect_ratio"] = aspect_ratio

                if seed != -1:
                    data["seed"] = str(seed)
                    
                if num_of_images > 1:
                    data["n"] = str(num_of_images)

                pbar.update_absolute(30)
                response = requests.post(
                    f"{baseurl}/v1/images/edits",
                    headers=self.get_headers(),
                    data=data,
                    files=files,
                    timeout=self.timeout
                )
            else:
                payload = {
                    "prompt": prompt,
                    "model": model,
                    "n": num_of_images
                }
                
                if aspect_ratio != "Default":
                    payload["aspect_ratio"] = aspect_ratio
                
                if seed != -1:
                    payload["seed"] = seed
                    
                headers = self.get_headers()
                headers["Content-Type"] = "application/json"
                
                response = requests.post(
                    f"{baseurl}/v1/images/generations",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )
            
            pbar.update_absolute(50)
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                if image is None:
                    blank_image = Image.new('RGB', (1024, 1024), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, "")
                return (image, "")
                
            result = response.json()

            if not result.get("data") or not result["data"]:
                error_message = "No image data in response"
                print(error_message)
                if image is None:
                    blank_image = Image.new('RGB', (1024, 1024), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, "")
                return (image, "")

            generated_tensors = []
            image_urls = []
            
            for i, item in enumerate(result["data"]):
                pbar.update_absolute(50 + (i+1) * 40 // len(result["data"]))
                
                if "url" in item:
                    image_url = item["url"]
                    image_urls.append(image_url)
                    
                    try:
                        img_response = requests.get(image_url, timeout=self.timeout)
                        img_response.raise_for_status()
                        generated_image = Image.open(BytesIO(img_response.content))
                        generated_tensor = pil2tensor(generated_image)
                        generated_tensors.append(generated_tensor)
                    except Exception as e:
                        print(f"Error downloading image from URL: {str(e)}")
                        
                elif "b64_json" in item:
                    image_data = base64.b64decode(item["b64_json"])
                    generated_image = Image.open(BytesIO(image_data))
                    generated_tensor = pil2tensor(generated_image)
                    generated_tensors.append(generated_tensor)
            
            pbar.update_absolute(100)
            
            if generated_tensors:
                combined_tensor = torch.cat(generated_tensors, dim=0)
                return (combined_tensor, "\n".join(image_urls))
            else:
                error_message = "Failed to process any images"
                print(error_message)
                if image is None:
                    blank_image = Image.new('RGB', (1024, 1024), color='white')
                    blank_tensor = pil2tensor(blank_image)
                    return (blank_tensor, "")
                return (image, "")
            
        except Exception as e:
            error_message = f"Error in image generation: {str(e)}"
            print(error_message)
            if image is None:
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, "")
            return (image, "")



class Comfly_Flux_Kontext_bfl:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "model": (["flux-kontext-pro", "flux-kontext-max"], {"default": "flux-kontext-pro"}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "input_image": ("IMAGE",),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
                "aspect_ratio": (["21:9", "16:9", "4:3", "3:2", "1:1", "2:3", "3:4", "9:16", "9:21"], 
                         {"default": "1:1"}),
                "output_format": (["png", "jpeg"], {"default": "png"}),
                "prompt_upsampling": ("BOOLEAN", {"default": False}),
                "safety_tolerance": ("INT", {"default": 2, "min": 0, "max": 6})
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "response")
    FUNCTION = "generate_image"
    CATEGORY = "Comfly-v2/Flux"
    OUTPUT_NODE = True

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def image_to_base64(self, image_tensor):
        """Convert tensor to base64 string"""
        if image_tensor is None:
            return None
            
        pil_image = tensor2pil(image_tensor)[0]
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    def generate_image(self, prompt, model="flux-kontext-pro", input_image=None, 
                      seed=-1, aspect_ratio="1:1", output_format="png", 
                      prompt_upsampling=False, safety_tolerance=2, api_key=""):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)

        if input_image is not None:
            default_tensor = input_image  
        else:
            blank_image = Image.new('RGB', (512, 512), color='white')
            default_tensor = pil2tensor(blank_image)
            
        if not self.api_key:
            error_response = {"status": "failed", "message": "API key not found"}
            return (default_tensor, "", json.dumps(error_response))
            
        pbar = comfy.utils.ProgressBar(100)
        pbar.update_absolute(10)

        api_endpoint = f"{baseurl}/bfl/v1/{model}"
        
        try:
            payload = {
                "prompt": prompt,
                "output_format": output_format,
                "prompt_upsampling": prompt_upsampling,
                "safety_tolerance": safety_tolerance
            }

            if input_image is not None:
                input_image_base64 = self.image_to_base64(input_image)
                if input_image_base64:
                    payload["input_image"] = input_image_base64
            
            if seed != -1:
                payload["seed"] = seed
                
            if aspect_ratio:
                payload["aspect_ratio"] = aspect_ratio

            response = requests.post(
                api_endpoint,
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            pbar.update_absolute(30)
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                return (default_tensor, "", json.dumps({"status": "failed", "message": error_message}))
                
            result = response.json()
            
            if "id" not in result or "polling_url" not in result:
                error_message = "Invalid response format from API"
                print(error_message)
                return (default_tensor, "", json.dumps({"status": "failed", "message": error_message}))
                
            task_id = result["id"]
            polling_url = result["polling_url"]

            pbar.update_absolute(40)

            max_attempts = 60  
            attempts = 0
            image_url = ""
            
            while attempts < max_attempts:
                time.sleep(10)
                attempts += 1
                
                try:
                    result_response = requests.get(
                        f"{baseurl}/bfl/v1/get_result?id={task_id}",
                        headers=self.get_headers(),
                        timeout=self.timeout
                    )
                    
                    if result_response.status_code != 200:
                        continue
                        
                    result_data = result_response.json()
                    status = result_data.get("status")
                    
                    if status == "Ready":
                        if "result" in result_data and "sample" in result_data["result"]:
                            image_url = result_data["result"]["sample"]
                            break

                    progress = min(80, 40 + (attempts * 40 // max_attempts))
                    pbar.update_absolute(progress)
                        
                except Exception as e:
                    print(f"Error checking generation status: {str(e)}")
            
            if not image_url:
                error_message = "Failed to retrieve generated image URL after multiple attempts"
                print(error_message)
                return (default_tensor, "", json.dumps({"status": "failed", "message": error_message}))

            pbar.update_absolute(90)
            
            try:
                img_response = requests.get(image_url, timeout=self.timeout)
                img_response.raise_for_status()
                
                generated_image = Image.open(BytesIO(img_response.content))
                generated_tensor = pil2tensor(generated_image)
                
                pbar.update_absolute(100)
                
                result_info = {
                    "status": "success",
                    "task_id": task_id,
                    "prompt": prompt,
                    "model": model,
                    "seed": seed if seed > 0 else "random",
                    "aspect_ratio": aspect_ratio
                }
                
                return (generated_tensor, image_url, json.dumps(result_info))
                
            except Exception as e:
                error_message = f"Error downloading generated image: {str(e)}"
                print(error_message)
                return (default_tensor, image_url, json.dumps({"status": "partial_success", "message": error_message, "image_url": image_url}))
            
        except Exception as e:
            error_message = f"Error in image generation: {str(e)}"
            print(error_message)
            import traceback
            traceback.print_exc()
            return (default_tensor, "", json.dumps({"status": "failed", "message": error_message}))



############################# Googel ###########################

class Comfly_Googel_Veo3:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "model": (["veo3", "veo3-fast", "veo3-pro", "veo3-fast-frames", "veo3-pro-frames", "veo3.1", "veo3.1-pro", "veo3.1-components"], {"default": "veo3"}),
                "enhance_prompt": ("BOOLEAN", {"default": False}),
                "aspect_ratio": (["16:9", "9:16"], {"default": "16:9"}),
            },
            "optional": {
                "apikey": ("STRING", {"default": ""}),
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "image3": ("IMAGE",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
                "enable_upsample": ("BOOLEAN", {"default": False}),
            }
        }
    
    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "response")
    FUNCTION = "generate_video"
    CATEGORY = "Comfly-v2/Google"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def image_to_base64(self, image_tensor):
        """Convert tensor to base64 string"""
        if image_tensor is None:
            return None
            
        pil_image = tensor2pil(image_tensor)[0]
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    def generate_video(self, prompt, model="veo3", enhance_prompt=False, aspect_ratio="16:9", apikey="", 
                      image1=None, image2=None, image3=None, seed=0, enable_upsample=False):
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)
            
        if not self.api_key:
            error_response = {"code": "error", "message": "API key not found in Comflyapi.json"}
            return ("", "", json.dumps(error_response))
            
        try:
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            has_images = any(img is not None for img in [image1, image2, image3])
 
            payload = {
                "prompt": prompt,
                "model": model,
                "enhance_prompt": enhance_prompt
            }
 
            if seed > 0:
                payload["seed"] = seed

            if model in ["veo3", "veo3-fast", "veo3-pro", "veo3.1", "veo3.1-pro"] and aspect_ratio:
                payload["aspect_ratio"] = aspect_ratio

            if model in ["veo3", "veo3-fast", "veo3-pro", "veo3.1", "veo3.1-pro"] and enable_upsample:
                payload["enable_upsample"] = enable_upsample

            if has_images:
                images_base64 = []
                for img in [image1, image2, image3]:
                    if img is not None:
                        batch_size = img.shape[0]
                        for i in range(batch_size):
                            single_image = img[i:i+1]
                            image_base64 = self.image_to_base64(single_image)
                            if image_base64:
                                images_base64.append(f"data:image/png;base64,{image_base64}")
                
                if images_base64:
                    payload["images"] = images_base64

            response = requests.post(
                f"{baseurl}/google/v1/models/veo/videos",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                return ("", "", json.dumps({"code": "error", "message": error_message}))
                
            result = response.json()
            
            if result.get("code") != "success":
                error_message = f"API returned error: {result.get('message', 'Unknown error')}"
                print(error_message)
                return ("", "", json.dumps({"code": "error", "message": error_message}))
                
            task_id = result.get("data")
            if not task_id:
                error_message = "No task ID returned from API"
                print(error_message)
                return ("", "", json.dumps({"code": "error", "message": error_message}))
            
            pbar.update_absolute(30)

            max_attempts = 60  
            attempts = 0
            video_url = None
            
            while attempts < max_attempts:
                time.sleep(10)
                attempts += 1
                
                try:
                    status_response = requests.get(
                        f"{baseurl}/google/v1/tasks/{task_id}",
                        headers=self.get_headers(),
                        timeout=self.timeout
                    )
                    
                    if status_response.status_code != 200:
                        continue
                        
                    status_result = status_response.json()
                    
                    if status_result.get("code") != "success":
                        continue
                    
                    data = status_result.get("data", {})
                    status = data.get("status", "")
                    progress = data.get("progress", "0%")
                    
                    try:
                        if progress.endswith('%'):
                            progress_num = int(progress.rstrip('%'))
                            pbar_value = min(90, 30 + progress_num * 60 / 100)
                            pbar.update_absolute(pbar_value)
                    except (ValueError, AttributeError):
                        progress_value = min(80, 30 + (attempts * 50 // max_attempts))
                        pbar.update_absolute(progress_value)
                    
                    if status == "SUCCESS":
                        if "data" in data and "video_url" in data["data"]:
                            video_url = data["data"]["video_url"]
                            break
                    elif status == "FAILURE":
                        fail_reason = data.get("fail_reason", "Unknown error")
                        error_message = f"Video generation failed: {fail_reason}"
                        print(error_message)
                        return ("", "", json.dumps({"code": "error", "message": error_message}))
                        
                except Exception as e:
                    print(f"Error checking generation status: {str(e)}")
            
            if not video_url:
                error_message = "Failed to retrieve video URL after multiple attempts"
                print(error_message)
                return ("", "", json.dumps({"code": "error", "message": error_message}))
            
            if video_url:
                pbar.update_absolute(95)
                
                response_data = {
                    "code": "success",
                    "task_id": task_id,
                    "prompt": prompt,
                    "model": model,
                    "enhance_prompt": enhance_prompt,
                    "aspect_ratio": aspect_ratio if model in ["veo3", "veo3-fast", "veo3-pro"] else "default",
                    "enable_upsample": enable_upsample if model in ["veo3", "veo3-fast", "veo3-pro"] else False,
                    "video_url": video_url,
                    "images_count": len([img for img in [image1, image2, image3] if img is not None])
                }
                
                video_adapter = ComflyVideoAdapter(video_url)
                return (video_adapter, video_url, json.dumps(response_data))
            
        except Exception as e:
            error_message = f"Error generating video: {str(e)}"
            print(error_message)
            return ("", "", json.dumps({"code": "error", "message": error_message}))


class Comfly_nano_banana:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True}),
                "model": (["gemini-2.5-flash-image", "nano-banana", "nano-banana-hd", "gemini-2.5-flash-image-preview"], {"default": "nano-banana"}),
            },
            "optional": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "image3": ("IMAGE",),
                "image4": ("IMAGE",),
                "temperature": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05}),
                "top_p": ("FLOAT", {"default": 0.95, "min": 0.0, "max": 1.0, "step": 0.05}),
                "apikey": ("STRING", {"default": ""}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
                "max_tokens": ("INT", {"default": 32768, "min": 1, "max": 32768})
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "response", "image_url")
    FUNCTION = "process"
    CATEGORY = "Comfly-v2/Google"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def image_to_base64(self, image_tensor):
        """Convert tensor to base64 string with data URI prefix"""
        if image_tensor is None:
            return None
            
        pil_image = tensor2pil(image_tensor)[0]
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        base64_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return base64_str

    def send_request_streaming(self, payload):
        """Send a streaming request to the API"""
        full_response = ""
        session = requests.Session()
        
        try:
            response = session.post(
                f"{baseurl}/v1/chat/completions",
                headers=self.get_headers(),
                json=payload, 
                stream=True,
                timeout=self.timeout
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    line_text = line.decode('utf-8').strip()
                    if line_text.startswith('data: '):
                        data = line_text[6:]  
                        if data == '[DONE]':
                            break
                        try:
                            chunk = json.loads(data)
                            if 'choices' in chunk and chunk['choices']:
                                delta = chunk['choices'][0].get('delta', {})
                                if 'content' in delta:
                                    content = delta['content']
                                    full_response += content
                        except json.JSONDecodeError:
                            continue
            
            return full_response
            
        except requests.exceptions.Timeout:
            raise TimeoutError(f"API request timed out after {self.timeout} seconds")
        except Exception as e:
            raise Exception(f"Error in streaming response: {str(e)}")

    def process(self, text, model="gemini-2.5-flash-image-preview", 
                image1=None, image2=None, image3=None, image4=None,
                temperature=1.0, top_p=0.95, apikey="", seed=0, max_tokens=32768):
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)

        default_image = None
        for img in [image1, image2, image3, image4]:
            if img is not None:
                default_image = img
                break

        if default_image is None:
            blank_image = Image.new('RGB', (512, 512), color='white')
            default_image = pil2tensor(blank_image)

        try:
            if not self.api_key:
                return (default_image, "API key not provided. Please set your API key.", "")

            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            content = [{"type": "text", "text": text}]

            images_added = 0
            for idx, img in enumerate([image1, image2, image3, image4], 1):
                if img is not None:
                    batch_size = img.shape[0]
                    print(f"Processing image{idx} with {batch_size} batch size")
                    
                    for i in range(batch_size):
                        single_image = img[i:i+1]
                        image_base64 = self.image_to_base64(single_image)
                        if image_base64:
                            content.append({
                                "type": "image_url", 
                                "image_url": {"url": f"data:image/png;base64,{image_base64}"}
                            })
                            images_added += 1

            print(f"Total of {images_added} images added to the request")

            messages = [{
                "role": "user",
                "content": content
            }]

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens,
                "stream": True 
            }

            if seed > 0:
                payload["seed"] = seed

            pbar.update_absolute(30)

            try:
                response_text = self.send_request_streaming(payload)
                pbar.update_absolute(70)
            except Exception as e:
                error_message = f"API Error: {str(e)}"
                print(error_message)
                return (default_image, error_message, "")

            base64_pattern = r'data:image\/[^;]+;base64,([A-Za-z0-9+/=]+)'
            base64_matches = re.findall(base64_pattern, response_text)
            
            if base64_matches:
                try:
                    image_data = base64.b64decode(base64_matches[0])
                    generated_image = Image.open(BytesIO(image_data))
                    generated_tensor = pil2tensor(generated_image)
                    
                    pbar.update_absolute(100)
                    return (generated_tensor, response_text, f"data:image/png;base64,{base64_matches[0]}")
                except Exception as e:
                    print(f"Error processing base64 image data: {str(e)}")

            image_pattern = r'!\[.*?\]\((.*?)\)'
            matches = re.findall(image_pattern, response_text)
            
            if not matches:
                url_pattern = r'https?://\S+\.(?:jpg|jpeg|png|gif|webp)'
                matches = re.findall(url_pattern, response_text)
            
            if not matches:
                all_urls_pattern = r'https?://\S+'
                matches = re.findall(all_urls_pattern, response_text)
                
            if matches:
                image_url = matches[0]
                try:
                    img_response = requests.get(image_url, timeout=self.timeout)
                    img_response.raise_for_status()
                    
                    generated_image = Image.open(BytesIO(img_response.content))
                    generated_tensor = pil2tensor(generated_image)
                    
                    pbar.update_absolute(100)
                    return (generated_tensor, response_text, image_url)
                except Exception as e:
                    print(f"Error downloading image: {str(e)}")
                    return (default_image, f"{response_text}\n\nError downloading image: {str(e)}", image_url)
            else:
                pbar.update_absolute(100)
                return (default_image, response_text, "")
                
        except Exception as e:
            error_message = f"Error processing request: {str(e)}"
            print(error_message)
            return (default_image, error_message, "")


class Comfly_nano_banana_fal:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "model": (["nano-banana", "nano-banana/edit"], {"default": "nano-banana/edit"}),
                "num_images": ("INT", {"default": 1, "min": 1, "max": 4}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
                "image_way": (["image", "image_url"], {"default": "image_url"})
            },
            "optional": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "image3": ("IMAGE",),
                "image4": ("IMAGE",),
                "apikey": ("STRING", {"default": ""})
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "response")
    FUNCTION = "process"
    CATEGORY = "Comfly-v2/Google"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def image_to_base64(self, image_tensor):
        """Convert tensor to base64 string with data URI prefix"""
        if image_tensor is None:
            return None
            
        pil_image = tensor2pil(image_tensor)[0]
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        base64_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{base64_str}"

    def upload_image_to_get_url(self, image_tensor):
        """Upload image to files API and get URL"""
        if image_tensor is None:
            return None
            
        try:
            pil_image = tensor2pil(image_tensor)[0]
            buffered = BytesIO()
            pil_image.save(buffered, format="PNG")
            file_content = buffered.getvalue()
            
            files = {'file': ('image.png', file_content, 'image/png')}
            
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = requests.post(
                f"{baseurl}/v1/files",
                headers=headers,
                files=files,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            result = response.json()
            
            if 'url' in result:
                return result['url']
            else:
                print(f"Unexpected response from file upload API: {result}")
                return None
                
        except Exception as e:
            print(f"Error uploading image: {str(e)}")
            return None

    def process(self, prompt, model, num_images=1, seed=0, image_way="image",
                image1=None, image2=None, image3=None, image4=None, apikey=""):
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)

        default_image = None
        for img in [image1, image2, image3, image4]:
            if img is not None:
                default_image = img
                break
                
        if default_image is None:
            blank_image = Image.new('RGB', (512, 512), color='white')
            default_image = pil2tensor(blank_image)
        
        try:
            if not self.api_key:
                return (default_image, "API key not provided. Please set your API key.")

            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            image_urls = []

            if image_way == "image":
                print("Using base64 encoded images")
                for idx, img in enumerate([image1, image2, image3, image4]):
                    if img is not None:
                        image_base64 = self.image_to_base64(img)
                        if image_base64:
                            image_urls.append(image_base64)
            else:  
                print("Uploading images to get URLs")
                input_images = [img for img in [image1, image2, image3, image4] if img is not None]
                total_images = len(input_images)
                
                for idx, img in enumerate(input_images):
                    progress = 10 + int((idx / max(1, total_images)) * 10)
                    pbar.update_absolute(progress)
                    
                    img_url = self.upload_image_to_get_url(img)
                    if img_url:
                        image_urls.append(img_url)
                        print(f"Image {idx+1}/{total_images} uploaded, URL: {img_url}")
                    else:
                        print(f"Failed to upload image {idx+1}/{total_images}")

            pbar.update_absolute(20)
            
            if model.endswith("/edit"):
                api_endpoint = f"{baseurl}/fal-ai/{model}"

                payload = {
                    "prompt": prompt,
                    "num_images": num_images
                }
                
                if seed > 0:
                    payload["seed"] = seed

                if image_urls and len(image_urls) > 0:
                    payload["image_urls"] = image_urls
                
                pbar.update_absolute(30)

                response = requests.post(
                    api_endpoint,
                    headers=self.get_headers(),
                    json=payload,
                    timeout=self.timeout
                )
            else:
                api_endpoint = f"{baseurl}/fal-ai/{model}"
                
                payload = {
                    "prompt": prompt,
                    "num_images": num_images
                }
                
                if seed > 0:
                    payload["seed"] = seed
                    
                if image_urls:
                    payload["image_urls"] = image_urls
                
                pbar.update_absolute(30)

                response = requests.post(
                    api_endpoint,
                    headers=self.get_headers(),
                    json=payload,
                    timeout=self.timeout
                )

            if response.status_code != 200:
                return (default_image, f"API Error: {response.status_code} - {response.text}")
                
            result = response.json()
 
            if "request_id" not in result:
                return (default_image, "No request_id in response: " + str(result))
            
            request_id = result.get("request_id")
            response_url = result.get("response_url", "")
 
            if "queue.fal.run" in response_url:
                response_url = response_url.replace("https://queue.fal.run", "https://ai.t8star.cn")

            if not response_url:
                response_url = f"{baseurl}/fal-ai/{model}/requests/{request_id}"
            
            pbar.update_absolute(50)

            max_retries = 30
            retry_count = 0
            result_data = None 
            
            while retry_count < max_retries:
                retry_count += 1
                pbar.update_absolute(50 + min(40, retry_count * 40 // max_retries))
                
                try:
                    result_response = requests.get(
                        response_url,
                        headers=self.get_headers(),
                        timeout=self.timeout
                    )
                    
                    if result_response.status_code != 200:
                        time.sleep(1)
                        continue
                        
                    result_data = result_response.json()

                    if "images" in result_data and result_data["images"]:
                        break

                    time.sleep(1)
                    
                except Exception as e:
                    print(f"Error fetching result: {str(e)}")
                    time.sleep(1)

            if result_data is None:
                return (default_image, "Failed to retrieve results after multiple attempts")

            if "images" not in result_data or not result_data["images"]:
                return (default_image, "No images in response: " + str(result_data))

            generated_images = []
            
            for i, img_data in enumerate(result_data["images"]):
                if "url" in img_data:
                    img_url = img_data["url"]
                    if "queue.fal.run" in img_url:
                        img_url = img_url.replace("https://queue.fal.run", "https://ai.t8star.cn")
                    
                    try:
                        img_response = requests.get(img_url, timeout=self.timeout)
                        if img_response.status_code == 200:
                            generated_image = Image.open(BytesIO(img_response.content))
                            generated_tensor = pil2tensor(generated_image)
                            generated_images.append(generated_tensor)
                    except Exception as e:
                        print(f"Error downloading image: {str(e)}")
            
            if generated_images:
                combined_tensor = torch.cat(generated_images, dim=0)
                pbar.update_absolute(100)
                return (combined_tensor, f"Successfully generated {len(generated_images)} images using {model}")
            else:
                return (default_image, "Failed to process any images from the API response")
                
        except Exception as e:
            error_message = f"Error processing request: {str(e)}"
            print(error_message)
            import traceback
            traceback.print_exc()
            return (default_image, error_message)


class Comfly_nano_banana_edit:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "mode": (["text2img", "img2img"], {"default": "text2img"}),
                "model": (["nano-banana", "nano-banana-hd"], {"default": "nano-banana"}),
                "aspect_ratio": (["16:9", "4:3", "4:5", "3:2", "1:1", "2:3", "3:4", "5:4", "9:16", "21:9"], {"default": "1:1"}),
            },
            "optional": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "image3": ("IMAGE",),
                "image4": ("IMAGE",),
                "apikey": ("STRING", {"default": ""}),
                "response_format": (["url", "b64_json"], {"default": "url"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647})  
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "response")
    FUNCTION = "generate_image"
    CATEGORY = "Comfly-v2/Google"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 600

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def image_to_base64(self, image_tensor):
        """Convert tensor to base64 string"""
        if image_tensor is None:
            return None
            
        pil_image = tensor2pil(image_tensor)[0]
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    def generate_image(self, prompt, mode="text2img", model="nano-banana", aspect_ratio="1:1", 
                      image1=None, image2=None, image3=None, image4=None,
                      apikey="", response_format="url", seed=0):  
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)
            
        if not self.api_key:
            error_message = "API key not found in Comflyapi.json"
            print(error_message)
            blank_image = Image.new('RGB', (1024, 1024), color='white')
            blank_tensor = pil2tensor(blank_image)
            return (blank_tensor, error_message)
            
        try:
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            final_prompt = prompt
            
            if mode == "text2img":
                headers = self.get_headers()
                headers["Content-Type"] = "application/json"
                
                payload = {
                    "prompt": final_prompt,
                    "model": model,
                    "aspect_ratio": aspect_ratio  
                }
                    
                if response_format:
                    payload["response_format"] = response_format

                if seed > 0:
                    payload["seed"] = seed
                
                response = requests.post(
                    f"{baseurl}/v1/images/generations",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )
            else:
                headers = self.get_headers()
                
                files = []
                for img in [image1, image2, image3, image4]:
                    if img is not None:
                        pil_img = tensor2pil(img)[0]
                        buffered = BytesIO()
                        pil_img.save(buffered, format="PNG")
                        buffered.seek(0)
                        files.append(('image', ('image.png', buffered, 'image/png')))
                
                data = {
                    "prompt": final_prompt,
                    "model": model,
                    "aspect_ratio": aspect_ratio 
                }
                
                if response_format:
                    data["response_format"] = response_format

                if seed > 0:
                    data["seed"] = str(seed)
                
                response = requests.post(
                    f"{baseurl}/v1/images/edits",
                    headers=headers,
                    data=data,
                    files=files,
                    timeout=self.timeout
                )
            
            pbar.update_absolute(50)
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, error_message)
                
            result = response.json()
            
            if "data" not in result or not result["data"]:
                error_message = "No image data in response"
                print(error_message)
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, error_message)
            
            generated_tensors = []
            response_info = f"Generated {len(result['data'])} images using {model}\n"
            response_info += f"Aspect ratio: {aspect_ratio}\n"

            if seed > 0:
                response_info += f"Seed: {seed}\n"
            
            for i, item in enumerate(result["data"]):
                pbar.update_absolute(50 + (i+1) * 40 // len(result["data"]))
                
                if "b64_json" in item:
                    image_data = base64.b64decode(item["b64_json"])
                    generated_image = Image.open(BytesIO(image_data))
                    generated_tensor = pil2tensor(generated_image)
                    generated_tensors.append(generated_tensor)
                    response_info += f"Image {i+1}: Base64 data\n"
                elif "url" in item:
                    image_url = item["url"]
                    response_info += f"Image {i+1}: {image_url}\n"
                    try:
                        img_response = requests.get(image_url, timeout=self.timeout)
                        img_response.raise_for_status()
                        generated_image = Image.open(BytesIO(img_response.content))
                        generated_tensor = pil2tensor(generated_image)
                        generated_tensors.append(generated_tensor)
                    except Exception as e:
                        print(f"Error downloading image from URL: {str(e)}")
            
            pbar.update_absolute(100)
            
            if generated_tensors:
                combined_tensor = torch.cat(generated_tensors, dim=0)
                return (combined_tensor, response_info)
            else:
                error_message = "Failed to process any images"
                print(error_message)
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, error_message)
            
        except Exception as e:
            error_message = f"Error in image generation: {str(e)}"
            print(error_message)
            blank_image = Image.new('RGB', (1024, 1024), color='white')
            blank_tensor = pil2tensor(blank_image)
            return (blank_tensor, error_message)



 ############################# Qwen ###########################

class Comfly_qwen_image:
    
    """
    A node that generates images using Qwen AI service
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "size": (["512x512", "1024x1024", "768x1024", "576x1024", "1024x768", "1024x576", "Custom"], {"default": "1024x768"}),
                "Custom_size": ("STRING", {"default": "Enter custom size (e.g. 1280x720)", "multiline": False}),
                "model": (["qwen-image"], {"default": "qwen-image"}),
                "num_images": ([1, 2, 3, 4], {"default": 1}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "num_inference_steps": ("INT", {"default": 30, "min": 2, "max": 50, "step": 1}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "guidance_scale": ("FLOAT", {"default": 2.5, "min": 0, "max": 20, "step": 0.5}),
                "enable_safety_checker": ("BOOLEAN", {"default": True}),
                "negative_prompt": ("STRING", {"default": "", "multiline": True}),
                "output_format": (["jpeg", "png"], {"default": "png"}),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "response", "image_url")
    FUNCTION = "generate_image"
    CATEGORY = "Comfly-v2/Qwen"
       
    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
 
    def generate_image(self, prompt, size, Custom_size, model, num_images=1,
                       api_key="", num_inference_steps=30, seed=0, guidance_scale=2.5, 
                       enable_safety_checker=True, negative_prompt="", output_format="png"):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        try:
            if not self.api_key:
                error_message = "API key not found in Comflyapi.json"
                print(error_message)
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, error_message, "")
                
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            
            actual_size = Custom_size if size == "Custom" else size

            if size == "Custom" and (Custom_size == "Enter custom size (e.g. 1280x720)" or "x" not in Custom_size):
                error_message = "Please enter a valid custom size in the format 'widthxheight' (e.g. 1280x720)"
                print(error_message)
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, error_message, "")

            payload = {
                "prompt": prompt,
                "size": actual_size,  
                "model": model,
                "n": num_images,  
            }

            if num_inference_steps != 30:
                payload["num_inference_steps"] = num_inference_steps
                
            if seed != 0:
                payload["seed"] = seed
                
            if guidance_scale != 2.5:
                payload["guidance_scale"] = guidance_scale
                
            if not enable_safety_checker:
                payload["enable_safety_checker"] = enable_safety_checker
                
            if negative_prompt.strip():
                payload["negative_prompt"] = negative_prompt
                
            if output_format != "png":
                payload["output_format"] = output_format
            
            pbar.update_absolute(30)
            
            response = requests.post(
                f"{baseurl}/v1/images/generations", 
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            pbar.update_absolute(50)
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, error_message, "")
                
            result = response.json()

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            response_info = f"**Qwen Image Generation ({timestamp})**\n\n"
            response_info += f"Prompt: {prompt}\n"
            response_info += f"Model: {model}\n"
            response_info += f"Size: {actual_size}\n"
            response_info += f"Number of Images: {num_images}\n"
            response_info += f"Seed: {seed}\n\n"
            
            generated_images = []
            image_urls = []
            
            if "data" in result and result["data"]:
                for i, item in enumerate(result["data"]):
                    pbar.update_absolute(50 + (i+1) * 40 // len(result["data"]))
                    
                    if "b64_json" in item:
                        image_data = base64.b64decode(item["b64_json"])
                        generated_image = Image.open(BytesIO(image_data))
                        generated_tensor = pil2tensor(generated_image)
                        generated_images.append(generated_tensor)
                    elif "url" in item:
                        image_url = item["url"]
                        image_urls.append(image_url)
                        try:
                            img_response = requests.get(image_url, timeout=self.timeout)
                            img_response.raise_for_status()
                            generated_image = Image.open(BytesIO(img_response.content))
                            generated_tensor = pil2tensor(generated_image)
                            generated_images.append(generated_tensor)
                        except Exception as e:
                            print(f"Error downloading image from URL: {str(e)}")
            else:
                error_message = "No generated images in response"
                print(error_message)
                response_info += f"Error: {error_message}\n"
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, response_info, "")
                
            if generated_images:
                combined_tensor = torch.cat(generated_images, dim=0)
                
                pbar.update_absolute(100)
                return (combined_tensor, response_info, image_urls[0] if image_urls else "")
            else:
                error_message = "No images were successfully processed"
                print(error_message)
                response_info += f"Error: {error_message}\n"
                blank_image = Image.new('RGB', (1024, 1024), color='white')
                blank_tensor = pil2tensor(blank_image)
                return (blank_tensor, response_info, "")
                
        except Exception as e:
            error_message = f"Error in image generation: {str(e)}"
            print(error_message)
            blank_image = Image.new('RGB', (1024, 1024), color='white')
            blank_tensor = pil2tensor(blank_image)
            return (blank_tensor, error_message, "")


class Comfly_qwen_image_edit:
    
    """
    A node that edits images using Qwen AI service
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "image": ("IMAGE",),
                "size": (["512x512", "1024x1024", "768x1024", "576x1024", "1024x768", "1024x576", "Custom"], {"default": "1024x768"}),
                "Custom_size": ("STRING", {"default": "Enter custom size (e.g. 1280x720)", "multiline": False}),
                "model": (["qwen-image-edit"], {"default": "qwen-image-edit"}),
            },
            "optional": {
                "apikey": ("STRING", {"default": ""}),
                "num_inference_steps": ("INT", {"default": 30, "min": 2, "max": 50, "step": 1}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "guidance_scale": ("FLOAT", {"default": 4.0, "min": 0, "max": 20, "step": 0.5}),
                "enable_safety_checker": ("BOOLEAN", {"default": True}),
                "negative_prompt": ("STRING", {"default": "", "multiline": True}),
                "output_format": (["jpeg", "png"], {"default": "png"}),
                "num_images": ("INT", {"default": 1, "min": 1, "max": 4}),
                "acceleration": (["none", "regular", "high"], {"default": "none"}),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "response", "image_url")
    FUNCTION = "edit_image"
    CATEGORY = "Comfly-v2/Qwen"
       
    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
 
    def edit_image(self, prompt, image, size, Custom_size, model,
                  apikey="", num_inference_steps=30, seed=0, guidance_scale=4.0, 
                  enable_safety_checker=True, negative_prompt="", output_format="png",
                  num_images=1, acceleration="none"):
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)
            
        try:
            if not self.api_key:
                error_message = "API key not found in Comflyapi.json"
                print(error_message)
                return (image, error_message, "")
                
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            
            actual_size = Custom_size if size == "Custom" else size

            if size == "Custom" and (Custom_size == "Enter custom size (e.g. 1280x720)" or "x" not in Custom_size):
                error_message = "Please enter a valid custom size in the format 'widthxheight' (e.g. 1280x720)"
                print(error_message)
                return (image, error_message, "")

            pil_image = tensor2pil(image)[0]

            buffered = BytesIO()
            pil_image.save(buffered, format="PNG")
            buffered.seek(0) 

            files = {
                'image': ('image.png', buffered, 'image/png')
            }
            
            data = {
                "prompt": prompt,
                "size": actual_size,  
                "model": model,
                "n": str(num_images),
            }

            if num_inference_steps != 30:
                data["num_inference_steps"] = str(num_inference_steps)
                
            if seed != 0:
                data["seed"] = str(seed)
                
            if guidance_scale != 4.0:
                data["guidance_scale"] = str(guidance_scale)
                
            if not enable_safety_checker:
                data["enable_safety_checker"] = str(enable_safety_checker).lower()
                
            if negative_prompt.strip():
                data["negative_prompt"] = negative_prompt
                
            if output_format != "png":
                data["output_format"] = output_format
                
            if acceleration != "none":
                data["acceleration"] = acceleration
            
            pbar.update_absolute(30)

            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            response = requests.post(
                f"{baseurl}/v1/images/edits", 
                headers=headers,
                files=files,
                data=data,
                timeout=self.timeout
            )
            
            pbar.update_absolute(50)
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                return (image, error_message, "")
                
            result = response.json()

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            response_info = f"**Qwen Image Edit ({timestamp})**\n\n"
            response_info += f"Prompt: {prompt}\n"
            response_info += f"Model: {model}\n"
            response_info += f"Size: {actual_size}\n"
            response_info += f"Number of Images: {num_images}\n"
            response_info += f"Acceleration: {acceleration}\n"
            response_info += f"Seed: {seed}\n\n"
            
            edited_images = []
            image_urls = []
            
            if "data" in result and result["data"]:
                for i, item in enumerate(result["data"]):
                    pbar.update_absolute(50 + (i+1) * 40 // len(result["data"]))
                    
                    if "b64_json" in item:
                        image_data = base64.b64decode(item["b64_json"])
                        edited_image = Image.open(BytesIO(image_data))
                        edited_tensor = pil2tensor(edited_image)
                        edited_images.append(edited_tensor)
                    elif "url" in item:
                        image_url = item["url"]
                        image_urls.append(image_url)
                        try:
                            img_response = requests.get(image_url, timeout=self.timeout)
                            img_response.raise_for_status()
                            edited_image = Image.open(BytesIO(img_response.content))
                            edited_tensor = pil2tensor(edited_image)
                            edited_images.append(edited_tensor)
                        except Exception as e:
                            print(f"Error downloading image from URL: {str(e)}")
            else:
                error_message = "No edited images in response"
                print(error_message)
                response_info += f"Error: {error_message}\n"
                return (image, response_info, "")
                
            if edited_images:
                combined_tensor = torch.cat(edited_images, dim=0)
                
                pbar.update_absolute(100)
                return (combined_tensor, response_info, image_urls[0] if image_urls else "")
            else:
                error_message = "No images were successfully processed"
                print(error_message)
                response_info += f"Error: {error_message}\n"
                return (image, response_info, "")
                
        except Exception as e:
            error_message = f"Error in image editing: {str(e)}"
            print(error_message)
            return (image, error_message, "")


############################# MiniMax ###########################

class Comfly_MiniMax_video:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "model": (["MiniMax-Hailuo-02", "T2V-01", "T2V-01-Director", "I2V-01-Director", "I2V-01-live", "I2V-01", "S2V-01"], {"default": "MiniMax-Hailuo-02"}),
                "duration": (["6", "10"], {"default": "6"}),
                "resolution": (["720P","768P", "1080P"], {"default": "768P"}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "prompt_optimizer": ("BOOLEAN", {"default": True}),
                "fast_pretreatment": ("BOOLEAN", {"default": False}),
                "first_frame_image": ("IMAGE",),
                "last_frame_image": ("IMAGE",),
                "subject_reference": ("IMAGE",),  
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
            }
        }
    
    RETURN_TYPES = (IO.VIDEO, "STRING", "STRING")
    RETURN_NAMES = ("video", "task_id", "response")
    FUNCTION = "generate_video"
    CATEGORY = "Comfly-v2/MiniMax"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 600
        self.api_endpoint = f"{baseurl}/minimax/v1/video_generation"
        self.query_endpoint = f"{baseurl}/minimax/v1/query/video_generation"

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def image_to_base64(self, image_tensor):
        """Convert tensor to base64 string"""
        if image_tensor is None:
            return None
            
        pil_image = tensor2pil(image_tensor)[0]
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    def generate_video(self, prompt, model="MiniMax-Hailuo-02", duration="6", resolution="768P", 
               prompt_optimizer=True, fast_pretreatment=False, first_frame_image=None, last_frame_image=None,
               subject_reference=None, api_key="", seed=0):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        if not self.api_key:
            error_response = {"status": "error", "message": "API key not provided or not found in config"}
            return (None, "", json.dumps(error_response))
            
        try:
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            payload = {
                "model": model,
                "prompt": prompt,
                "duration": int(duration),
                "resolution": resolution,
                "prompt_optimizer": prompt_optimizer
            }

            if seed > 0:
                payload["seed"] = seed

            if model == "MiniMax-Hailuo-02":
                payload["fast_pretreatment"] = fast_pretreatment

                if fast_pretreatment and last_frame_image is not None:
                    print("Note: fast_pretreatment is disabled when last_frame_image is provided")
                    payload["fast_pretreatment"] = False

            if model in ["T2V-01", "T2V-01-Director"]:
                if first_frame_image is not None or last_frame_image is not None:
                    print(f"Warning: Model {model} only supports text-to-video. Image inputs will be ignored.")
                
            elif model in ["I2V-01-Director", "I2V-01-live", "I2V-01"]:
                if first_frame_image is None:
                    print(f"Warning: Model {model} requires first_frame_image for image-to-video generation.")
                if last_frame_image is not None:
                    print(f"Warning: Model {model} doesn't support last_frame_image. It will be ignored.")

            if first_frame_image is not None and model != "T2V-01" and model != "T2V-01-Director":
                image_base64 = self.image_to_base64(first_frame_image)
                if image_base64:
                    payload["first_frame_image"] = f"data:image/png;base64,{image_base64}"

            if last_frame_image is not None and model == "MiniMax-Hailuo-02":
                image_base64 = self.image_to_base64(last_frame_image)
                if image_base64:
                    payload["last_frame_image"] = f"data:image/png;base64,{image_base64}"

            if model == "S2V-01" and subject_reference is not None:
                image_base64 = self.image_to_base64(subject_reference)
                if image_base64:
                    payload["subject_reference"] = {
                        "type": "character",
                        "image": [f"data:image/png;base64,{image_base64}"]
                    }
            
            response = requests.post(
                self.api_endpoint,
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            pbar.update_absolute(30)
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                return (None, "", json.dumps({"status": "error", "message": error_message}))
                
            result = response.json()
            
            if "base_resp" not in result or result["base_resp"]["status_code"] != 0:
                error_message = f"API returned error: {result.get('base_resp', {}).get('status_msg', 'Unknown error')}"
                print(error_message)
                return (None, "", json.dumps({"status": "error", "message": error_message}))
                
            task_id = result.get("task_id")
            if not task_id:
                error_message = "No task ID returned from API"
                print(error_message)
                return (None, "", json.dumps({"status": "error", "message": error_message}))
            
            pbar.update_absolute(40)
            print(f"Video generation task submitted. Task ID: {task_id}")

            max_attempts = 120  
            attempts = 0
            file_id = None
            video_url = None
            
            while attempts < max_attempts:
                time.sleep(10)  
                attempts += 1
                
                try:
                    status_response = requests.get(
                        f"{self.query_endpoint}?task_id={task_id}",
                        headers=self.get_headers(),
                        timeout=self.timeout
                    )
                    
                    if status_response.status_code != 200:
                        print(f"Error checking status: {status_response.status_code} - {status_response.text}")
                        continue
                        
                    status_result = status_response.json()
                    
                    if "base_resp" not in status_result or status_result["base_resp"]["status_code"] != 0:
                        print(f"Error in status response: {status_result.get('base_resp', {}).get('status_msg', 'Unknown error')}")
                        continue
                    
                    status = status_result.get("status", "")
                    
                    progress_value = min(80, 40 + (attempts * 40 // max_attempts))
                    pbar.update_absolute(progress_value)
                    
                    if status == "Success":
                        file_id = status_result.get("file_id")
                        if file_id:
                            video_retrieval_url = f"{baseurl}/minimax/v1/files/retrieve?file_id={file_id}"
                            file_response = requests.get(
                                video_retrieval_url,
                                headers=self.get_headers(),
                                timeout=self.timeout
                            )
                            
                            if file_response.status_code == 200:
                                file_data = file_response.json()
                                if "file" in file_data and "download_url" in file_data["file"]:
                                    video_url = file_data["file"]["download_url"]
                                    break
                                else:
                                    video_url = f"{baseurl}/minimax/v1/file?file_id={file_id}"
                                    break
                            else:
                                video_url = f"{baseurl}/minimax/v1/file?file_id={file_id}"
                                break
                    elif status == "Failed":
                        error_message = f"Video generation failed: {status_result.get('base_resp', {}).get('status_msg', 'Unknown error')}"
                        print(error_message)
                        return (None, task_id, json.dumps({"status": "error", "message": error_message}))
                    
                except Exception as e:
                    print(f"Error checking generation status: {str(e)}")
            
            if not file_id:
                error_message = "Failed to retrieve file_id after multiple attempts"
                print(error_message)
                return (None, task_id, json.dumps({"status": "error", "message": error_message}))
                
            if not video_url:
                video_url = f"{baseurl}/minimax/v1/file?file_id={file_id}"
            
            pbar.update_absolute(90)
            print(f"Video generation completed. URL: {video_url}")
            
            video_adapter = ComflyVideoAdapter(video_url)
            
            response_data = {
                "status": "success",
                "task_id": task_id,
                "file_id": file_id,
                "video_url": video_url,
                "width": status_result.get("video_width", 0),
                "height": status_result.get("video_height", 0)
            }
            
            pbar.update_absolute(100)
            return (video_adapter, task_id, json.dumps(response_data))
            
        except Exception as e:
            error_message = f"Error generating video: {str(e)}"
            print(error_message)
            import traceback
            traceback.print_exc()
            return (None, "", json.dumps({"status": "error", "message": error_message}))



############################# Suno ###########################

class Comfly_suno_description:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "title": ("STRING", {"default": ""}),
                "description_prompt": ("STRING", {"multiline": True}),
                "version": (["v3.0", "v3.5", "v4", "v4.5", "v4.5+", "v5"], {"default": "v4.5"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
                "make_instrumental": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "apikey": ("STRING", {"default": ""})
            }
        }
    
    RETURN_TYPES = ("AUDIO", "AUDIO", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio1", "audio2", "audio_url1", "audio_url2", "prompt", "task_id", "response", "clip_id1", "clip_id2", "tags", "title")
    FUNCTION = "generate_music"
    CATEGORY = "Comfly-v2/Suno"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300
        
    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key
        }
    
    def generate_music(self, title, description_prompt, version="v4.5", seed=0, make_instrumental=False, apikey=""):
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)
            
        if not self.api_key:
            error_message = "API key not found in Comflyapi.json"
            print(error_message)
            empty_audio = create_audio_object("")
            return (empty_audio, empty_audio, "", "", "", "", error_message, "", "", "", "")
        
        mv_mapping = {
            "v3.0": "chirp-v3.0",
            "v3.5": "chirp-v3.5", 
            "v4": "chirp-v4",
            "v4.5": "chirp-auk",
            "v4.5+": "chirp-bluejay",
            "v5": "chirp-crow"
        }
        
        mv = mv_mapping.get(version, "chirp-auk")
            
        try:
            payload = {
                "gpt_description_prompt": description_prompt,
                "make_instrumental": make_instrumental,
                "mv": mv,
                "prompt": ""
            }
            if seed > 0:
                payload["seed"] = seed
            
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
           
            response = requests.post(
                f"{baseurl}/suno/generate/description-mode",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            pbar.update_absolute(20)
           
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                empty_audio = create_audio_object("")
                return (empty_audio, empty_audio, "", "", "", "", error_message, "", "", "", "")
                
            result = response.json()
           
            if "id" not in result:
                error_message = "No task ID in response"
                print(error_message)
                empty_audio = create_audio_object("")
                return (empty_audio, empty_audio, "", "", "", "", error_message, "", "", "", "")
                
            task_id = result.get("id")
            
            if "clips" not in result or len(result["clips"]) < 2:
                error_message = "Expected at least 2 clips in the response"
                print(error_message)
                empty_audio = create_audio_object("")
                return (empty_audio, empty_audio, "", "", "", task_id, error_message, "", "", "", "")
                
            clip_ids = [clip["id"] for clip in result["clips"]]
            if len(clip_ids) < 2:
                error_message = "Expected at least 2 clip IDs"
                print(error_message)
                empty_audio = create_audio_object("")
                return (empty_audio, empty_audio, "", "", "", task_id, error_message, "", "", "", "")
                
            pbar.update_absolute(30)
            max_attempts = 30
            attempts = 0
            final_clips = []
            generated_prompt = ""
            extracted_tags = ""
            generated_title = ""  
           
            while attempts < max_attempts and len(final_clips) < 2:
                time.sleep(5)
                attempts += 1
                
                try:
                    clip_response = requests.get(
                        f"{baseurl}/suno/feed/{','.join(clip_ids)}",
                        headers=self.get_headers(),
                        timeout=self.timeout
                    )
                    
                    if clip_response.status_code != 200:
                        continue
                        
                    clips_data = clip_response.json()
                   
                    progress = min(80, 30 + (attempts * 50 // max_attempts))
                    pbar.update_absolute(progress)
                    complete_clips = [
                        clip for clip in clips_data 
                        if clip.get("status") == "complete" and (clip.get("audio_url") or clip.get("state") == "succeeded")
                    ]
                    for clip in complete_clips:
                        if clip.get("id") in clip_ids and clip not in final_clips:
                            final_clips.append(clip)
                            if not generated_prompt and "prompt" in clip:
                                generated_prompt = clip["prompt"]
                            if not extracted_tags and "tags" in clip:
                                extracted_tags = clip["tags"]
                            if not generated_title and "title" in clip and clip["title"]:
                                generated_title = clip["title"]
                    
                    if len(final_clips) >= 2:
                        break
                        
                except Exception as e:
                    print(f"[Description Debug] Error checking clip status: {str(e)}")
            
            if len(final_clips) < 2:
                error_message = f"Only received {len(final_clips)} complete clips after {max_attempts} attempts"
                print(error_message)
                
                if not final_clips:
                    empty_audio = create_audio_object("")
                    return (empty_audio, empty_audio, "", "", "", task_id, error_message, "", "", "", "")
                
            final_title = generated_title if generated_title else title
            for clip in final_clips:
                if "title" not in clip or not clip["title"]:
                    clip["title"] = final_title
                    
            audio_urls = []
            clip_id_values = []
            
            for clip in final_clips[:2]:  
                audio_url = ""
                if "audio_url" in clip and clip["audio_url"]:
                    audio_url = clip["audio_url"]
                elif "cdn1.suno.ai" in str(clip):
                    match = re.search(r'https://cdn1\.suno\.ai/[^"\']+\.mp3', str(clip))
                    if match:
                        audio_url = match.group(0)
                
                if audio_url:
                    print(f"Found audio URL: {audio_url}")
                    audio_urls.append(audio_url)
                else:
                    print(f"No audio URL found in clip")
                    audio_urls.append("")
                    
                clip_id_value = clip.get("id", "")
                if clip_id_value:
                    clip_id_values.append(clip_id_value)
                else:
                    clip_id_values.append("")
                
            while len(audio_urls) < 2:
                audio_urls.append("")
                
            while len(clip_id_values) < 2:
                clip_id_values.append("")
            audio_objects = [create_audio_object(url) for url in audio_urls[:2]]
            while len(audio_objects) < 2:
                audio_objects.append(create_audio_object(""))
            
            pbar.update_absolute(100)
            
            response_info = {
                "status": "success",
                "prompt": generated_prompt,
                "title": final_title, 
                "version": version,
                "seed": seed if seed > 0 else "auto",
                "make_instrumental": make_instrumental,
                "clips_generated": len(final_clips),
                "tags": extracted_tags
            }
            return (
                audio_objects[0],
                audio_objects[1],
                audio_urls[0],
                audio_urls[1],
                generated_prompt,
                task_id,
                json.dumps(response_info),
                clip_id_values[0],
                clip_id_values[1],
                extracted_tags,
                final_title  
            )
                
        except Exception as e:
            error_message = f"Error generating music: {str(e)}"
            print(error_message)
            import traceback
            traceback.print_exc()
            empty_audio = create_audio_object("")
            return (empty_audio, empty_audio, "", "", "", "", error_message, "", "", "", "")


class Comfly_suno_lyrics:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
            },
            "optional": {
                "apikey": ("STRING", {"default": ""})
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("lyrics", "response", "title", "tags")
    FUNCTION = "generate_lyrics"
    CATEGORY = "Comfly-v2/Suno"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300
        
    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key
        }
        
    def generate_lyrics(self, prompt, seed=0, apikey=""):
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)
            
        if not self.api_key:
            error_message = "API key not found in Comflyapi.json"
            print(error_message)
            return ("", json.dumps({"status": "error", "message": error_message}), "", "")
            
        try:
            payload = {"prompt": prompt}
            
            if seed > 0:
                payload["seed"] = seed

            response = requests.post(
                f"{baseurl}/suno/generate/lyrics/",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                return ("", json.dumps({"status": "error", "message": error_message}), "", "")
                
            result = response.json()
            
            if "id" not in result:
                error_message = "No task ID in response"
                print(error_message)
                return ("", json.dumps({"status": "error", "message": error_message}), "", "")
                
            task_id = result.get("id")

            max_attempts = 30
            attempts = 0
            lyrics_text = ""
            generated_title = ""  
            tags = ""
            
            while attempts < max_attempts:
                time.sleep(2)
                attempts += 1
                
                try:
                    lyrics_response = requests.get(
                        f"{baseurl}/suno/lyrics/{task_id}",
                        headers=self.get_headers(),
                        timeout=self.timeout
                    )
                    
                    if lyrics_response.status_code != 200:
                        continue
                        
                    lyrics_data = lyrics_response.json()
                    
                    if lyrics_data.get("status") == "complete" or lyrics_data.get("status") == "succeed":
                        lyrics_text = lyrics_data.get("text", "")
                        generated_title = lyrics_data.get("title", "")  
                        tags = lyrics_data.get("tags", "")
                        break
                        
                except Exception as e:
                    print(f"Error checking lyrics status: {str(e)}")
            
            if not lyrics_text:
                error_message = f"Failed to generate lyrics after {max_attempts} attempts"
                print(error_message)
                return ("", json.dumps({"status": "error", "message": error_message}), "", "")
            
            success_response = {
                "status": "success",
                "title": generated_title,  
                "prompt": prompt,
                "seed": seed if seed > 0 else "auto",
                "tags": tags
            }
            
            return (lyrics_text, json.dumps(success_response), generated_title, tags)  
                
        except Exception as e:
            error_message = f"Error generating lyrics: {str(e)}"
            print(error_message)
            return ("", json.dumps({"status": "error", "message": error_message}), "", "")



class Comfly_suno_custom:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "title": ("STRING", {"default": ""}),
                "version": (["v3.0", "v3.5", "v4", "v4.5", "v4.5+", "v5"], {"default": "v4.5"}),
                "prompt": ("STRING", {"multiline": True}), 
                "tags": ("STRING", {"default": ""}),  
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
            },
            "optional": {
                "apikey": ("STRING", {"default": ""})
            }
        }
    
    RETURN_TYPES = ("AUDIO", "AUDIO", "STRING", "STRING", "STRING", "STRING", 
                   "STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio1", "audio2", "audio_url1", "audio_url2", "task_id", "response",
                   "clip_id1", "clip_id2", "image_large_url1", "image_large_url2", "tags", "title")
    FUNCTION = "generate_music"
    CATEGORY = "Comfly-v2/Suno"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key
        }
    
    def generate_music(self, title, version="v4.5", prompt="", tags="", seed=0, apikey=""):
        if apikey.strip():
            self.api_key = apikey
            config = get_config()
            config['api_key'] = apikey
            save_config(config)
            
        if not self.api_key:
            error_message = "API key not found in Comflyapi.json"
            print(error_message)
            empty_audio = create_audio_object("")
            return (empty_audio, empty_audio, "", "", "", error_message, 
                "", "", "", "", "", "")
        
        mv_mapping = {
            "v3.0": "chirp-v3.0",
            "v3.5": "chirp-v3.5", 
            "v4": "chirp-v4",
            "v4.5": "chirp-auk",
            "v4.5+": "chirp-bluejay",
            "v5": "chirp-crow"
        }
        
        mv = mv_mapping.get(version, "chirp-auk")
            
        try:
            payload = {
                "prompt": prompt,
                "tags": tags,
                "mv": mv,
                "title": title  
            }
            if seed > 0:
                payload["seed"] = seed
            
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
           
            response = requests.post(
                f"{baseurl}/suno/generate",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            pbar.update_absolute(20)
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                empty_audio = create_audio_object("")
                return (empty_audio, empty_audio, "", "", "", error_message, 
                    "", "", "", "", "", "")
                
            result = response.json()
            
            if "id" not in result:
                error_message = "No task ID in response"
                print(error_message)
                empty_audio = create_audio_object("")
                return (empty_audio, empty_audio, "", "", "", error_message, 
                    "", "", "", "", "", "")
                
            task_id = result.get("id")
            
            if "clips" not in result or len(result["clips"]) < 2:
                error_message = "Expected at least 2 clips in the response"
                print(error_message)
                empty_audio = create_audio_object("")
                return (empty_audio, empty_audio, "", "", task_id, error_message, 
                    "", "", "", "", "", "")
                
            clip_ids = [clip["id"] for clip in result["clips"]]
            if len(clip_ids) < 2:
                error_message = "Expected at least 2 clip IDs"
                print(error_message)
                empty_audio = create_audio_object("")
                return (empty_audio, empty_audio, "", "", task_id, error_message, 
                    "", "", "", "", "", "")
                
            pbar.update_absolute(30)
            max_attempts = 30
            attempts = 0
            final_clips = []
            final_tags = tags  
            generated_title = ""  
            
            while attempts < max_attempts and len(final_clips) < 2:
                time.sleep(5)
                attempts += 1
                
                try:
                    clip_response = requests.get(
                        f"{baseurl}/suno/feed/{','.join(clip_ids)}",
                        headers=self.get_headers(),
                        timeout=self.timeout
                    )
                    
                    if clip_response.status_code != 200:
                        continue
                        
                    clips_data = clip_response.json()
                    
                    progress = min(80, 30 + (attempts * 50 // max_attempts))
                    pbar.update_absolute(progress)
                    complete_clips = [
                        clip for clip in clips_data 
                        if clip.get("status") == "complete" and (clip.get("audio_url") or clip.get("state") == "succeeded")
                    ]
                    
                    for clip in complete_clips:
                        if clip.get("id") in clip_ids and clip not in final_clips:
                            final_clips.append(clip)
                            if "tags" in clip and clip["tags"]:
                                final_tags = clip["tags"]
                            if "title" in clip and clip["title"]:
                                generated_title = clip["title"]
                    
                    if len(final_clips) >= 2:
                        break
                        
                except Exception as e:
                    print(f"[Custom Debug] Error checking clip status: {str(e)}")
            
            if len(final_clips) < 2:
                error_message = f"Only received {len(final_clips)} complete clips after {max_attempts} attempts"
                print(error_message)
                
                if not final_clips:
                    empty_audio = create_audio_object("")
                    return (empty_audio, empty_audio, "", "", task_id, error_message, 
                        "", "", "", "", "", "")
            final_title = generated_title if generated_title else title
                    
            audio_urls = []
            clip_id_values = []
            image_large_urls = []
            
            for clip in final_clips[:2]:
                audio_url = ""
                if "audio_url" in clip and clip["audio_url"]:
                    audio_url = clip["audio_url"]
                elif "cdn1.suno.ai" in str(clip):
                    match = re.search(r'https://cdn1\.suno\.ai/[^"\']+\.mp3', str(clip))
                    if match:
                        audio_url = match.group(0)
                
                audio_urls.append(audio_url if audio_url else "")
                clip_id = clip.get("clip_id", clip.get("id", ""))
                clip_id_values.append(clip_id)
                image_large_url = clip.get("image_large_url", "")
                image_large_urls.append(image_large_url)
            while len(audio_urls) < 2:
                audio_urls.append("")
                
            while len(clip_id_values) < 2:
                clip_id_values.append("")
                
            while len(image_large_urls) < 2:
                image_large_urls.append("")
            audio_objects = [create_audio_object(url) for url in audio_urls[:2]]
            while len(audio_objects) < 2:
                audio_objects.append(create_audio_object(""))
            
            pbar.update_absolute(100)
            
            response_info = {
                "status": "success",
                "title": final_title,
                "version": version,
                "seed": seed if seed > 0 else "auto",
                "clips_generated": len(final_clips),
                "tags": final_tags
            }
            return (
                audio_objects[0],  
                audio_objects[1],  
                audio_urls[0],     
                audio_urls[1],     
                task_id,
                json.dumps(response_info),
                clip_id_values[0],
                clip_id_values[1],
                image_large_urls[0],
                image_large_urls[1],
                final_tags,
                final_title  
            )
                
        except Exception as e:
            error_message = f"Error generating music: {str(e)}"
            print(error_message)
            import traceback
            traceback.print_exc()
            empty_audio = create_audio_object("")
            return (empty_audio, empty_audio, "", "", "", error_message, "", "", "", "", "", "")
        

class Comfly_suno_upload:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "upload_filename": ("STRING", {"default": "audio.mp3"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("clip_id", "title", "tags", "lyrics", "response")
    FUNCTION = "upload_audio"
    CATEGORY = "Comfly-v2/Suno"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def upload_audio(self, audio, api_key="", upload_filename="audio.mp3", seed=0):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        if not self.api_key:
            error_message = "API key not found in Comflyapi.json"
            print(error_message)
            return ("", "", "", "", error_message)
            
        try:
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
 
            extension = upload_filename.split('.')[-1] if '.' in upload_filename else "mp3"
            payload = {"extension": extension}

            if seed > 0:
                payload["seed"] = seed
            
            response = requests.post(
                f"{baseurl}/suno/uploads/audio",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                error_message = f"Failed to get upload URL: {response.status_code} - {response.text}"
                print(error_message)
                return ("", "", "", "", error_message)
                
            upload_data = response.json()
            upload_id = upload_data["id"]
            upload_url = upload_data["url"]
            fields = upload_data["fields"]
            
            pbar.update_absolute(30)

            waveform = audio["waveform"]
            sample_rate = audio["sample_rate"]

            if len(waveform.shape) == 3:
                waveform = waveform.squeeze(0)

            temp_file = io.BytesIO()
            torchaudio.save(temp_file, waveform, sample_rate, format="mp3")
            temp_file.seek(0)
            audio_data = temp_file.read()

            files = {
                'Content-Type': ('', fields['Content-Type']),
                'key': ('', fields['key']),
                'AWSAccessKeyId': ('', fields['AWSAccessKeyId']),
                'policy': ('', fields['policy']),
                'signature': ('', fields['signature']),
                'file': (upload_filename, audio_data, 'audio/mpeg')
            }
            
            upload_response = requests.post(upload_url, files=files, timeout=self.timeout)
            
            if upload_response.status_code != 204:
                error_message = f"Failed to upload audio: {upload_response.status_code}"
                print(error_message)
                return ("", "", "", "", error_message)
                
            pbar.update_absolute(50)

            finish_payload = {
                "upload_type": "file_upload",
                "upload_filename": upload_filename
            }
            
            finish_response = requests.post(
                f"{baseurl}/suno/uploads/audio/{upload_id}/upload-finish",
                headers=self.get_headers(),
                json=finish_payload,
                timeout=self.timeout
            )
            
            if finish_response.status_code != 200:
                error_message = f"Failed to finish upload: {finish_response.status_code}"
                print(error_message)
                return ("", "", "", "", error_message)
                
            pbar.update_absolute(60)

            max_attempts = 20
            attempts = 0
            clip_id = ""
            title = ""
            tags = ""
            lyrics = ""
            
            while attempts < max_attempts:
                time.sleep(2)
                attempts += 1
                
                status_response = requests.get(
                    f"{baseurl}/suno/uploads/audio/{upload_id}",
                    headers=self.get_headers(),
                    timeout=self.timeout
                )
                
                if status_response.status_code != 200:
                    continue
                    
                status_data = status_response.json()
                status = status_data.get("status", "")
                
                pbar.update_absolute(60 + (attempts * 20 // max_attempts))
                
                if status == "complete":
                    init_response = requests.post(
                        f"{baseurl}/suno/uploads/audio/{upload_id}/initialize-clip",
                        headers=self.get_headers(),
                        json={},
                        timeout=self.timeout
                    )
                    
                    if init_response.status_code == 200:
                        init_data = init_response.json()
                        clip_id = init_data.get("clip_id", "")

                        if clip_id:
                            try:
                                clip_detail_response = requests.get(
                                    f"{baseurl}/suno/feed/{clip_id}",
                                    headers=self.get_headers(),
                                    timeout=self.timeout
                                )
                                
                                if clip_detail_response.status_code == 200:
                                    clip_details = clip_detail_response.json()
                                    if isinstance(clip_details, list) and len(clip_details) > 0:
                                        clip_info = clip_details[0]
                                    else:
                                        clip_info = clip_details
                                    
                                    title = clip_info.get("title", "")
                                    tags = clip_info.get("tags", "")
                                    lyrics = clip_info.get("metadata", {}).get("prompt", "") or clip_info.get("prompt", "")
                                    
                            except Exception as e:
                                print(f"Error fetching clip details: {str(e)}")
                        
                        pbar.update_absolute(100)
                        
                        response_info = {
                            "status": "success",
                            "upload_id": upload_id,
                            "clip_id": clip_id,
                            "title": title,
                            "tags": tags,
                            "lyrics": lyrics,
                            "seed": seed if seed > 0 else "auto",
                            "upload_filename": upload_filename
                        }
                        
                        print(f"Audio uploaded successfully. Clip ID: {clip_id}")
                        return (clip_id, title, tags, lyrics, json.dumps(response_info))
                    else:
                        error_message = f"Failed to initialize clip: {init_response.status_code}"
                        print(error_message)
                        return ("", "", "", "", error_message)
                        
                elif status in ["failed", "error"]:
                    error_message = f"Upload failed with status: {status}"
                    print(error_message)
                    return ("", "", "", "", error_message)
            
            error_message = "Upload timeout - status check exceeded maximum attempts"
            print(error_message)
            return ("", "", "", "", error_message)
            
        except Exception as e:
            error_message = f"Error uploading audio: {str(e)}"
            print(error_message)
            return ("", "", "", "", error_message)


class Comfly_suno_upload_extend:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip_id": ("STRING", {"forceInput": True}),
                "prompt": ("STRING", {"multiline": True}),
                "tags": ("STRING", {"default": ""}),
                "title": ("STRING", {"default": ""}),
                "continue_at": ("INT", {"default": 28, "min": 0, "max": 120}),
                "version": (["v3.0", "v3.5", "v4", "v4.5", "v4.5+", "v5"], {"default": "v5"}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
            }
        }
    
    RETURN_TYPES = ("AUDIO", "AUDIO", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio1", "audio2", "audio_url1", "audio_url2", "task_id", "response", "clip_id1", "clip_id2", "duration")
    FUNCTION = "extend_audio"
    CATEGORY = "Comfly-v2/Suno"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def extend_audio(self, clip_id, prompt, tags="", title="", continue_at=28, version="v5", api_key="", seed=0):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        if not self.api_key:
            error_message = "API key not found in Comflyapi.json"
            print(error_message)
            empty_audio = create_audio_object("")
            return (empty_audio, empty_audio, "", "", "", error_message, "", "", "")

        mv_mapping = {
            "v3.0": "chirp-v3.0",
            "v3.5": "chirp-v3.5", 
            "v4": "chirp-v4",
            "v4.5": "chirp-auk",
            "v4.5+": "chirp-bluejay",
            "v5": "chirp-crow"
        }
        
        mv = mv_mapping.get(version, "chirp-crow")
            
        try:
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)

            payload = {
                "continue_at": continue_at,
                "continue_clip_id": clip_id,
                "mv": mv,
                "prompt": prompt,
                "tags": tags,
                "task": "upload_extend",
                "title": title
            }
            
            if seed > 0:
                payload["seed"] = seed

            response = requests.post(
                f"{baseurl}/suno/generate",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            pbar.update_absolute(20)
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                empty_audio = create_audio_object("")
                return (empty_audio, empty_audio, "", "", "", error_message, "", "", "")
                
            result = response.json()
            
            if "id" not in result:
                error_message = "No task ID in response"
                print(error_message)
                empty_audio = create_audio_object("")
                return (empty_audio, empty_audio, "", "", "", error_message, "", "", "")
                
            task_id = result.get("id")
            
            if "clips" not in result or len(result["clips"]) < 2:
                error_message = "Expected at least 2 clips in the response"
                print(error_message)
                empty_audio = create_audio_object("")
                return (empty_audio, empty_audio, "", "", task_id, error_message, "", "", "")
                
            clip_ids = [clip["id"] for clip in result["clips"]]
            
            pbar.update_absolute(30)

            max_attempts = 40
            attempts = 0
            final_clips = []
            
            while attempts < max_attempts and len(final_clips) < 2:
                time.sleep(5)
                attempts += 1
                
                try:
                    clip_response = requests.get(
                        f"{baseurl}/suno/feed/{','.join(clip_ids)}",
                        headers=self.get_headers(),
                        timeout=self.timeout
                    )
                    
                    if clip_response.status_code != 200:
                        continue
                        
                    clips_data = clip_response.json()
                   
                    progress = min(80, 30 + (attempts * 50 // max_attempts))
                    pbar.update_absolute(progress)
                    
                    complete_clips = [
                        clip for clip in clips_data 
                        if clip.get("status") == "complete" and (
                            clip.get("audio_url") or 
                            clip.get("state") == "succeeded"
                        )
                    ]
                    
                    for clip in complete_clips:
                        if clip.get("id") in clip_ids and clip not in final_clips:
                            final_clips.append(clip)
                    
                    if len(final_clips) >= 2:
                        break
                        
                except Exception as e:
                    print(f"Error checking clip status: {str(e)}")
            
            if len(final_clips) < 2:
                error_message = f"Only received {len(final_clips)} complete clips after {max_attempts} attempts"
                print(error_message)
                
                if not final_clips:
                    empty_audio = create_audio_object("")
                    return (empty_audio, empty_audio, "", "", task_id, error_message, "", "", "")

            audio_urls = []
            clip_id_values = []
            durations = []
            
            for clip in final_clips[:2]:
                audio_url = ""
                if "audio_url" in clip and clip["audio_url"]:
                    audio_url = clip["audio_url"]
                    print(f"Found audio URL: {audio_url}")
                elif "cdn1.suno.ai" in str(clip):
                    match = re.search(r'https://cdn1\.suno\.ai/[^"\']+\.mp3', str(clip))
                    if match:
                        audio_url = match.group(0)
                
                audio_urls.append(audio_url if audio_url else "")

                clip_id_value = clip.get("clip_id", clip.get("id", ""))
                clip_id_values.append(clip_id_value)

                duration = clip.get("duration", clip.get("metadata", {}).get("duration", 0))
                durations.append(str(duration))
                
            while len(audio_urls) < 2:
                audio_urls.append("")
                
            while len(clip_id_values) < 2:
                clip_id_values.append("")
                
            while len(durations) < 2:
                durations.append("0")

            audio_objects = [create_audio_object(url) for url in audio_urls[:2]]
            while len(audio_objects) < 2:
                audio_objects.append(create_audio_object(""))
            
            pbar.update_absolute(100)
            
            response_info = {
                "status": "success",
                "original_clip_id": clip_id,
                "continue_at": continue_at,
                "extended_clips": len(final_clips),
                "version": version,
                "title": title,
                "tags": tags
            }

            duration_info = durations[0] if durations[0] != "0" else (durations[1] if len(durations) > 1 else "0")
            
            return (
                audio_objects[0],  
                audio_objects[1],  
                audio_urls[0],     
                audio_urls[1],     
                task_id,
                json.dumps(response_info),
                clip_id_values[0],
                clip_id_values[1],
                duration_info
            )
                
        except Exception as e:
            error_message = f"Error extending audio: {str(e)}"
            print(error_message)
            import traceback
            traceback.print_exc()
            empty_audio = create_audio_object("")
            return (empty_audio, empty_audio, "", "", "", error_message, "", "", "")


class Comfly_suno_cover:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "cover_clip_id": ("STRING", {"forceInput": True}),
                "prompt": ("STRING", {"multiline": True}),
                "title": ("STRING", {"default": ""}),
                "tags": ("STRING", {"default": ""}),
                "version": (["v3.0", "v3.5", "v4", "v4.5", "v4.5+", "v5"], {"default": "v5"}),
                "make_instrumental": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "negative_tags": ("STRING", {"default": ""}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
            }
        }
    
    RETURN_TYPES = ("AUDIO", "AUDIO", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio1", "audio2", "audio_url1", "audio_url2", "task_id", "response", "clip_id1", "clip_id2", "image_url1", "image_url2")
    FUNCTION = "generate_cover"
    CATEGORY = "Comfly-v2/Suno"

    def __init__(self):
        self.api_key = get_config().get('api_key', '')
        self.timeout = 300

    def get_headers(self):
        return {
            "accept": "*/*",
            "Authorization": f"Bearer {self.api_key}",
            "content-type": "application/json"
        }
    
    def generate_cover(self, cover_clip_id, prompt, title="", tags="", version="v5", 
                    make_instrumental=False, api_key="", negative_tags="", seed=0):
        if api_key.strip():
            self.api_key = api_key
            config = get_config()
            config['api_key'] = api_key
            save_config(config)
            
        if not self.api_key:
            error_message = "API key not found in Comflyapi.json"
            print(error_message)
            empty_audio = create_audio_object("")
            return (empty_audio, empty_audio, "", "", "", error_message, "", "", "", "")
        mv_mapping = {
            "v3.0": "chirp-v3.0",
            "v3.5": "chirp-v3.5", 
            "v4": "chirp-v4-tau",
            "v4.5": "chirp-auk",
            "v4.5+": "chirp-bluejay",
            "v5": "chirp-crow"
        }
        
        mv = mv_mapping.get(version, "chirp-v4-tau")
            
        try:
            pbar = comfy.utils.ProgressBar(100)
            pbar.update_absolute(10)
            payload = {
                "prompt": prompt,
                "generation_type": "TEXT",
                "tags": tags,
                "negative_tags": negative_tags,
                "mv": mv,
                "title": title,
                "continue_clip_id": None,
                "continue_at": None,
                "continued_aligned_prompt": None,
                "infill_start_s": None,
                "infill_end_s": None,
                "task": "cover",
                "make_instrumental": make_instrumental,
                "cover_clip_id": cover_clip_id
            }
            
            if seed > 0:
                payload["seed"] = seed
           
            response = requests.post(
                f"{baseurl}/suno/submit/music",
                headers=self.get_headers(),
                json=payload,
                timeout=self.timeout
            )
            
            pbar.update_absolute(30)
            
            if response.status_code != 200:
                error_message = f"API Error: {response.status_code} - {response.text}"
                print(error_message)
                empty_audio = create_audio_object("")
                return (empty_audio, empty_audio, "", "", "", error_message, "", "", "", "")
                
            result = response.json()
            clips = []
            task_id = ""
            
            if isinstance(result, dict):
                if result.get("code") == "success" and "data" in result:
                    task_id = result["data"]
                    if isinstance(task_id, str):
                        clips = self.wait_for_task_completion(task_id, pbar)
                    elif isinstance(task_id, list):
                        clips = task_id
                    elif isinstance(task_id, dict) and "clips" in task_id:
                        clips = task_id["clips"]
                    else:
                        clips = []
                elif "status" in result and result.get("status") == "SUCCESS" and "data" in result:
                    clips = result["data"]
                    task_id = result.get("task_id", "")
                    print(f"Found completed response with {len(clips)} clips")
                    pbar.update_absolute(80)
                elif "clips" in result:
                    clips = result["clips"]
                    task_id = result.get("id", result.get("task_id", ""))
                elif "data" in result and isinstance(result["data"], list):
                    clips = result["data"]
                    task_id = result.get("id", result.get("task_id", ""))
                elif "id" in result:
                    task_id = result["id"]
                    clips = []
                    clips = self.wait_for_task_completion(task_id, pbar)
                else:
                    task_id = str(result)[:50]
                    clips = []
            elif isinstance(result, list):
                clips = result
                task_id = "direct_response"
            else:
                error_message = f"Unexpected response format: {result}"
                print(error_message)
                empty_audio = create_audio_object("")
                return (empty_audio, empty_audio, "", "", "", error_message, "", "", "", "")
            
            if len(clips) == 0:
                error_message = f"No clips found in response. Task ID: {task_id}"
                print(error_message)
                empty_audio = create_audio_object("")
                return (empty_audio, empty_audio, "", "", task_id, error_message, "", "", "", "")
            if len(clips) < 2:
                while len(clips) < 2:
                    clips.append(clips[0] if clips else {})
            audio_urls = []
            clip_id_values = []
            image_urls = []
            
            for i, clip in enumerate(clips[:2]):
               
                audio_url = ""
                if "audio_url" in clip and clip["audio_url"]:
                    audio_url = clip["audio_url"]
                    print(f"Found audio_url: {audio_url}")
                
                audio_urls.append(audio_url)
                
                clip_id_value = clip.get("clip_id", clip.get("id", ""))
                clip_id_values.append(clip_id_value)
                image_url = clip.get("image_url", clip.get("image_large_url", ""))
                image_urls.append(image_url)
            while len(audio_urls) < 2:
                audio_urls.append("")
            while len(clip_id_values) < 2:
                clip_id_values.append("")
            while len(image_urls) < 2:
                image_urls.append("")
            pbar.update_absolute(90)
            audio_objects = [create_audio_object(url) for url in audio_urls[:2]]
            while len(audio_objects) < 2:
                audio_objects.append(create_audio_object(""))
            
            pbar.update_absolute(100)
            
            response_info = {
                "status": "success",
                "cover_clip_id": cover_clip_id,
                "version": version,
                "title": title,
                "tags": tags,
                "make_instrumental": make_instrumental,
                "clips_generated": len(clips),
                "audio_urls": audio_urls,
                "clip_ids": clip_id_values
            }

            return (
                audio_objects[0],  
                audio_objects[1],  
                audio_urls[0],     
                audio_urls[1],     
                task_id,
                json.dumps(response_info),
                clip_id_values[0],
                clip_id_values[1],
                image_urls[0],
                image_urls[1]
            )
                
        except Exception as e:
            error_message = f"Error generating cover: {str(e)}"
            print(error_message)
            import traceback
            traceback.print_exc()
            empty_audio = create_audio_object("")
            return (empty_audio, empty_audio, "", "", "", error_message, "", "", "", "")
        
    def wait_for_task_completion(self, task_id, pbar):
        max_attempts = 50
        attempts = 0
        
        while attempts < max_attempts:
            time.sleep(3)
            attempts += 1
            
            try:
                status_response = requests.get(
                    f"{baseurl}/suno/task/{task_id}",
                    headers=self.get_headers(),
                    timeout=self.timeout
                )
                
                if status_response.status_code == 200:
                    status_result = status_response.json()

                    if status_result.get("status") == "SUCCESS" and "data" in status_result:
                        clips = status_result["data"]
                        if isinstance(clips, list) and len(clips) > 0:
                            return clips
                    elif status_result.get("status") in ["FAILED", "ERROR"]:
                        break

                feed_response = requests.get(
                    f"{baseurl}/suno/feed/{task_id}",
                    headers=self.get_headers(),
                    timeout=self.timeout
                )
                
                if feed_response.status_code == 200:
                    feed_result = feed_response.json()
                    if isinstance(feed_result, list):
                        complete_clips = [
                            clip for clip in feed_result 
                            if clip.get("status") == "complete" and (
                                clip.get("audio_url") or clip.get("state") == "succeeded"
                            )
                        ]
                        if len(complete_clips) >= 1:
                            return complete_clips
                
                progress = min(85, 35 + (attempts * 50 // max_attempts))
                pbar.update_absolute(progress)
                
            except Exception as e:
                print(f"Error checking task status: {str(e)}")
        
        print(f"Task {task_id} did not complete within {max_attempts} attempts")
        return []


class OpenAISoraAPIPlus:
    """
    ComfyUI自定义节点：ai.t8star.cn Sora-2 视频生成（OpenAI兼容流式接口）
    - 参考 openai_chat_api_node.py 的结构与风格
    - 通过 ai.t8star.cn 的 /chat/completions 接口，以 stream=True 获取流式增量内容
    - 适配示例返回：每行均为 JSON，字段为 choices[0].delta.content
    - 超时时间：600 秒（10 分钟）
    输入参数：
      - base_url: 默认 https://ai.t8star.cn/v1
      - model: 默认 sora_video2
      - api_key: 必填
      - system_prompt: 可选，用于设定系统指令
      - user_prompt: 必填，视频生成描述
    输出：
      - reasoning_content: 保留为空（""），与参考节点保持一致
      - answer: 汇总的增量内容（通常包含进度与最终信息）
      - tokens_usage: 由于返回中未提供 usage，这里一般为空字符串
    """
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {"default": "https://ai.t8star.cn/v1", "multiline": False}),
                "model": ("STRING", {"default": "sora_video2", "multiline": False}),
                "api_key": ("STRING", {"default": "", "multiline": False}),
                "user_prompt": ("STRING", {"multiline": True, "default": "请描述要生成的视频内容"}),
            },
            "optional": {
                # 可选图像输入：提供则走“图生视频（image-to-video）”，不提供则为“文生视频（text-to-video）”
                "aspect_ratio": ("STRING", {"default": "16:9", "multiline": False, "options": ["16:9", "9:16"]}),
                "hd": ("BOOLEAN", {"default": True}),
                "duration": ("INT", {"default": 15, "options": [10, 15]}),
            }
        }

    RETURN_TYPES = ("VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "tokens_usage")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen"

    def generate(self, base_url, model, api_key, user_prompt,image=None,hd=True,duration=15,aspect_ratio="16:9"):
        """
        调用 ai.t8star.cn 的 sora-2 模型进行视频生成（流式）。
        请求：
          POST {base_url}/chat/completions
          headers:
            - Authorization: Bearer {api_key}
            - Accept: application/json
            - Content-Type: application/json
          json:
            {
              "model": model,
              "messages": [{"role": "system","content": system_prompt}, {"role":"user","content": user_prompt}],
              "stream": true
            }
        解析：
          - 逐行读取，每行是 JSON，取 choices[0].delta.content 累加
          - 若流式无内容，降级为非流式请求（stream=false）再解析
        超时：
          - timeout=600 秒
        """
        if not api_key:
            return (None, "", "错误：未配置API Key，请在节点参数中设置 api_key")
        if not base_url:
            return (None, "", "错误：未配置 base_url，请在节点参数中设置 base_url")
        if not user_prompt.strip():
            return (None, "", "错误：user_prompt 为空，请提供视频描述")

        try:
            headers = self._build_headers(api_key)
            api_url = f"{base_url.rstrip('/')}/chat/completions"

            # 构建聊天内容：
            # - 若提供 image：按 OpenAI 多模态格式使用 content 数组，携带文本与图片
            # - 若不提供 image：保持纯文本 content 字符串，兼容各类兼容接口
            if image is not None:
                try:
                    from io import BytesIO
                    import base64
                    from PIL import Image as _PILImage  # 仅用于确保PIL可用
                    pil_image = self._convert_to_pil(image)
                    buf = BytesIO()
                    pil_image.save(buf, format="PNG")
                    buf.seek(0)
                    image_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    base64_url = f"data:image/png;base64,{image_base64}"
                    content = [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": base64_url,
                                "detail": "high"
                            }
                        }
                    ]
                    print(f"[OpenAISoraAPI] 图生视频模式: 已附带输入图像，尺寸={pil_image.size}, base64长度={len(image_base64)}")
                except Exception as e:
                    return (None, f"输入图像处理失败: {e}", "")
                messages = [{"role": "user", "content": content}]
            else:
                print(f"[OpenAISoraAPI] 文生视频模式: 纯文本提示词")
                messages = [{"role": "user", "content": user_prompt}]

            payload = {
                "model": model,
                "messages": messages,
                "stream": True
            }

            print(f"[OpenAISoraAPI] 请求: {api_url} (chat/completions, stream=True)")
            print(f"[OpenAISoraAPI] 模型: {model}")
            # 打印裁剪后的提示词，便于用户确认任务内容
            _preview = (user_prompt[:120] + "...") if len(user_prompt) > 120 else user_prompt
            print(f"[OpenAISoraAPI] 提交Sora任务 | 提示词: {_preview}")
            # 打印精简后的载荷（避免输出完整base64）
            try:
                print(f"[OpenAISoraAPI] 请求载荷(精简): {self._safe_json_dumps(payload)}")
            except Exception:
                pass
            resp = requests.post(api_url, headers=headers, json=payload, timeout=600, stream=True)
            print(f"[OpenAISoraAPI] 响应状态码: {resp.status_code}")

            if resp.status_code != 200:
                return (None, f"API错误 (状态码: {resp.status_code}): {resp.text}", "")

            reasoning_content, answer, tokens_usage = self._parse_302_stream(resp)

            # 若流式无内容，降级为非流式
            if not answer:
                try:
                    safe_payload = dict(payload)
                    safe_payload["stream"] = False
                    print(f"[OpenAISoraAPI] 流式无增量，降级为非流式请求")
                    resp2 = requests.post(api_url, headers=headers, json=safe_payload, timeout=600)
                    if resp2.status_code == 200:
                        rc2, answer2, tu2 = self._parse_non_stream(resp2)
                        video_url2 = self._extract_video_url(answer2)
                        video2 = self._download_and_convert_video(video_url2)
                        return (video2, video_url2 or "", tu2)
                    else:
                        return (None, f"非流式降级失败 (状态码: {resp2.status_code}): {resp2.text}", tokens_usage)
                except Exception as _e:
                    print(f"[OpenAISoraAPI] 非流式降级异常: {_e}")

            # 正常流式结果：提取视频URL并下载
            video_url = self._extract_video_url(answer)
            video_output = self._download_and_convert_video(video_url)
            return (video_output, video_url or "", tokens_usage)
        except requests.exceptions.ConnectTimeout as e:
            return (None, f"网络连接超时: 无法连接到API服务器。请检查网络连接或代理。错误: {e}", "")
        except requests.exceptions.Timeout as e:
            return (None, f"请求超时: API响应时间过长。请稍后重试。错误: {e}", "")
        except requests.exceptions.ConnectionError as e:
            return (None, f"网络连接错误: 无法建立到API的连接。请检查网络设置。错误: {e}", "")
        except requests.exceptions.RequestException as e:
            return (None, f"API请求失败: {e}", "")
        except Exception as e:
            return (None, f"处理失败: {e}", "")

    def _build_headers(self, api_key: str):
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _convert_to_pil(self, image):
        """
        将ComfyUI的IMAGE/常见输入转换为PIL Image（RGB）。
        - 支持 torch.Tensor (N,H,W,3) 或 (H,W,3)，数值范围[0,1]或[0,255]
        - 支持PIL Image
        - 支持numpy数组
        """
        try:
            from PIL import Image
            if hasattr(image, "cpu"):  # torch.Tensor
                import torch
                import numpy as np
                t = image
                if t.dim() == 4:
                    t = t[0]
                # 期望 (H,W,3)
                if t.shape[-1] == 3:
                    arr = t.detach().cpu().numpy()
                elif t.shape[0] == 3 and t.dim() == 3:
                    # 兼容 (3,H,W) -> (H,W,3)
                    arr = t.detach().cpu().numpy().transpose(1, 2, 0)
                else:
                    raise ValueError(f"不支持的Tensor形状: {tuple(t.shape)}")
                # 归一化
                if arr.max() <= 1.0:
                    arr = (arr * 255.0).clip(0, 255).astype("uint8")
                else:
                    arr = arr.clip(0, 255).astype("uint8")
                img = Image.fromarray(arr)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                return img
            elif hasattr(image, "save"):  # PIL
                from PIL import Image as _Image
                img = image
                if img.mode != "RGB":
                    img = img.convert("RGB")
                return img
            else:
                import numpy as np
                if isinstance(image, np.ndarray):
                    arr = image
                    if arr.ndim == 3 and arr.shape[0] == 3:
                        arr = arr.transpose(1, 2, 0)
                    if arr.max() <= 1.0:
                        arr = (arr * 255.0).clip(0, 255).astype("uint8")
                    else:
                        arr = arr.clip(0, 255).astype("uint8")
                    from PIL import Image
                    img = Image.fromarray(arr)
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    return img
                raise ValueError(f"不支持的图像类型: {type(image)}")
        except Exception as e:
            print(f"[OpenAISoraAPI] 图像转换失败: {e}")
            raise

    def _safe_json_dumps(self, obj, ensure_ascii=False, indent=2):
        """
        序列化JSON时截断超长/疑似base64字段，避免日志刷屏。
        """
        import json as _json

        def _truncate_base64(value: str):
            if not isinstance(value, str):
                return value
            if len(value) > 100 and (
                value.startswith("data:image/") or
                value[:8] in ("iVBORw0K", "/9j/")  # 常见PNG/JPEG开头
            ):
                return value[:50] + f"... (len={len(value)})"
            return value

        def _walk(v):
            if isinstance(v, dict):
                return {k: _walk(_truncate_base64(val)) for k, val in v.items()}
            if isinstance(v, list):
                return [_walk(_truncate_base64(x)) for x in v]
            return _truncate_base64(v)

        return _json.dumps(_walk(obj), ensure_ascii=ensure_ascii, indent=indent)

    def _parse_302_stream(self, resp):
        """
        解析 ai.t8star.cn 的流式响应。
        示例行：
          {"choices":[{"delta":{"content":"...","role":"assistant"},"index":0}],"id":"...","model":"sora-2","object":"chat.completion.chunk"}
        策略：
          - 逐行解析 JSON
          - 提取 choices[0].delta.content 累加
          - 无 usage 字段，tokens_usage 保持为空
        """
        answer_parts = []
        tokens_usage = ""
        # 进度与心跳跟踪
        last_progress = -1   # 最近一次打印的百分比进度（0-100）
        chunk_count = 0      # 已接收的增量块数量
        printed_url = False  # 是否已打印过URL
        try:
            for raw in resp.iter_lines(decode_unicode=True):
                if raw is None:
                    continue
                line = raw.strip()
                if not line:
                    continue

                # 可能伴随时间戳行，如 "21:56:01"，跳过非 JSON 行
                if not (line.startswith("{") and line.endswith("}")):
                    continue

                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if "choices" in payload and isinstance(payload["choices"], list) and payload["choices"]:
                    delta = payload["choices"][0].get("delta", {})
                    if isinstance(delta, dict):
                        piece = delta.get("content")
                        if isinstance(piece, str) and piece:
                            # 进度日志：尽量识别诸如 "进度 36.."、"41.."、"60.." 等
                            text = piece.strip()
                            # 优先匹配包含“进度”的片段
                            prog_candidates = []
                            if "进度" in text or "progress" in text.lower():
                                prog_candidates = re.findall(r'(\d{1,3})(?=%|\.{2,})', text)
                                if not prog_candidates:
                                    prog_candidates = re.findall(r'进度[^0-9]*?(\d{1,3})', text)
                            else:
                                # 一般性匹配 "41.." 这类
                                prog_candidates = re.findall(r'(\d{1,3})(?=%|\.{2,})', text)

                            # 过滤到 0-100 的最大值作为当前进度
                            curr_prog = None
                            for p in prog_candidates:
                                try:
                                    v = int(p)
                                    if 0 <= v <= 100:
                                        curr_prog = v if (curr_prog is None or v > curr_prog) else curr_prog
                                except Exception:
                                    pass
                            if curr_prog is not None and curr_prog > last_progress:
                                last_progress = curr_prog
                                print(f"[OpenAISoraAPI][{time.strftime('%H:%M:%S')}] 任务进度: {last_progress}%")

                            # 首次发现 URL 则提示
                            if not printed_url and ("http://" in text or "https://" in text):
                                urls = re.findall(r'https?://\S+', text)
                                if urls:
                                    print(f"[OpenAISoraAPI] 可能的视频URL: {urls[0]}")
                                    printed_url = True

                            # 心跳：每收到一定数量块打印一次累计长度
                            chunk_count += 1
                            if chunk_count % 20 == 0:
                                total_len = sum(len(x) for x in answer_parts) + len(text)
                                print(f"[OpenAISoraAPI] 流式接收中... 已接收 {chunk_count} 块，累计字符 {total_len}")

                            answer_parts.append(piece)

            # 合并并做简单的编码清理
            answer = self._normalize_text("".join(answer_parts).strip())
            return ("", answer, tokens_usage)
        except Exception as e:
            return ("", f"流式解析失败: {e}", tokens_usage)

    def _parse_non_stream(self, resp):
        """
        非流式响应解析（兼容 OpenAI chat/completions）
        预期结构：
          {"choices":[{"message":{"role":"assistant","content":"..."},"finish_reason":"..." }], "usage": {...}}
        """
        try:
            if resp.status_code != 200:
                return ("", f"API错误 (状态码: {resp.status_code}): {resp.text}", "")
            if not resp.text.strip():
                return ("", "API返回空响应", "")

            try:
                data = resp.json()
            except json.JSONDecodeError as json_error:
                return ("", f"API响应格式错误: {str(json_error)}", "")

            # 错误字段
            if "error" in data and data["error"]:
                err = data["error"]
                msg = err.get("message", str(err))
                typ = err.get("type", "unknown_error")
                return ("", f"API错误 ({typ}): {msg}", "")

            usage = data.get("usage", {})
            tokens_usage = self._format_tokens_usage(usage)

            if "choices" in data and data["choices"]:
                message = data["choices"][0].get("message", {})
                content = message.get("content", "")
                if not content:
                    finish_reason = data["choices"][0].get("finish_reason", "")
                    return ("", f"未返回内容，finish_reason={finish_reason}", tokens_usage)
                reasoning_content, answer = self._parse_content_tags(content)
                return ("", answer, tokens_usage)

            return ("", "API未返回choices内容", tokens_usage)
        except Exception as e:
            return ("", f"响应解析失败: {e}", "")

    def _parse_content_tags(self, content: str):
        """
        复用与参考节点一致的标签解析逻辑：
        - <think>...</think> 抽取思考
        - <answer>...</answer> 抽取答案
        - <reasoning>...</reasoning> 抽取思考
        """
        try:
            think_pattern = r'<think>(.*?)</think>'
            think_match = re.search(think_pattern, content, re.DOTALL)
            if think_match:
                reasoning_content = think_match.group(1).strip()
                answer = content.replace(think_match.group(0), "").strip()
                return (reasoning_content, answer)

            answer_pattern = r'<answer>(.*?)</answer>'
            answer_match = re.search(answer_pattern, content, re.DOTALL)
            if answer_match:
                return ("", answer_match.group(1).strip())

            answer_pattern_open = r'<answer>(.*)'
            answer_match_open = re.search(answer_pattern_open, content, re.DOTALL)
            if answer_match_open:
                return ("", answer_match_open.group(1).strip())

            reasoning_pattern = r'<reasoning>(.*?)</reasoning>'
            reasoning_match = re.search(reasoning_pattern, content, re.DOTALL)
            if reasoning_match:
                reasoning_content = reasoning_match.group(1).strip()
                answer = content.replace(reasoning_match.group(0), "").strip()
                return (reasoning_content, answer)

            return ("", content.strip())
        except Exception:
            return ("", content.strip())

    def _format_tokens_usage(self, usage):
        if not usage:
            return ""
        total_tokens = usage.get('total_tokens') or usage.get('total') or usage.get('tokens') or '-'
        prompt_tokens = (
            usage.get('prompt_tokens')
            or usage.get('input_tokens')
            or (usage.get('input', {}) if isinstance(usage.get('input'), dict) else None)
            or usage.get('prompt')
            or '-'
        )
        if isinstance(prompt_tokens, dict):
            prompt_tokens = prompt_tokens.get('tokens') or prompt_tokens.get('count') or '-'
        completion_tokens = (
            usage.get('completion_tokens')
            or usage.get('output_tokens')
            or (usage.get('output', {}) if isinstance(usage.get('output'), dict) else None)
            or usage.get('completion')
            or '-'
        )
        if isinstance(completion_tokens, dict):
            completion_tokens = completion_tokens.get('tokens') or completion_tokens.get('count') or '-'
        return f"total_tokens={total_tokens}, input_tokens={prompt_tokens}, output_tokens={completion_tokens}"

    def _normalize_text(self, s: str) -> str:
        if not isinstance(s, str) or not s:
            return s or ""
        sample = s[:8]
        suspicious = ("Ã", "å", "æ", "ç", "ð", "þ")
        if any(ch in sample for ch in suspicious):
            try:
                return s.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
            except Exception:
                return s
        return s

    def _extract_video_url(self, text: str) -> Optional[str]:
        """
        从返回文本中提取视频URL。
        优先匹配指向 mp4/webm 等视频资源的URL；若未匹配到，则回退匹配任意 http/https 链接。
        """
        if not isinstance(text, str) or not text:
            return None
        try:
            # 优先匹配视频直链
            m = re.findall(r'(https?://[^\s)>\]]+\.(?:mp4|webm)(?:\?[^\s)>\]]*)?)', text, flags=re.IGNORECASE)
            if m:
                return m[0]
            # 其次匹配 markdown 的 [在线播放](url) 格式
            m2 = re.findall(r'\((https?://[^\s)]+)\)', text, flags=re.IGNORECASE)
            if m2:
                return m2[0]
            # 再次匹配任意 http/https 链接
            m3 = re.findall(r'(https?://[^\s)>\]]+)', text, flags=re.IGNORECASE)
            if m3:
                return m3[0]
            return None
        except Exception:
            return None

    def _download_and_convert_video(self, video_url: str) -> Optional[Any]:
        """
        下载视频URL并转换为VIDEO对象，参考 jimeng_video_node.py 的实现。
        - 校验URL合法性
        - 使用 download_url_to_video_output(video_url, timeout=120)
        - 出错返回 None，保证节点稳定
        """
        try:
            if not video_url or not isinstance(video_url, str):
                print(f"[OpenAISoraAPI] 无效的视频URL: {video_url}")
                return None
            if not video_url.startswith(("http://", "https://")):
                print(f"[OpenAISoraAPI] 不支持的URL格式: {video_url}")
                return None

            print(f"[OpenAISoraAPI] 🎬 开始下载视频: {video_url[:80]}...")
            try:
                video_output = download_url_to_video_output(video_url, timeout=120)
                print(f"[OpenAISoraAPI] ✅ 视频下载完成")
                return video_output
            except Exception as download_error:
                print(f"[OpenAISoraAPI] ❌ 视频下载失败: {download_error}")
                return None
        except Exception as e:
            print(f"[OpenAISoraAPI] 视频下载转换过程出错: {e}")
            return None


class OpenAISoraAPI:
    """
    ComfyUI自定义节点：ai.t8star.cn Sora-2 视频生成（OpenAI兼容流式接口）
    - 参考 openai_chat_api_node.py 的结构与风格
    - 通过 ai.t8star.cn 的 /chat/completions 接口，以 stream=True 获取流式增量内容
    - 适配示例返回：每行均为 JSON，字段为 choices[0].delta.content
    - 超时时间：600 秒（10 分钟）
    输入参数：
      - base_url: 默认 https://ai.t8star.cn/v1
      - model: 默认 sora_video2
      - api_key: 必填
      - system_prompt: 可选，用于设定系统指令
      - user_prompt: 必填，视频生成描述
    输出：
      - reasoning_content: 保留为空（""），与参考节点保持一致
      - answer: 汇总的增量内容（通常包含进度与最终信息）
      - tokens_usage: 由于返回中未提供 usage，这里一般为空字符串
    """
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {"default": "https://ai.t8star.cn/v1", "multiline": False}),
                "model": ("STRING", {"default": "sora_video2", "multiline": False}),
                "api_key": ("STRING", {"default": "", "multiline": False}),
                "user_prompt": ("STRING", {"multiline": True, "default": "请描述要生成的视频内容"}),
                #"hd": (["true", "false"], {"default": "false"}),
                #"duration": (["10", "15"], {"default": "15"}),
                #"aspect_ratio": (["16:9", "9:16"], {"default": "9:16"}),
            },
            "optional": {
                # 可选图像输入：提供则走“图生视频（image-to-video）”，不提供则为“文生视频（text-to-video）”
                "image": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "tokens_usage")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen"

    def generate(self, base_url, model, api_key, user_prompt, image=None):
        """
        调用 ai.t8star.cn 的 sora-2 模型进行视频生成（流式）。
        请求：
          POST {base_url}/chat/completions
          headers:
            - Authorization: Bearer {api_key}
            - Accept: application/json
            - Content-Type: application/json
          json:
            {
              "model": model,
              "messages": [{"role": "system","content": system_prompt}, {"role":"user","content": user_prompt}],
              "stream": true
            }
        解析：
          - 逐行读取，每行是 JSON，取 choices[0].delta.content 累加
          - 若流式无内容，降级为非流式请求（stream=false）再解析
        超时：
          - timeout=600 秒
        """
        if not api_key:
            return (None, "", "错误：未配置API Key，请在节点参数中设置 api_key")
        if not base_url:
            return (None, "", "错误：未配置 base_url，请在节点参数中设置 base_url")
        if not user_prompt.strip():
            return (None, "", "错误：user_prompt 为空，请提供视频描述")

        try:
            headers = self._build_headers(api_key)
            api_url = f"{base_url.rstrip('/')}/chat/completions"

            # 构建聊天内容：
            # - 若提供 image：按 OpenAI 多模态格式使用 content 数组，携带文本与图片
            # - 若不提供 image：保持纯文本 content 字符串，兼容各类兼容接口
            if image is not None:
                try:
                    from io import BytesIO
                    import base64
                    from PIL import Image as _PILImage  # 仅用于确保PIL可用
                    pil_image = self._convert_to_pil(image)
                    buf = BytesIO()
                    pil_image.save(buf, format="PNG")
                    buf.seek(0)
                    image_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    base64_url = f"data:image/png;base64,{image_base64}"
                    content = [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": base64_url,
                                "detail": "high"
                            }
                        }
                    ]
                    print(f"[OpenAISoraAPI] 图生视频模式: 已附带输入图像，尺寸={pil_image.size}, base64长度={len(image_base64)}")
                except Exception as e:
                    return (None, f"输入图像处理失败: {e}", "")
                messages = [{"role": "user", "content": content}]
            else:
                print(f"[OpenAISoraAPI] 文生视频模式: 纯文本提示词")
                messages = [{"role": "user", "content": user_prompt}]

            payload = {
                "model": model,
                "messages": messages,
                "stream": True
            }

            print(f"[OpenAISoraAPI] 请求: {api_url} (chat/completions, stream=True)")
            print(f"[OpenAISoraAPI] 模型: {model}")
            # 打印裁剪后的提示词，便于用户确认任务内容
            _preview = (user_prompt[:120] + "...") if len(user_prompt) > 120 else user_prompt
            print(f"[OpenAISoraAPI] 提交Sora任务 | 提示词: {_preview}")
            # 打印精简后的载荷（避免输出完整base64）
            try:
                print(f"[OpenAISoraAPI] 请求载荷(精简): {self._safe_json_dumps(payload)}")
            except Exception:
                pass
            resp = requests.post(api_url, headers=headers, json=payload, timeout=600, stream=True)
            print(f"[OpenAISoraAPI] 响应状态码: {resp.status_code}")

            if resp.status_code != 200:
                return (None, f"API错误 (状态码: {resp.status_code}): {resp.text}", "")

            reasoning_content, answer, tokens_usage = self._parse_302_stream(resp)

            # 若流式无内容，降级为非流式
            if not answer:
                try:
                    safe_payload = dict(payload)
                    safe_payload["stream"] = False
                    print(f"[OpenAISoraAPI] 流式无增量，降级为非流式请求")
                    resp2 = requests.post(api_url, headers=headers, json=safe_payload, timeout=600)
                    if resp2.status_code == 200:
                        rc2, answer2, tu2 = self._parse_non_stream(resp2)
                        video_url2 = self._extract_video_url(answer2)
                        video2 = self._download_and_convert_video(video_url2)
                        return (video2, video_url2 or "", tu2)
                    else:
                        return (None, f"非流式降级失败 (状态码: {resp2.status_code}): {resp2.text}", tokens_usage)
                except Exception as _e:
                    print(f"[OpenAISoraAPI] 非流式降级异常: {_e}")

            # 正常流式结果：提取视频URL并下载
            video_url = self._extract_video_url(answer)
            video_output = self._download_and_convert_video(video_url)
            return (video_output, video_url or "", tokens_usage)
        except requests.exceptions.ConnectTimeout as e:
            return (None, f"网络连接超时: 无法连接到API服务器。请检查网络连接或代理。错误: {e}", "")
        except requests.exceptions.Timeout as e:
            return (None, f"请求超时: API响应时间过长。请稍后重试。错误: {e}", "")
        except requests.exceptions.ConnectionError as e:
            return (None, f"网络连接错误: 无法建立到API的连接。请检查网络设置。错误: {e}", "")
        except requests.exceptions.RequestException as e:
            return (None, f"API请求失败: {e}", "")
        except Exception as e:
            return (None, f"处理失败: {e}", "")

    def _build_headers(self, api_key: str):
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _convert_to_pil(self, image):
        """
        将ComfyUI的IMAGE/常见输入转换为PIL Image（RGB）。
        - 支持 torch.Tensor (N,H,W,3) 或 (H,W,3)，数值范围[0,1]或[0,255]
        - 支持PIL Image
        - 支持numpy数组
        """
        try:
            from PIL import Image
            if hasattr(image, "cpu"):  # torch.Tensor
                import torch
                import numpy as np
                t = image
                if t.dim() == 4:
                    t = t[0]
                # 期望 (H,W,3)
                if t.shape[-1] == 3:
                    arr = t.detach().cpu().numpy()
                elif t.shape[0] == 3 and t.dim() == 3:
                    # 兼容 (3,H,W) -> (H,W,3)
                    arr = t.detach().cpu().numpy().transpose(1, 2, 0)
                else:
                    raise ValueError(f"不支持的Tensor形状: {tuple(t.shape)}")
                # 归一化
                if arr.max() <= 1.0:
                    arr = (arr * 255.0).clip(0, 255).astype("uint8")
                else:
                    arr = arr.clip(0, 255).astype("uint8")
                img = Image.fromarray(arr)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                return img
            elif hasattr(image, "save"):  # PIL
                from PIL import Image as _Image
                img = image
                if img.mode != "RGB":
                    img = img.convert("RGB")
                return img
            else:
                import numpy as np
                if isinstance(image, np.ndarray):
                    arr = image
                    if arr.ndim == 3 and arr.shape[0] == 3:
                        arr = arr.transpose(1, 2, 0)
                    if arr.max() <= 1.0:
                        arr = (arr * 255.0).clip(0, 255).astype("uint8")
                    else:
                        arr = arr.clip(0, 255).astype("uint8")
                    from PIL import Image
                    img = Image.fromarray(arr)
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    return img
                raise ValueError(f"不支持的图像类型: {type(image)}")
        except Exception as e:
            print(f"[OpenAISoraAPI] 图像转换失败: {e}")
            raise

    def _safe_json_dumps(self, obj, ensure_ascii=False, indent=2):
        """
        序列化JSON时截断超长/疑似base64字段，避免日志刷屏。
        """
        import json as _json

        def _truncate_base64(value: str):
            if not isinstance(value, str):
                return value
            if len(value) > 100 and (
                value.startswith("data:image/") or
                value[:8] in ("iVBORw0K", "/9j/")  # 常见PNG/JPEG开头
            ):
                return value[:50] + f"... (len={len(value)})"
            return value

        def _walk(v):
            if isinstance(v, dict):
                return {k: _walk(_truncate_base64(val)) for k, val in v.items()}
            if isinstance(v, list):
                return [_walk(_truncate_base64(x)) for x in v]
            return _truncate_base64(v)

        return _json.dumps(_walk(obj), ensure_ascii=ensure_ascii, indent=indent)

    def _parse_302_stream(self, resp):
        """
        解析 ai.t8star.cn 的流式响应。
        示例行：
          {"choices":[{"delta":{"content":"...","role":"assistant"},"index":0}],"id":"...","model":"sora-2","object":"chat.completion.chunk"}
        策略：
          - 逐行解析 JSON
          - 提取 choices[0].delta.content 累加
          - 无 usage 字段，tokens_usage 保持为空
        """
        answer_parts = []
        tokens_usage = ""
        # 进度与心跳跟踪
        last_progress = -1   # 最近一次打印的百分比进度（0-100）
        chunk_count = 0      # 已接收的增量块数量
        printed_url = False  # 是否已打印过URL
        try:
            for raw in resp.iter_lines(decode_unicode=True):
                if raw is None:
                    continue
                line = raw.strip()
                if not line:
                    continue

                # 可能伴随时间戳行，如 "21:56:01"，跳过非 JSON 行
                if not (line.startswith("{") and line.endswith("}")):
                    continue

                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if "choices" in payload and isinstance(payload["choices"], list) and payload["choices"]:
                    delta = payload["choices"][0].get("delta", {})
                    if isinstance(delta, dict):
                        piece = delta.get("content")
                        if isinstance(piece, str) and piece:
                            # 进度日志：尽量识别诸如 "进度 36.."、"41.."、"60.." 等
                            text = piece.strip()
                            # 优先匹配包含“进度”的片段
                            prog_candidates = []
                            if "进度" in text or "progress" in text.lower():
                                prog_candidates = re.findall(r'(\d{1,3})(?=%|\.{2,})', text)
                                if not prog_candidates:
                                    prog_candidates = re.findall(r'进度[^0-9]*?(\d{1,3})', text)
                            else:
                                # 一般性匹配 "41.." 这类
                                prog_candidates = re.findall(r'(\d{1,3})(?=%|\.{2,})', text)

                            # 过滤到 0-100 的最大值作为当前进度
                            curr_prog = None
                            for p in prog_candidates:
                                try:
                                    v = int(p)
                                    if 0 <= v <= 100:
                                        curr_prog = v if (curr_prog is None or v > curr_prog) else curr_prog
                                except Exception:
                                    pass
                            if curr_prog is not None and curr_prog > last_progress:
                                last_progress = curr_prog
                                print(f"[OpenAISoraAPI][{time.strftime('%H:%M:%S')}] 任务进度: {last_progress}%")

                            # 首次发现 URL 则提示
                            if not printed_url and ("http://" in text or "https://" in text):
                                urls = re.findall(r'https?://\S+', text)
                                if urls:
                                    print(f"[OpenAISoraAPI] 可能的视频URL: {urls[0]}")
                                    printed_url = True

                            # 心跳：每收到一定数量块打印一次累计长度
                            chunk_count += 1
                            if chunk_count % 20 == 0:
                                total_len = sum(len(x) for x in answer_parts) + len(text)
                                print(f"[OpenAISoraAPI] 流式接收中... 已接收 {chunk_count} 块，累计字符 {total_len}")

                            answer_parts.append(piece)

            # 合并并做简单的编码清理
            answer = self._normalize_text("".join(answer_parts).strip())
            return ("", answer, tokens_usage)
        except Exception as e:
            return ("", f"流式解析失败: {e}", tokens_usage)

    def _parse_non_stream(self, resp):
        """
        非流式响应解析（兼容 OpenAI chat/completions）
        预期结构：
          {"choices":[{"message":{"role":"assistant","content":"..."},"finish_reason":"..." }], "usage": {...}}
        """
        try:
            if resp.status_code != 200:
                return ("", f"API错误 (状态码: {resp.status_code}): {resp.text}", "")
            if not resp.text.strip():
                return ("", "API返回空响应", "")

            try:
                data = resp.json()
            except json.JSONDecodeError as json_error:
                return ("", f"API响应格式错误: {str(json_error)}", "")

            # 错误字段
            if "error" in data and data["error"]:
                err = data["error"]
                msg = err.get("message", str(err))
                typ = err.get("type", "unknown_error")
                return ("", f"API错误 ({typ}): {msg}", "")

            usage = data.get("usage", {})
            tokens_usage = self._format_tokens_usage(usage)

            if "choices" in data and data["choices"]:
                message = data["choices"][0].get("message", {})
                content = message.get("content", "")
                if not content:
                    finish_reason = data["choices"][0].get("finish_reason", "")
                    return ("", f"未返回内容，finish_reason={finish_reason}", tokens_usage)
                reasoning_content, answer = self._parse_content_tags(content)
                return ("", answer, tokens_usage)

            return ("", "API未返回choices内容", tokens_usage)
        except Exception as e:
            return ("", f"响应解析失败: {e}", "")

    def _parse_content_tags(self, content: str):
        """
        复用与参考节点一致的标签解析逻辑：
        - <think>...</think> 抽取思考
        - <answer>...</answer> 抽取答案
        - <reasoning>...</reasoning> 抽取思考
        """
        try:
            think_pattern = r'<think>(.*?)</think>'
            think_match = re.search(think_pattern, content, re.DOTALL)
            if think_match:
                reasoning_content = think_match.group(1).strip()
                answer = content.replace(think_match.group(0), "").strip()
                return (reasoning_content, answer)

            answer_pattern = r'<answer>(.*?)</answer>'
            answer_match = re.search(answer_pattern, content, re.DOTALL)
            if answer_match:
                return ("", answer_match.group(1).strip())

            answer_pattern_open = r'<answer>(.*)'
            answer_match_open = re.search(answer_pattern_open, content, re.DOTALL)
            if answer_match_open:
                return ("", answer_match_open.group(1).strip())

            reasoning_pattern = r'<reasoning>(.*?)</reasoning>'
            reasoning_match = re.search(reasoning_pattern, content, re.DOTALL)
            if reasoning_match:
                reasoning_content = reasoning_match.group(1).strip()
                answer = content.replace(reasoning_match.group(0), "").strip()
                return (reasoning_content, answer)

            return ("", content.strip())
        except Exception:
            return ("", content.strip())

    def _format_tokens_usage(self, usage):
        if not usage:
            return ""
        total_tokens = usage.get('total_tokens') or usage.get('total') or usage.get('tokens') or '-'
        prompt_tokens = (
            usage.get('prompt_tokens')
            or usage.get('input_tokens')
            or (usage.get('input', {}) if isinstance(usage.get('input'), dict) else None)
            or usage.get('prompt')
            or '-'
        )
        if isinstance(prompt_tokens, dict):
            prompt_tokens = prompt_tokens.get('tokens') or prompt_tokens.get('count') or '-'
        completion_tokens = (
            usage.get('completion_tokens')
            or usage.get('output_tokens')
            or (usage.get('output', {}) if isinstance(usage.get('output'), dict) else None)
            or usage.get('completion')
            or '-'
        )
        if isinstance(completion_tokens, dict):
            completion_tokens = completion_tokens.get('tokens') or completion_tokens.get('count') or '-'
        return f"total_tokens={total_tokens}, input_tokens={prompt_tokens}, output_tokens={completion_tokens}"

    def _normalize_text(self, s: str) -> str:
        if not isinstance(s, str) or not s:
            return s or ""
        sample = s[:8]
        suspicious = ("Ã", "å", "æ", "ç", "ð", "þ")
        if any(ch in sample for ch in suspicious):
            try:
                return s.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
            except Exception:
                return s
        return s

    def _extract_video_url(self, text: str) -> Optional[str]:
        """
        从返回文本中提取视频URL。
        优先匹配指向 mp4/webm 等视频资源的URL；若未匹配到，则回退匹配任意 http/https 链接。
        """
        if not isinstance(text, str) or not text:
            return None
        try:
            # 优先匹配视频直链
            m = re.findall(r'(https?://[^\s)>\]]+\.(?:mp4|webm)(?:\?[^\s)>\]]*)?)', text, flags=re.IGNORECASE)
            if m:
                return m[0]
            # 其次匹配 markdown 的 [在线播放](url) 格式
            m2 = re.findall(r'\((https?://[^\s)]+)\)', text, flags=re.IGNORECASE)
            if m2:
                return m2[0]
            # 再次匹配任意 http/https 链接
            m3 = re.findall(r'(https?://[^\s)>\]]+)', text, flags=re.IGNORECASE)
            if m3:
                return m3[0]
            return None
        except Exception:
            return None

    def _download_and_convert_video(self, video_url: str) -> Optional[Any]:
        """
        下载视频URL并转换为VIDEO对象，参考 jimeng_video_node.py 的实现。
        - 校验URL合法性
        - 使用 download_url_to_video_output(video_url, timeout=120)
        - 出错返回 None，保证节点稳定
        """
        try:
            if not video_url or not isinstance(video_url, str):
                print(f"[OpenAISoraAPI] 无效的视频URL: {video_url}")
                return None
            if not video_url.startswith(("http://", "https://")):
                print(f"[OpenAISoraAPI] 不支持的URL格式: {video_url}")
                return None

            print(f"[OpenAISoraAPI] 🎬 开始下载视频: {video_url[:80]}...")
            try:
                video_output = download_url_to_video_output(video_url, timeout=120)
                print(f"[OpenAISoraAPI] ✅ 视频下载完成")
                return video_output
            except Exception as download_error:
                print(f"[OpenAISoraAPI] ❌ 视频下载失败: {download_error}")
                return None
        except Exception as e:
            print(f"[OpenAISoraAPI] 视频下载转换过程出错: {e}")
            return None



WEB_DIRECTORY = "./web"    
        
NODE_CLASS_MAPPINGS = {
    "Comfly_api_set": Comfly_api_set,
    "OpenAI_Sora_API_Plus": OpenAISoraAPIPlus,    
    "OpenAI_Sora_API": OpenAISoraAPI,
    "Comfly_Mj": Comfly_Mj,
    "Comfly_mjstyle": Comfly_mjstyle,
    "Comfly_upload": Comfly_upload,
    "Comfly_Mju": Comfly_Mju,
    "Comfly_Mjv": Comfly_Mjv,  
    "Comfly_Mj_swap_face": Comfly_Mj_swap_face,
    "Comfly_kling_text2video": Comfly_kling_text2video,
    "Comfly_kling_image2video": Comfly_kling_image2video,
    "Comfly_kling_multi_image2video": Comfly_kling_multi_image2video,
    "Comfly_video_extend": Comfly_video_extend,
    "Comfly_lip_sync": Comfly_lip_sync,
    "ComflyGeminiAPI": ComflyGeminiAPI,
    "ComflySeededit": ComflySeededit,
    "ComflyChatGPTApi": ComflyChatGPTApi,
    "Comfly_sora2_openai": Comfly_sora2_openai, 
    "Comfly_sora2": Comfly_sora2, 
    "Comfly_sora2_chat": Comfly_sora2_chat,  
    "ComflyJimengApi": ComflyJimengApi, 
    "Comfly_gpt_image_1_edit": Comfly_gpt_image_1_edit,
    "Comfly_gpt_image_1": Comfly_gpt_image_1,
    "ComflyJimengVideoApi": ComflyJimengVideoApi,
    "Comfly_Flux_Kontext": Comfly_Flux_Kontext,
    "Comfly_Flux_Kontext_Edit": Comfly_Flux_Kontext_Edit,
    "Comfly_Flux_Kontext_bfl": Comfly_Flux_Kontext_bfl,
    "Comfly_Googel_Veo3": Comfly_Googel_Veo3,
    "Comfly_mj_video": Comfly_mj_video,
    "Comfly_mj_video_extend": Comfly_mj_video_extend,
    "Comfly_qwen_image": Comfly_qwen_image,
    "Comfly_qwen_image_edit": Comfly_qwen_image_edit, 
    "Comfly_Doubao_Seedream": Comfly_Doubao_Seedream,
    "Comfly_Doubao_Seedream_4": Comfly_Doubao_Seedream_4,
    "Comfly_Doubao_Seededit": Comfly_Doubao_Seededit,
    "Comfly_MiniMax_video": Comfly_MiniMax_video,
    "Comfly_suno_description": Comfly_suno_description,
    "Comfly_suno_lyrics": Comfly_suno_lyrics,
    "Comfly_suno_custom": Comfly_suno_custom,
    "Comfly_suno_upload": Comfly_suno_upload,
    "Comfly_suno_upload_extend": Comfly_suno_upload_extend,
    "Comfly_suno_cover": Comfly_suno_cover,
    "Comfly_nano_banana": Comfly_nano_banana,
    "Comfly_nano_banana_fal": Comfly_nano_banana_fal,
    "Comfly_nano_banana_edit": Comfly_nano_banana_edit
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Comfly_api_set": "Comfly API Settings",
    "OpenAI_Sora_API_Plus": "OpenAI Sora API Plus节点",
    "OpenAI_Sora_API": "OpenAI Sora API节点",
    "Comfly_Mj": "Comfly_Mj", 
    "Comfly_mjstyle": "Comfly_mjstyle",
    "Comfly_upload": "Comfly_upload",
    "Comfly_Mju": "Comfly_Mju",
    "Comfly_Mjv": "Comfly_Mjv",  
    "Comfly_Mj_swap_face": "Comfly MJ Face Swap",
    "Comfly_kling_text2video": "Comfly_kling_text2video",
    "Comfly_kling_image2video": "Comfly_kling_image2video",
    "Comfly_kling_multi_image2video": "Comfly_kling_multi_image2video",
    "Comfly_video_extend": "Comfly_video_extend",
    "Comfly_lip_sync": "Comfly_lip_sync",
    "ComflyGeminiAPI": "Comfly Gemini API",
    "ComflySeededit": "Comfly Doubao SeedEdit2.0",
    "ComflyChatGPTApi": "Comfly ChatGPT Api",
    "Comfly_sora2_openai": "Comfly_sora2_openai", 
    "Comfly_sora2": "Comfly_sora2", 
    "Comfly_sora2_chat": "Comfly_sora2_chat", 
    "ComflyJimengApi": "Comfly Jimeng API", 
    "Comfly_gpt_image_1_edit": "Comfly_gpt_image_1_edit",
    "Comfly_gpt_image_1": "Comfly_gpt_image_1", 
    "ComflyJimengVideoApi": "Comfly Jimeng Video API",
    "Comfly_Flux_Kontext": "Comfly_Flux_Kontext",
    "Comfly_Flux_Kontext_Edit": "Comfly_Flux_Kontext_Edit",
    "Comfly_Flux_Kontext_bfl": "Comfly_Flux_Kontext_bfl",
    "Comfly_Googel_Veo3": "Comfly Google Veo3",
    "Comfly_mj_video": "Comfly MJ Video",
    "Comfly_mj_video_extend": "Comfly MJ Video Extend",
    "Comfly_qwen_image": "Comfly_qwen_image",
    "Comfly_qwen_image_edit": "Comfly_qwen_image_edit",
    "Comfly_Doubao_Seedream": "Comfly Doubao Seedream3.0",
    "Comfly_Doubao_Seedream_4": "Comfly Doubao Seedream4.0",
    "Comfly_Doubao_Seededit": "Comfly Doubao Seededit3.0",
    "Comfly_MiniMax_video": "Comfly MiniMax Hailuo Video",
    "Comfly_suno_description": "Comfly Suno Description",
    "Comfly_suno_lyrics": "Comfly Suno Lyrics",
    "Comfly_suno_custom": "Comfly Suno Custom",
    "Comfly_suno_upload": "Comfly Suno Upload",
    "Comfly_suno_upload_extend": "Comfly Suno Upload Extend", 
    "Comfly_suno_cover": "Comfly Suno Cover",
    "Comfly_nano_banana": "Comfly_nano_banana",
    "Comfly_nano_banana_fal": "Comfly_nano_banana_fal",
    "Comfly_nano_banana_edit": "Comfly_nano_banana_edit"
}