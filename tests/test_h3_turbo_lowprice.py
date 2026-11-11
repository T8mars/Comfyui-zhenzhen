import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import torch

from nov08_fixture import ROOT, module

nodes = module("h3_turbo_low_price_nodes")
contracts = nodes.contracts
plugin = module("Comfly")
parallel = module("ComflyConcurrent")
Error = nodes.api.SeedanceLowPriceError
IMAGE = torch.zeros(1, 8, 8, 4)
AUDIO = {"waveform": torch.zeros(1, 1, 800), "sample_rate": 8000}
CONFIG = {"base_url": "https://example.test", "api_key": "sk-test"}
URL = "https://example.test/output"


class H3TurboTests(unittest.TestCase):
    def test_unique_nodes_and_pure_concurrent_wrappers(self):
        for kind, cls in nodes.CLASSES.items():
            self.assertIs(plugin.NODE_CLASS_MAPPINGS[nodes.KEYS[kind]], cls)
            schema = cls.INPUT_TYPES()
            self.assertEqual(schema["required"]["resolution"][1]["default"], contracts.PROFILES[kind]["default"])
            self.assertFalse(schema["optional"]["skip_error"][1]["default"])
            seed = schema["optional"].get("seed") or schema["required"]["seed"]
            self.assertTrue(seed[1]["control_after_generate"])
            self.assertEqual(len(cls.RETURN_TYPES), 4)
            wrapper = parallel.CONCURRENT_NODE_CLASS_MAPPINGS["ComflyConcurrent_"+nodes.KEYS[kind]+"_Submit"]
            self.assertFalse(hasattr(wrapper, "VALIDATE_INPUTS"))
            self.assertEqual(wrapper.INPUT_TYPES(), schema)

    def test_default_payload_whitelists_and_no_video_api_seed(self):
        self.assertEqual(contracts.payload("video", {"prompt": " animate ", "seed": 3}, []),
            {"model": "minimax-h3-comfyui-max", "prompt": "animate", "seconds": "5", "metadata": {"resolution": "480p", "ratio": "16:9"}})
        for kind in ("minimax_image", "qwen"):
            body = contracts.payload(kind, {"prompt": "draw", "seed": -1, "n": 20, "megapixels": 4, "output_format": "png"}, [])
            self.assertEqual(set(body), {"model", "prompt", "metadata"})
            self.assertNotIn("seed", body["metadata"])
            self.assertEqual("output_format" in body["metadata"], kind == "minimax_image")

    def test_video_enums_are_not_legacy_h3_enums(self):
        self.assertEqual(contracts.PROFILES["video"]["resolutions"], ["480p","608p","768p","896p","1088p","1280p","1440p"])
        for resolution in contracts.PROFILES["video"]["resolutions"]:
            for seconds in ("3", "15"):
                self.assertTrue(contracts.validate("video", {"resolution": resolution, "seconds": seconds, "ratio": "9:16"}))
        for values in ({"resolution":"1080p"},{"ratio":"1:1"},{"seconds":3},{"seconds":"2"},{"seconds":"16"}):
            with self.assertRaises(Error):
                contracts.validate("video", values)

    def test_prompt_and_converted_controls_deferred_until_execution(self):
        for kind, cls in nodes.CLASSES.items():
            self.assertIs(cls.VALIDATE_INPUTS(prompt=None, resolution=None, ratio=None, seed=None), True)
            self.assertIsNot(cls.VALIDATE_INPUTS(prompt=12), True)
            for values in ({"prompt":" "}, {"prompt":"draw","resolution":None}, {"prompt":"draw","ratio":None}):
                with self.assertRaises(Error):
                    contracts.validate(kind, values, strict=True)

    def test_qwen_limit_is_utf8_bytes(self):
        self.assertTrue(contracts.validate("qwen", {"prompt":"中"*2730+"ab"}, strict=True))
        for text in ("a"*8193, "中"*2731, "😀"*2049):
            with self.assertRaisesRegex(Error, "8192 UTF-8"):
                contracts.validate("qwen", {"prompt":text}, strict=True)

    def test_qwen_edit_only_720p_and_minimax_formats(self):
        self.assertTrue(contracts.validate("qwen", {"resolution":"720p"}))
        with self.assertRaisesRegex(Error,"720p"):
            contracts.payload("qwen", {"prompt":"draw","resolution":"720p"}, [])
        body = contracts.payload("qwen", {"prompt":"edit","resolution":"720p","image1":IMAGE}, [URL])
        self.assertEqual(body["metadata"], {"resolution":"720p","ratio":"1:1"})
        for format_ in ("jpeg","png","webp"):
            self.assertEqual(contracts.payload("minimax_image", {"prompt":"draw","output_format":format_}, [])["metadata"]["output_format"],format_)
        for values in ({"output_format":"gif"},{"ratio":"auto"},{"resolution":"720p"}):
            with self.assertRaises(Error):
                contracts.validate("minimax_image", values)

    def test_native_seed_zero_max_and_minus_one(self):
        for kind in ("minimax_image","qwen"):
            for seed in (0,2147483647):
                self.assertEqual(contracts.payload(kind,{"prompt":"draw","seed":seed},[])["metadata"]["seed"],seed)
            for seed in (-2,2147483648,True,1.5,"1",None):
                with self.assertRaises(Error):
                    contracts.validate(kind,{"prompt":"draw","seed":seed},strict=True)

    def test_reference_limits_order_and_rgba_encoding(self):
        for kind, spec in contracts.PROFILES.items():
            values = {f"image{i}":IMAGE for i in range(1,spec["images"]+1)}
            self.assertTrue(contracts.validate(kind,values))
            with self.assertRaises(Error):
                contracts.validate(kind,{**values,f"image{spec['images']+1}":IMAGE})
        prepared = contracts.encode_media("minimax_image",{"prompt":"edit","image16":IMAGE,"image2":IMAGE})
        self.assertEqual([item[0] for item in prepared],["image2","image16"])
        with Image.open(io.BytesIO(prepared[0][1])) as image:
            self.assertEqual(image.mode,"RGBA")

    def test_all_validation_finishes_before_first_upload(self):
        for bad in (torch.zeros(2,8,8,3),torch.zeros(1,8,8,1),torch.full((1,8,8,3),float("nan"))):
            with patch.object(nodes.api,"upload_media") as upload:
                with self.assertRaises(Error):
                    nodes.T8ZhenzhenMinimaxH3Image().execute(prompt="edit",image1=IMAGE,image16=bad,api_config=CONFIG)
                upload.assert_not_called()
        with patch.object(nodes.api,"upload_media") as upload:
            with self.assertRaises(Error):
                nodes.T8ZhenzhenMinimaxH3ComfyUIMax().execute(prompt="animate",image1=IMAGE,audio1={"waveform":torch.zeros(2,1,8),"sample_rate":8000},api_config=CONFIG)
            upload.assert_not_called()

    def test_video_image_and_audio_encoded_size_limits(self):
        for unit,count,message in ((1,1,"10 MiB"),(10,9,"50 MiB")):
            with patch.object(contracts,"MIB",unit):
                with self.assertRaisesRegex(Error,message):
                    contracts.encode_media("video",{"prompt":"animate",**{f"image{i}":IMAGE for i in range(1,count+1)}})
        with patch.object(contracts,"MIB",1),patch.object(contracts,"audio_to_wav_bytes",return_value=b"x"*6):
            with self.assertRaisesRegex(Error,"10 MiB"):
                contracts.encode_media("video",{"prompt":"animate","audio1":AUDIO,"audio2":AUDIO})

    def test_three_audio_slots_order_and_metadata_location(self):
        with patch.object(contracts,"audio_to_wav_bytes",return_value=b"wave"):
            prepared=contracts.encode_media("video",{"prompt":"animate","audio3":AUDIO,"audio1":AUDIO})
        self.assertEqual([item[0] for item in prepared],["audio1","audio3"])
        body=contracts.payload("video",{"prompt":"animate"},[],[URL,"https://example.test/second.wav"])
        self.assertEqual(body["metadata"]["audio_urls"],[URL,"https://example.test/second.wav"])
        with self.assertRaises(Error):
            contracts.validate("video",{"audio4":AUDIO})

    def test_correct_endpoints_and_close_without_post_replay(self):
        for video in (False,True):
            response=Mock(status_code=200,text="ok")
            response.json.return_value={"data":{"id":"fixture"}}
            session=Mock()
            session.post.return_value=response
            with patch.object(nodes.api,"_get_session",return_value=session):
                self.assertEqual(nodes.submit_task({"model":"fixture"},CONFIG,video),"fixture")
            self.assertEqual(session.post.call_args.args[0],CONFIG["base_url"]+"/v1/"+("video" if video else "image")+"/generations")
            response.close.assert_called_once()
        session=Mock()
        session.post.side_effect=nodes.api.requests.ReadTimeout("fixture")
        with patch.object(nodes.api,"_get_session",return_value=session):
            with self.assertRaisesRegex(Error,"not retried"):
                nodes.submit_task({},CONFIG,True)
        self.assertEqual(session.post.call_count,1)

    def test_node_pipeline_selects_legacy_video_parser_and_shared_download(self):
        final={"data":{"status":"SUCCESS","result_url":URL}}
        for kind,cls in nodes.CLASSES.items():
            video=kind=="video"
            with patch.object(nodes.api,"upload_media",side_effect=lambda data,name,*a:URL+"/"+name) as upload,patch.object(nodes,"submit_task",return_value="fixture") as submit,patch.object(nodes,"poll_task",return_value=final) as poll,patch.object(nodes.api,"download_video" if video else "download_image",return_value=IMAGE) as download:
                result=cls().execute(api_config=CONFIG,prompt="animate",image3=IMAGE,image1=IMAGE,seed=0,**({"audio1":AUDIO} if video else {}))["result"]
            self.assertIs(result[0],IMAGE)
            self.assertEqual(result[2],"fixture")
            body=submit.call_args.args[0]
            self.assertEqual(body["images"],[URL+"/image1.png",URL+"/image3.png"])
            self.assertEqual("seed" in body["metadata"],not video)
            self.assertEqual(submit.call_args.kwargs["video"],video)
            self.assertEqual(upload.call_count,3 if video else 2)
            poll.assert_called_once()
            download.assert_called_once_with(URL)

    def test_missing_and_blank_key_never_fall_back(self):
        with patch.dict(os.environ,{"SEEDANCE_API_KEY":"sk-environment-fixture"}):
            for value in (None,{}, {"api_key":" "}):
                with self.assertRaises(Error):
                    nodes.get_config(value)

    def test_skip_error_and_concurrent_runtime_validation(self):
        for cls in nodes.CLASSES.values():
            with patch.object(cls,"_execute_inner",side_effect=RuntimeError("fixture")),patch.object(nodes.api,"make_error_video",return_value="video"):
                with self.assertRaises(RuntimeError):
                    cls().execute()
                self.assertEqual(len(cls().execute(skip_error=True)["result"]),4)
        wrapper=parallel.CONCURRENT_NODE_CLASS_MAPPINGS["ComflyConcurrent_"+nodes.KEYS["qwen"]+"_Submit"]
        with patch.object(parallel.IMAGE_EXECUTOR,"submit") as submit:
            with self.assertRaisesRegex(ValueError,"720p"):
                wrapper().submit(prompt="draw",resolution="720p")
            submit.assert_not_called()

    def test_eight_blank_key_workflows_cover_native_saving_and_all_modes(self):
        paths=[p for p in (ROOT/"workflow").glob("*.json") if p.name.startswith(("zhenzhen-minimax-h3-comfyui-max-","zhenzhen-minimax-h3-image-","zhenzhen-qwen-image-2.1-turbo-"))]
        self.assertEqual(len(paths),8)
        for path in paths:
            graph=json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(graph["nodes"][0]["widgets_values"],["seedance_low_price","","",False])
            self.assertTrue(any(n["type"]==("SaveVideo" if "comfyui-max" in path.name else "SaveImage") for n in graph["nodes"]))
            if "-edit-" in path.name:
                self.assertEqual(sum(n["type"]=="LoadImage" for n in graph["nodes"]),2)


if __name__ == "__main__":
    unittest.main()
