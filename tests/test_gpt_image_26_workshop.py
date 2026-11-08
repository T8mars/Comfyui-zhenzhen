import base64
import io
import json
from pathlib import Path
import re
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import torch

from nov08_fixture import module

nodes = module("gpt_image_26_workshop_nodes")
IMAGE = torch.zeros(1, 32, 32, 3)
URL = "https://example.test/image.png"
KEY = "test-key"
NODE_KEY = "T8Zhenzhen_GPT_Image_2_6_Workshop"


def response(body, status=200):
    result = Mock(status_code=status)
    result.json.return_value = body
    return result


def encoded(alpha=255, color="red"):
    image = Image.new("RGBA", (16, 16), color)
    image.putalpha(alpha)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode()


class ContractTests(unittest.TestCase):
    def test_exact_models_and_static_schema(self):
        self.assertEqual(nodes.MODELS, tuple(f"gpt-image-2.6-{variant}{suffix}" for variant in ("flare", "sunburst") for suffix in ("", "-2k", "-4k")))
        schema = nodes.T8ZhenzhenGPTImage26Workshop.INPUT_TYPES()
        self.assertEqual(schema["optional"]["output_format"][0], ["png", "jpeg", "webp"])
        self.assertFalse(set(schema["optional"]) & {"frame_count", "frame_duration_ms", "svg", "input_fidelity"})
        self.assertFalse(schema["optional"]["skip_error"][1]["default"])
        self.assertTrue(schema["optional"]["seed"][1]["control_after_generate"])

    def test_payload_whitelist_and_optional_fields(self):
        for model in nodes.MODELS:
            data = nodes.payload({"model": model, "prompt": " Product ", "seed": 42, "frame_count": 9, "input_fidelity": "high"})
            self.assertEqual(data, {"model": model, "prompt": "Product", "quality": "auto", "size": "1024x1024", "n": 1,
                "background": "auto", "moderation": "auto", "output_format": "png"})
        for output in ("png", "jpeg", "webp"):
            data = nodes.payload({"prompt": "Product", "output_format": output, "output_compression": 80, "complexity": "low"})
            self.assertEqual("output_compression" in data, output != "png")
            self.assertEqual(data["complexity"], "low")

    def test_sizes_and_boundaries(self):
        for size in nodes.SIZES:
            if size != "custom":
                self.assertEqual(nodes.resolved_size({"size": size}, True), size)
        self.assertEqual(nodes.resolved_size({"size": "custom", "custom_width": 1536, "custom_height": 864}, True), "1536x864")
        self.assertIsNone(nodes.resolved_size({"size": "custom", "custom_width": 3840}))
        for width, height in ((512, 512), (3841, 2160), (3840, 3840), (3840, 256), (True, 1024), (1025, 1024)):
            with self.assertRaises(nodes.GPTImage26Error):
                nodes.resolved_size({"size": "custom", "custom_width": width, "custom_height": height}, True)

    def test_invalid_enums_numbers_prompt_and_gif(self):
        for values in ({"model": "gpt-image-2.5-flare"}, {"prompt": " "}, {"prompt": 42}, {"prompt": "x" * 32001},
            {"quality": "hd"}, {"complexity": "bad"}, {"background": "transparent", "output_format": "jpeg"},
            {"output_format": "gif"}, {"output_format": "svg"}, {"n": 0}, {"n": 11}, {"n": True},
            {"output_compression": 101}, {"poll_interval": 1}, {"max_poll_time": 1}, {"async_mode": "true"}):
            with self.assertRaises(nodes.GPTImage26Error):
                nodes.validate(values)

    def test_linked_prompt_and_custom_dimensions_deferred(self):
        cls = nodes.T8ZhenzhenGPTImage26Workshop
        self.assertIs(cls.VALIDATE_INPUTS(prompt=None), True)
        self.assertIs(cls.VALIDATE_INPUTS(prompt="Product", size="custom", custom_width=3840, custom_height=None), True)
        self.assertIsNot(cls.VALIDATE_INPUTS(strict=True, prompt=None), True)

    def test_reference_order_batch_count_and_extra_socket(self):
        values = {f"image{i}": IMAGE + i / 20 for i in range(nodes.MAX_IMAGES, 0, -1)}
        files = nodes.prepare_files(values)
        self.assertTrue(all(field == "image[]" for field, _ in files))
        self.assertEqual([name for field, (name, _, _) in files], [f"reference_{i}.png" for i in range(1, nodes.MAX_IMAGES + 1)])
        for invalid in ({"image1": IMAGE.repeat(nodes.MAX_IMAGES + 1, 1, 1, 1)}, {f"image{nodes.MAX_IMAGES + 1}": IMAGE}):
            with self.assertRaises(nodes.GPTImage26Error):
                nodes.collect_frames(invalid)
        with self.assertRaises(nodes.GPTImage26Error):
            nodes.prepare_files({"image1": torch.full_like(IMAGE, float("nan"))})

    def test_edit_compression_rejected_before_submission(self):
        for output in ("jpeg", "webp"):
            with self.assertRaises(nodes.GPTImage26Error):
                nodes.payload({"prompt": "Edit", "image1": IMAGE, "output_format": output, "output_compression": 80})
            self.assertNotIn("output_compression", nodes.payload({"prompt": "Edit", "image1": IMAGE, "output_format": output}))

    def test_mask_polarity_and_markup(self):
        mask = torch.zeros(1, 32, 32)
        mask[:, :16] = 1
        files = nodes.prepare_files({"image1": IMAGE, "mask": mask})
        with Image.open(io.BytesIO(files[-1][1][1])) as decoded:
            self.assertEqual(decoded.getpixel((0, 0))[3], 0)
            self.assertEqual(decoded.getpixel((0, 31))[3], 255)
        markup = torch.zeros(1, 32, 32, 4)
        markup[:, :4, :, 3] = 1
        files = nodes.prepare_files({"image1": IMAGE, "markup": markup})
        self.assertEqual(files[-1][0], "markup")
        with self.assertRaises(nodes.GPTImage26Error):
            nodes.validate({"prompt": "Edit", "image1": IMAGE, "mask": mask, "markup": markup}, True)
        with self.assertRaises(nodes.GPTImage26Error):
            nodes.prepare_files({"image1": IMAGE, "markup": IMAGE})
        with self.assertRaises(nodes.GPTImage26Error):
            nodes.prepare_files({"image1": IMAGE, "markup": torch.ones(1, 32, 32, 4)})

    def test_invalid_inputs_and_empty_key_stop_before_http(self):
        for values in ({"api_key": ""}, {"api_key": KEY, "image17": IMAGE}, {"api_key": KEY, "output_format": "gif"},
            {"api_key": KEY, "mask": torch.zeros(1, 32, 32)}):
            with patch.object(nodes.requests, "post") as post:
                with self.assertRaises(Exception):
                    nodes.T8ZhenzhenGPTImage26Workshop().generate(prompt="Edit", **values)
                post.assert_not_called()


class TransportTests(unittest.TestCase):
    def test_multi_reference_edit_multipart_preserves_all_files(self):
        files = nodes.prepare_files({"image1": IMAGE, "image2": IMAGE + .5})
        reply = response({"data": "fixture"})
        with patch.object(nodes.requests, "post", return_value=reply) as post:
            nodes.submit(KEY, {"model": nodes.MODELS[0], "prompt": "Edit"}, files)
        self.assertTrue(post.call_args.args[0].endswith("/edits?async=true"))
        self.assertEqual(post.call_args.kwargs["files"], files)
        self.assertEqual([field for field, _ in files], ["image[]", "image[]"])
        self.assertEqual(post.call_args.kwargs["data"]["model"], nodes.MODELS[0])

    def test_generation_json_and_edit_multipart_use_workshop(self):
        for files in ([], [("image", ("ref.png", b"png", "image/png"))]):
            reply = response({"data": "fixture"})
            with patch.object(nodes.requests, "post", return_value=reply) as post:
                nodes.submit(KEY, {"model": nodes.MODELS[0], "prompt": "Edit", "n": 1}, files)
            self.assertEqual(post.call_args.args[0], "https://ai.t8star.org/v1/images/" + ("edits" if files else "generations") + "?async=true")
            self.assertIn("data" if files else "json", post.call_args.kwargs)
            reply.close.assert_called_once()

    def test_lost_or_unrelated_failed_submission_is_not_replayed(self):
        with patch.object(nodes.requests, "post", side_effect=nodes.requests.RequestException("lost")) as post:
            with self.assertRaises(nodes.GPTImage26Error):
                nodes.submit(KEY, {"model": nodes.MODELS[1]}, [])
            self.assertEqual(post.call_count, 1)
        reply = response({"error": {"message": "unrelated failure"}}, 503)
        with patch.object(nodes.requests, "post", return_value=reply) as post:
            with self.assertRaises(nodes.GPTImage26Error):
                nodes.submit(KEY, {"model": nodes.MODELS[1]}, [])
            self.assertEqual(post.call_count, 1)

    def test_only_explicit_duplicate_size_route_can_use_canonical_once(self):
        for model in (nodes.MODELS[1], nodes.MODELS[2], nodes.MODELS[4], nodes.MODELS[5]):
            suffix = model[-3:]
            first = response({"error": {"message": f"no available channel for {model}{suffix}"}}, 503)
            last = response({"data": "fixture"})
            with patch.object(nodes.requests, "post", side_effect=[first, last]) as post:
                result = nodes.submit(KEY, {"model": model, "size": "2048x2048"}, [])
            self.assertEqual(post.call_count, 2)
            self.assertEqual(post.call_args.kwargs["json"]["model"], model[:-3])
            self.assertEqual(result["_zhenzhen_wire_model"], model[:-3])
            self.assertEqual(post.call_args.kwargs["json"]["size"], "2048x2048")

    def test_never_replay_route_error_with_existing_task_or_edit(self):
        model = nodes.MODELS[1]
        body = {"error": {"message": f"no available channel for {model}-2k"}}
        for value, files in ((dict(body, id="fixture"), []), (body, [("image", ("ref.png", b"png", "image/png"))])):
            with patch.object(nodes.requests, "post", return_value=response(value, 503)) as post:
                with self.assertRaises(nodes.GPTImage26Error):
                    nodes.submit(KEY, {"model": model}, files)
                self.assertEqual(post.call_count, 1)

    def test_poll_normalization_failure_deadline_and_close(self):
        complete = response({"data": {"status": "SUCCESS", "data": {"data": [{"b64_json": encoded()}]}}})
        with patch.object(nodes.requests, "get", return_value=complete):
            result = nodes.poll(KEY, "fixture", 2, 60, sleep=lambda value: None)
        self.assertEqual(len(result["data"]), 1)
        complete.close.assert_called_once()
        for reply in (response({"data": {"status": "FAILURE", "fail_reason": "fixture rejection"}}), response({"error": {"message": "bad key"}}, 401)):
            with patch.object(nodes.requests, "get", return_value=reply) as get:
                with self.assertRaises(nodes.GPTImage26Error):
                    nodes.poll(KEY, "fixture", 2, 60, sleep=lambda value: None)
                self.assertEqual(get.call_count, 1)
            reply.close.assert_called_once()
        with self.assertRaises(nodes.GPTImage26Error):
            nodes.poll(KEY, "fixture", 2, 60, clock=Mock(side_effect=[0, 61]), sleep=lambda value: None)

    def test_invalid_query_data_has_bounded_retries(self):
        malformed = response({})
        malformed.json.side_effect = ValueError("bad json")
        with patch.object(nodes.requests, "get", return_value=malformed) as get:
            with self.assertRaises(nodes.GPTImage26Error):
                nodes.poll(KEY, "fixture", 2, 60, sleep=lambda value: None)
            self.assertEqual(get.call_count, 8)


class ResultAndPluginTests(unittest.TestCase):
    def test_all_new_workflows_are_wired_and_credential_free(self):
        files = list((Path(__file__).resolve().parents[1] / "workflow").glob("zhenzhen-gpt-image-2.6-*-workshop.json"))
        self.assertEqual(len(files), 16)
        modes = set()
        for filename in files:
            text = filename.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"sk-[A-Za-z0-9]{20,}", text))
            graph = json.loads(text)
            by_id = {item["id"]: item for item in graph["nodes"]}
            self.assertEqual(len(by_id), len(graph["nodes"]))
            for link_id, source, output, target, input_index, kind in graph["links"]:
                self.assertIn(link_id, by_id[source]["outputs"][output]["links"])
                self.assertEqual(by_id[target]["inputs"][input_index]["link"], link_id)
                self.assertEqual(by_id[source]["outputs"][output]["type"], kind)
            for item in graph["nodes"]:
                if item["type"] == "T8Zhenzhen_API_Settings":
                    self.assertEqual(item["widgets_values"], ["zhenzhen", "", "", False])
                if NODE_KEY in item["type"]:
                    self.assertTrue(next(value for value in item["inputs"] if value["name"] == "api_key")["link"])
                    self.assertIn("fixed", item["widgets_values"])
            for model in nodes.MODELS:
                for mode in ("text", "edit"):
                    if filename.name == f"zhenzhen-{model}-{mode}-workshop.json":
                        modes.add((model, mode))
        self.assertEqual(len(modes), 12)

    def test_all_base64_and_url_items_decoded_with_transparency(self):
        result = {"data": [{"b64_json": encoded(0)}, {"url": URL}, {"b64_json": encoded(128)}]}
        with patch.object(nodes, "download_image_with_alpha_retry", return_value=Image.new("RGBA", (16, 16), "blue")):
            images, urls, masks = nodes.decode_result(result)
        self.assertEqual(tuple(images.shape), (3, 16, 16, 3))
        self.assertEqual(tuple(masks.shape), (3, 16, 16))
        self.assertEqual(urls, [URL])
        self.assertEqual(float(masks[0, 0, 0]), 1)
        self.assertEqual(float(masks[1, 0, 0]), 0)
        self.assertAlmostEqual(float(masks[2, 0, 0]), 127 / 255, places=6)

    def test_bad_results_and_mismatched_sizes_are_explicit(self):
        for result in ({}, {"data": []}, {"data": [{}]}, {"data": [{"b64_json": "bad!"}]}):
            with self.assertRaises(Exception):
                nodes.decode_result(result)
        with patch.object(nodes, "download_image_with_alpha_retry", return_value=Image.new("RGBA", (32, 16), "blue")):
            with self.assertRaises(nodes.GPTImage26Error):
                nodes.decode_result({"data": [{"b64_json": encoded()}, {"url": URL}]})

    def test_immediate_and_async_execution_mask_and_safe_response(self):
        for asynchronous in (False, True):
            completed = {"data": [{"b64_json": encoded(128)}]}
            with patch.object(nodes, "submit", return_value={"data": "fixture"} if asynchronous else completed) as submit, \
                 patch.object(nodes, "poll", return_value=completed) as poll:
                result = nodes.T8ZhenzhenGPTImage26Workshop().generate(prompt="Edit", api_key=KEY, async_mode=asynchronous, seed=42)
            self.assertEqual(len(result), 4)
            self.assertEqual(poll.call_count, int(asynchronous))
            self.assertNotIn("seed", submit.call_args.args[1])
            self.assertNotIn(encoded(128), result[2])
            self.assertEqual(json.loads(result[2])["selected_model"], nodes.MODELS[0])

    def test_skip_error_returns_all_slots_without_http_for_invalid_input(self):
        with patch.object(nodes.requests, "post") as post:
            result = nodes.T8ZhenzhenGPTImage26Workshop().generate(prompt="", api_key=KEY, skip_error=True)
        self.assertEqual(len(result), 4)
        self.assertEqual(tuple(result[0].shape), (1, 512, 512, 3))
        self.assertEqual(tuple(result[3].shape), (1, 512, 512))
        self.assertEqual(result[1], "")
        post.assert_not_called()

    def test_registration_cache_controls_and_concurrent_schema(self):
        plugin, concurrent = module("Comfly"), module("ComflyConcurrent")
        cls = plugin.NODE_CLASS_MAPPINGS[NODE_KEY]
        wrapper = concurrent.CONCURRENT_NODE_CLASS_MAPPINGS[f"ComflyConcurrent_{NODE_KEY}_Submit"]
        self.assertEqual(cls.INPUT_TYPES(), wrapper.INPUT_TYPES())
        self.assertFalse(hasattr(wrapper, "VALIDATE_INPUTS"))
        with patch.object(concurrent.IMAGE_EXECUTOR, "submit") as worker:
            with self.assertRaises(ValueError):
                wrapper().submit(prompt=" ")
            worker.assert_not_called()
        self.assertIn(NODE_KEY, plugin.EXECUTION_SEED_NODE_KEYS)
        self.assertIs(plugin.NODE_CLASS_MAPPINGS["T8Zhenzhen_GPT_Image_2_5_Workshop"], nodes.legacy.T8ZhenzhenGPTImage25Workshop)


if __name__ == "__main__":
    unittest.main()
