import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import torch
from PIL import Image

from nov08_fixture import module, ROOT
nodes = module("seedream55_low_price_nodes")
api = module("seedream55_contracts")
legacy = module("seedance_low_price_nodes")
concurrent_nodes = module("ComflyConcurrent")
plugin = module("Comfly")
SeedanceAPIError = nodes.Error

CONFIG = {"base_url": "https://example.test", "api_key": "sk-test"}
URL = "https://example.com/image.png"
IMAGE = torch.zeros(1, 4, 4, 3)


class Seedream55Tests(unittest.TestCase):
    def test_independent_catalogs_outputs_lists_and_cache_controls(self):
        self.assertEqual(len(api.IMAGE_MODELS), 4)
        self.assertEqual(len(api.LAYER_MODELS), 2)
        for key, cls in (("T8Zhenzhen_Seedream_55_Image_LowPrice", nodes.T8ZhenzhenSeedream55Image), ("T8Zhenzhen_Seedream_55_Layers_LowPrice", nodes.T8ZhenzhenSeedream55Layers)):
            self.assertIs(plugin.NODE_CLASS_MAPPINGS[key], cls)
            schema = cls.INPUT_TYPES()
            self.assertFalse(schema["optional"]["skip_error"][1]["default"])
            self.assertTrue(schema["optional"]["seed"][1]["control_after_generate"])
            self.assertTrue(cls.SEEDANCE_EXPLICIT_CACHE_ONLY_SEED)
        self.assertEqual(nodes.T8ZhenzhenSeedream55Layers.OUTPUT_IS_LIST, (True, True, False, False, False, False, False, False))
        self.assertNotIn("ComflyConcurrent_T8Zhenzhen_Seedream_55_Layers_LowPrice_Submit", concurrent_nodes.CONCURRENT_NODE_CLASS_MAPPINGS)

    def test_all_six_models_exact_request_whitelist(self):
        for model in api.IMAGE_MODELS + api.LAYER_MODELS:
            layer = model.endswith("layer-decomposition")
            kwargs = {"model": model, "prompt": "five characters", "resolution": "1k", "seed": 42,
                      "safety_identifier": "test-session", "unknown": "ignored", "width": 123, "height": 456}
            urls = []
            if layer:
                kwargs.update(image=IMAGE, max_images=2, text_recognition=True)
                urls = [URL]
            elif model.endswith("i2i"):
                kwargs["image1"] = IMAGE
                urls = [URL]
            payload = api.payload(kwargs, urls, layer)
            self.assertEqual(payload["model"], model)
            self.assertEqual(payload["metadata"]["resolution"], "1k")
            self.assertNotIn("width", payload["metadata"])
            self.assertNotIn("seed", payload["metadata"])
            self.assertNotIn("unknown", payload)
            self.assertFalse(payload["metadata"]["watermark"])
            self.assertEqual(payload["metadata"]["safety_identifier"], "test-session")
            if layer:
                self.assertEqual(payload["metadata"]["max_images"], 2)
                self.assertTrue(payload["metadata"]["text_recognition"])
                self.assertNotIn("background", payload["metadata"])

    def test_reference_bounds_t2i_and_i2i(self):
        base = {"model": api.IMAGE_MODELS[1], "prompt": "five chars"}
        for count in (1, 10):
            kwargs = {**base, **{f"image{i}": IMAGE for i in range(1, count+1)}}
            self.assertTrue(api.validate(kwargs, strict=True))
        for kwargs in (base, {**base, "image11": IMAGE}, {"prompt": "five chars", "image1": IMAGE}):
            with self.assertRaises(SeedanceAPIError):
                api.validate(kwargs, strict=True)

    def test_custom_canvas_limits_area_ratio_and_resolution_precedence(self):
        for width, height in ((960, 960), (11520, 720), (720, 11520), (2048, 1152)):
            payload = api.payload({"prompt": "five chars", "resolution": "custom", "width": width, "height": height}, [])
            self.assertEqual(payload["metadata"]["width"], width)
            self.assertNotIn("resolution", payload["metadata"])
        for width, height in ((959, 960), (11521, 720), (11520, 719), (3000, 3000), (True, 1024), (1024.0, 1024)):
            with self.subTest(width=width, height=height), self.assertRaises(SeedanceAPIError):
                api.validate({"prompt": "five chars", "resolution": "custom", "width": width, "height": height}, strict=True)

    def test_prompts_transparency_safety_and_boolean_types(self):
        for kwargs in ({"prompt": "four"}, {"prompt": "x"*5001}, {"prompt": 42}, {"prompt": "valid text", "background": "transparent", "output_format": "jpeg"},
                       {"prompt": "valid text", "watermark": "false"}, {"prompt": "valid text", "safety_identifier": "x"*65}):
            with self.assertRaises(SeedanceAPIError):
                api.validate(kwargs, strict=True)
        self.assertTrue(api.validate({"prompt": None, "resolution": "custom", "width": None, "height": None}, strict=False))
        self.assertTrue(api.validate({"prompt": "x"*5000, "background": "transparent", "output_format": "png"}, strict=True))
        self.assertTrue(api.validate({"image": IMAGE, "prompt": ""}, layer=True, strict=True))
        with self.assertRaises(SeedanceAPIError):
            api.validate({"image": IMAGE, "prompt": "x"*2001}, layer=True, strict=True)

    def test_layer_max_images_includes_base(self):
        for count in (2, 30, 100):
            self.assertTrue(api.validate({"image": IMAGE, "max_images": count}, layer=True, strict=True))
        for count in (1, 101, 2.0, True, "2"):
            with self.assertRaises(SeedanceAPIError):
                api.validate({"image": IMAGE, "max_images": count}, layer=True, strict=True)
        with self.assertRaises(SeedanceAPIError):
            api.validate({"image": IMAGE, "image1": IMAGE}, layer=True, strict=True)

    def test_reference_png_preserves_alpha_and_source_order(self):
        rgba = torch.ones(1, 3, 2, 4)
        rgba[0, 0, 0, 3] = 0
        encoded = api.encode_references({"image2": rgba, "image10": IMAGE})
        self.assertEqual([index for index, _ in encoded], [2, 10])
        with Image.open(io.BytesIO(encoded[0][1])) as image:
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.getpixel((0, 0))[3], 0)


    def test_bad_sources_stop_before_first_upload(self):
        for source in (torch.zeros(2,4,4,3), torch.zeros(1,4,4,2), torch.full_like(IMAGE, float("nan"))):
            with patch.object(nodes.api, "upload_media") as upload:
                with self.assertRaises(SeedanceAPIError):
                    nodes.T8ZhenzhenSeedream55Image().execute(model=api.IMAGE_MODELS[1], prompt="valid prompt", image1=IMAGE, image2=source, api_config=CONFIG)
                upload.assert_not_called()

    def test_original_rgba_bytes_and_mask_are_preserved(self):
        image = Image.new("RGBA", (3,2), (20,30,40,255))
        image.putpixel((0,0), (20,30,40,0))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        data = stream.getvalue()
        from unittest.mock import Mock
        response = Mock(headers={"Content-Length": str(len(data))})
        response.iter_content.return_value = [data]
        artifacts = module("image_artifacts")
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, {"folder_paths": SimpleNamespace(get_output_directory=lambda: directory)}), patch.object(artifacts, "get_media_response", return_value=response):
            tensor, mask, path, entry = api.download_original(URL)
            self.assertEqual(tensor.shape[-1], 4)
            self.assertEqual(float(mask[0,0,0]), 1)
            self.assertEqual(float(mask[0,0,1]), 0)
            self.assertEqual(Path(path).read_bytes(), data)
            self.assertEqual(entry["type"], "output")
            self.assertFalse(list(Path(directory).rglob("*.part")))
        response.close.assert_called_once()

    def test_all_100_layers_keep_order_sizes_alpha_paths_and_metadata(self):
        urls = [f"https://example.com/layer{i}.png" for i in range(100)]
        final = {"data":{"data":{"content":{"image_urls":urls}}}}
        def download(url, prefix):
            index = urls.index(url)
            return torch.zeros(1,index+1,2,4), torch.zeros(1,index+1,2), f"/output/layer{index}.png", {"filename":f"layer{index}.png"}
        with patch.object(nodes, "get_config", return_value=CONFIG), patch.object(nodes.api, "upload_media", return_value=URL), patch.object(nodes, "submit_task", return_value="fixture"), patch.object(nodes, "poll_task", return_value=final), patch.object(api, "download_original", side_effect=download) as downloads:
            result = nodes.T8ZhenzhenSeedream55Layers().execute(image=IMAGE, max_images=100)
        values = result["result"]
        self.assertEqual([len(values[0]),len(values[1]),values[3],len(json.loads(values[6])),len(result["ui"]["images"])], [100]*5)
        self.assertEqual(values[0][-1].shape[1], 100)
        self.assertEqual(json.loads(values[7]), [])
        self.assertEqual([call.args[0] for call in downloads.call_args_list], urls)

    def test_layer_metadata_and_url_array_are_not_guessed_or_truncated(self):
        self.assertEqual(api.layer_metadata({}, [URL]), [])
        final = {"data":{"data":{"content":{"image_urls":[URL], "layers":[{"url":URL,"name":"foreground"}]}}}}
        self.assertEqual(api.layer_metadata(final, [URL])[0]["name"], "foreground")
        with self.assertRaises(SeedanceAPIError):
            api.layer_metadata(final, [URL,URL])
        for urls in (None, [], [URL,None], [URL,""]):
            with self.assertRaises(SeedanceAPIError):
                nodes.layer_urls({"data":{"data":{"content":{"image_urls":urls}}}})

    def test_output_prefix_and_blank_config_fail_before_requests(self):
        import os
        for cls, kwargs in ((nodes.T8ZhenzhenSeedream55Image, {"prompt":"valid prompt"}), (nodes.T8ZhenzhenSeedream55Layers, {"image":IMAGE})):
            for config, prefix in ((CONFIG, "../outside"), ({}, "zhenzhen/valid"), (None, "zhenzhen/valid")):
                with patch.dict(os.environ, {"SEEDANCE_API_KEY":"environment-fixture"}), patch.object(nodes.api,"upload_media") as upload, patch.object(nodes,"submit_task") as submit:
                    with self.assertRaises(SeedanceAPIError):
                        cls().execute(api_config=config, filename_prefix=prefix, **kwargs)
                    upload.assert_not_called()
                    submit.assert_not_called()

    def test_concurrent_rgba_and_skip_error_output_shapes(self):
        cls = concurrent_nodes.CONCURRENT_NODE_CLASS_MAPPINGS["ComflyConcurrent_T8Zhenzhen_Seedream_55_Image_LowPrice_Submit"]
        self.assertFalse(hasattr(cls,"VALIDATE_INPUTS"))
        rgba = torch.zeros(1,3,4,4)
        with patch.object(nodes.T8ZhenzhenSeedream55Image,"_execute_inner",return_value={"result":(rgba,URL,"fixture","{}",rgba[...,3],"local.png")}):
            future = cls().submit(prompt="valid prompt",api_config=CONFIG)[0]
            result = concurrent_nodes.CONCURRENT_NODE_CLASS_MAPPINGS["ComflyConcurrent_Image_Await"]().wait_all(failure_mode="placeholder", task_1=future)
        values = result["result"] if isinstance(result,dict) else result
        self.assertTrue(torch.equal(values[0],rgba))
        for node in (nodes.T8ZhenzhenSeedream55Image(),nodes.T8ZhenzhenSeedream55Layers()):
            with patch.object(node,"_execute_inner",side_effect=RuntimeError("fixture")) as inner:
                result = node.execute(seed=42,skip_error=True)["result"]
                self.assertNotIn("seed",inner.call_args.kwargs)
                self.assertEqual(len(result),len(node.RETURN_TYPES))


class DraftTests(unittest.TestCase):
    def test_legacy_prefix_catalog_and_default_false_remain_compatible(self):
        schema = legacy.Comfly_seedance25_standard_low_price.INPUT_TYPES()
        self.assertEqual(list(schema["optional"])[-5:], ["generate_audio","return_last_frame","seed","skip_error","draft"])
        self.assertFalse(schema["optional"]["draft"][1]["default"])
        self.assertEqual(len(legacy.SEEDANCE25_MODELS),6)
        self.assertEqual(legacy.Comfly_seedance25_standard_low_price.RETURN_NAMES,("video","video_url","task_id","response"))
        for model in legacy.SEEDANCE25_MODELS:
            values = {"model":model,"prompt":"valid prompt","seconds":"4","resolution":"native1080p","ratio":"16:9","seed":-1}
            media = {"images":[URL]} if model.endswith("i2v") else {"content":[]} if model.endswith("multi") else {}
            original = legacy.Comfly_seedance25_standard_low_price.build_payload(values,media)
            self.assertNotIn("draft",original["metadata"])
            self.assertEqual(original,legacy.Comfly_seedance25_standard_low_price.build_payload({**values,"draft":False},media))
            draft = legacy.Comfly_seedance25_standard_low_price.build_payload({**values,"draft":True},media)
            self.assertEqual(draft["metadata"]["resolution"],"480p")
            self.assertTrue(draft["metadata"]["draft"])
        with self.assertRaises(SeedanceAPIError):
            legacy.Comfly_seedance25_standard_low_price.build_payload({**values,"draft":"false"},media)

    def test_enhancement_metadata_whitelist_and_connected_validation(self):
        cls = nodes.T8ZhenzhenSeedance25DraftToVideo
        self.assertTrue(cls.VALIDATE_INPUTS(draft_task_id=None))
        for model in nodes.DRAFT_MODELS:
            body = cls().build_payload({"model":model,"draft_task_id":" fixture ","output_format":"mov","return_last_frame":True,"seed":99,"prompt":"stale","resolution":"4k","image1":IMAGE,"seconds":"30"})
            self.assertEqual(body,{"model":model,"metadata":{"draft_task_id":"fixture","output_format":"mov","return_last_frame":True}})
        for values in ({},{"draft_task_id":""},{"draft_task_id":"https://example.com/video.mp4"},{"draft_task_id":123},{"draft_task_id":"fixture","output_format":"avi"},{"draft_task_id":"fixture","return_last_frame":"true"},{"draft_task_id":"fixture","model":None}):
            with patch.object(nodes,"submit_task") as submit:
                with self.assertRaises(SeedanceAPIError):
                    cls().execute(api_config=CONFIG,**values)
                submit.assert_not_called()

    def test_enhancement_downloads_requested_container(self):
        with patch.object(nodes,"submit_task",return_value="fixture") as submit, patch.object(nodes,"poll_task",return_value={"status":"completed","url":URL}), patch.object(nodes,"download_video_with_path",return_value=("video","file.mov")) as download:
            result = nodes.T8ZhenzhenSeedance25DraftToVideo().execute(draft_task_id="fixture",api_config=CONFIG,output_format="mov",seed=42)
        self.assertEqual(result[:3],("video",URL,"fixture"))
        self.assertEqual(download.call_args.kwargs["file_extension"],"mov")
        self.assertNotIn("seed",submit.call_args.args[0]["metadata"])

    def test_shared_download_extension_opt_in_preserves_mp4_default(self):
        from unittest.mock import Mock
        for extension in ("mp4","mov"):
            response = Mock(headers={})
            response.iter_content.return_value=[b"fixture-video"]
            with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules,{"folder_paths":SimpleNamespace(get_output_directory=lambda:directory)}), patch.object(legacy,"get_media_response",return_value=response), patch.object(legacy,"_video_from_path",side_effect=lambda path:path):
                kwargs = {} if extension == "mp4" else {"file_extension":extension}
                path = legacy.download_video(URL,**kwargs)
                self.assertTrue(path.endswith("."+extension))
                self.assertEqual(Path(path).read_bytes(),b"fixture-video")

    def test_creation_transport_is_single_attempt_and_closes_response(self):
        from unittest.mock import Mock
        response = Mock(status_code=200,text="ok")
        response.json.return_value={"id":"fixture"}
        with patch.object(nodes.api,"_get_session",return_value=Mock(post=Mock(return_value=response))):
            self.assertEqual(nodes.submit_task({"model":"fixture"},CONFIG),"fixture")
        response.close.assert_called_once()
        session=Mock()
        session.post.side_effect=nodes.api.requests.ReadTimeout("fixture")
        with patch.object(nodes.api,"_get_session",return_value=session):
            with self.assertRaises(SeedanceAPIError):
                nodes.submit_task({"model":"fixture"},CONFIG)
        self.assertEqual(session.post.call_count,1)

    def test_eleven_examples_have_blank_keys_layer_savers_and_correct_id_wiring(self):
        paths=[path for path in (ROOT/"workflow").glob("*.json") if path.name.startswith(("zhenzhen-seedream-v5.5-", "zhenzhen-dola-seedream-5.5-", "zhenzhen-seedance-2.5-")) and ("5.5" in path.name or "draft-to-video" in path.name)]
        paths.append(ROOT/"workflow/zhenzhen-seedream55-transparent-lowprice.json")
        self.assertEqual(len(paths),11)
        for path in paths:
            graph=json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(graph["nodes"][0]["widgets_values"],["seedance_low_price","","",False])
            if "layer-decomposition" in path.name:
                self.assertIn("JoinImageWithAlpha",[node["type"] for node in graph["nodes"]])
                self.assertIn("SaveImage",[node["type"] for node in graph["nodes"]])
            if "-chain-" in path.name:
                source=next(node for node in graph["nodes"] if node["type"]=="Comfly_seedance25_standard_low_price")
                self.assertEqual(source["widgets_values"][8:],["fixed",False,True])
                enhance=next(node for node in graph["nodes"] if node["type"]=="T8Zhenzhen_Seedance_25_Draft_To_Video_LowPrice")
                item=next(item for item in enhance["inputs"] if item["name"]=="draft_task_id")
                link=next(link for link in graph["links"] if link[0]==item["link"])
                self.assertEqual(link[2],2)


if __name__ == "__main__":
    unittest.main()
