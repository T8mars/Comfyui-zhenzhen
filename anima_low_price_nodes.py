"""Anima v1 text-to-image on the Low Price channel."""

from . import seedance_low_price_nodes as api
from .nov21_contracts import choice, text
from .nov21_low_price_nodes import OPTIONS, PROMPT, _LowPriceNode, combo, result

KEY = "T8Zhenzhen_Anima_V1_T2I_LowPrice"
MODEL = "Anima-v1-t2i"
RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"]


class T8ZhenzhenAnimaV1(_LowPriceNode):
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": PROMPT, "ratio": combo(RATIOS)}, "optional": OPTIONS.copy()}

    @staticmethod
    def plan(values, strict=False):
        prompt = text(values, "prompt", required=strict).strip()
        return {"model": MODEL, "prompt": prompt, "metadata": {"ratio": choice(values, "ratio", RATIOS)}}

    def prepare(self, values):
        return self.plan(values, strict=True)

    def run(self, body, config, progress):
        task, _ = api.submit_image_task(body, config, retry_server_errors=False)
        progress(20)
        final = api.poll_image_task(task, config, on_progress=lambda value: progress(20 + value * .75))
        urls = api.extract_image_urls(final)
        if len(urls) != 1:
            raise api.SeedanceLowPriceError(f"Anima expected one image, got {len(urls)}")
        image = api.download_image(urls[0])
        progress(100)
        return result((image, urls[0]), task, final, urls)

    def error_result(self, message):
        return result((api.torch.zeros((1, 64, 64, 3)), ""), "", {"error": message}, [message])
