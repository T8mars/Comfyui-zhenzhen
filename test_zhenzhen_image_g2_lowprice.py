import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

import seedance_low_price_nodes as nodes


ROOT = Path(__file__).resolve().parent
WORKFLOW_CASES = {
    "zhenzhen-image-g2文生图（贞贞的平价AI小屋）.json": {
        "model": nodes.ZHENZHEN_IMAGE_G2_T2I_MODEL,
        "image_link": False,
    },
    "zhenzhen-image-g2图像编辑（贞贞的平价AI小屋）.json": {
        "model": nodes.ZHENZHEN_IMAGE_G2_I2I_MODEL,
        "image_link": True,
    },
}


class ZhenzhenImageG2NodeTests(unittest.TestCase):
    def test_text_to_image_payload_matches_documented_contract(self):
        payload = nodes.build_zhenzhen_image_g2_payload(
            nodes.ZHENZHEN_IMAGE_G2_T2I_MODEL,
            "a clean studio product photo",
            "1k",
            "adaptive",
            ["https://cdn.test/ignored.png"],
        )

        self.assertEqual(
            payload,
            {
                "model": "zhenzhen-image-g2-t2i",
                "prompt": "a clean studio product photo",
                "metadata": {"resolution": "1k"},
            },
        )
        self.assertNotIn("images", payload)
        self.assertNotIn("output_format", payload["metadata"])
        self.assertNotIn("width", payload["metadata"])
        self.assertNotIn("height", payload["metadata"])

    def test_image_to_image_payload_matches_documented_contract(self):
        payload = nodes.build_zhenzhen_image_g2_payload(
            nodes.ZHENZHEN_IMAGE_G2_I2I_MODEL,
            "turn this into a polished blue app icon",
            "1k",
            "1:1",
            ["https://cdn.test/reference.png"],
        )

        self.assertEqual(payload["model"], "zhenzhen-image-g2-i2i")
        self.assertEqual(payload["images"], ["https://cdn.test/reference.png"])
        self.assertEqual(payload["metadata"], {"resolution": "1k", "ratio": "1:1"})

    def test_validation_enforces_g2_limits(self):
        self.assertIs(
            nodes.Comfly_zhenzhen_image_g2_lowprice.VALIDATE_INPUTS(
                model=nodes.ZHENZHEN_IMAGE_G2_T2I_MODEL,
                prompt="",
                resolution="1k",
                ratio="adaptive",
            ),
            True,
        )
        self.assertIsNot(
            nodes.Comfly_zhenzhen_image_g2_lowprice.VALIDATE_INPUTS(
                model=nodes.ZHENZHEN_IMAGE_G2_T2I_MODEL,
                prompt="",
                resolution="1k",
                ratio="adaptive",
                strict=True,
            ),
            True,
        )
        self.assertIsNot(
            nodes.Comfly_zhenzhen_image_g2_lowprice.VALIDATE_INPUTS(
                model=nodes.ZHENZHEN_IMAGE_G2_T2I_MODEL,
                prompt="valid prompt",
                resolution="2k",
                ratio="adaptive",
            ),
            True,
        )
        with self.assertRaises(nodes.SeedanceLowPriceError):
            nodes.build_zhenzhen_image_g2_payload(
                nodes.ZHENZHEN_IMAGE_G2_I2I_MODEL,
                "valid editing prompt",
                "1k",
                "adaptive",
                [],
            )

    def test_execute_uploads_i2i_reference_and_returns_downloaded_image(self):
        node = nodes.Comfly_zhenzhen_image_g2_lowprice()
        reference = torch.zeros((1, 8, 8, 3), dtype=torch.float32)
        result_tensor = torch.ones((1, 4, 4, 3), dtype=torch.float32)
        final_response = {
            "data": {
                "status": "SUCCESS",
                "result_url": "https://cdn.test/result.png",
            }
        }

        with patch.object(
            nodes,
            "resolve_config",
            return_value={"base_url": "https://api.seedance.nz", "api_key": "test"},
        ), patch.object(
            nodes,
            "upload_media",
            return_value="https://cdn.test/reference.png",
        ) as upload, patch.object(
            nodes,
            "submit_image_task",
            return_value=("image-task", {"id": "image-task"}),
        ) as submit, patch.object(
            nodes,
            "poll_image_task",
            return_value=final_response,
        ), patch.object(
            nodes,
            "download_image",
            return_value=result_tensor,
        ):
            output = node.generate_image(
                model=nodes.ZHENZHEN_IMAGE_G2_I2I_MODEL,
                prompt="turn this into a polished blue app icon",
                resolution="1k",
                ratio="1:1",
                image1=reference,
            )

        upload.assert_called_once()
        submitted_payload = submit.call_args.args[0]
        self.assertEqual(submitted_payload["images"], ["https://cdn.test/reference.png"])
        self.assertEqual(submitted_payload["metadata"], {"resolution": "1k", "ratio": "1:1"})
        self.assertIs(output[0], result_tensor)
        self.assertEqual(output[1:3], ("https://cdn.test/result.png", "image-task"))


@unittest.skipUnless(
    os.environ.get("ZHENZHEN_IMAGE_G2_LIVE_TEST") == "1"
    and os.environ.get("ZHENZHEN_IMAGE_G2_TEST_API_KEY"),
    "set ZHENZHEN_IMAGE_G2_LIVE_TEST=1 and ZHENZHEN_IMAGE_G2_TEST_API_KEY",
)
class ZhenzhenImageG2LiveTests(unittest.TestCase):
    def test_real_text_to_image_then_image_to_image(self):
        config = {
            "base_url": nodes.DEFAULT_BASE_URL,
            "api_key": os.environ["ZHENZHEN_IMAGE_G2_TEST_API_KEY"],
        }
        node = nodes.Comfly_zhenzhen_image_g2_lowprice()

        t2i = node.generate_image(
            model=nodes.ZHENZHEN_IMAGE_G2_T2I_MODEL,
            prompt="minimal flat blue circle icon centered on a clean white background",
            resolution="1k",
            ratio="1:1",
            api_config=config,
        )
        self.assertEqual(tuple(t2i[0].shape)[0], 1)
        self.assertTrue(t2i[1].startswith("http"))
        self.assertTrue(t2i[2])

        i2i = node.generate_image(
            model=nodes.ZHENZHEN_IMAGE_G2_I2I_MODEL,
            prompt="change the blue circle to red while keeping the white background",
            resolution="1k",
            ratio="1:1",
            api_config=config,
            image1=t2i[0],
        )
        self.assertEqual(tuple(i2i[0].shape)[0], 1)
        self.assertTrue(i2i[1].startswith("http"))
        self.assertTrue(i2i[2])


class ZhenzhenImageG2WorkflowTests(unittest.TestCase):
    def test_workflows_use_current_nodes_and_valid_links(self):
        for filename, expected in WORKFLOW_CASES.items():
            with self.subTest(filename=filename):
                path = ROOT / "workflow" / filename
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("sk-", text)
                data = json.loads(text)
                by_id = {node["id"]: node for node in data["nodes"]}
                config = next(node for node in data["nodes"] if node["type"] == "Comfly_api_set")
                generator = next(
                    node
                    for node in data["nodes"]
                    if node["type"] == "Comfly_zhenzhen_image_g2_lowprice"
                )
                save_image = next(node for node in data["nodes"] if node["type"] == "SaveImage")

                self.assertEqual(config["widgets_values"], ["seedance_low_price", "", "", False])
                self.assertEqual(generator["widgets_values"][0], expected["model"])
                self.assertEqual(generator["widgets_values"][2], "1k")
                self.assertEqual(generator["widgets_values"][-1], False)
                self.assertEqual(
                    [item["name"] for item in generator["inputs"]],
                    ["api_config"] + [f"image{i}" for i in range(1, 11)],
                )
                self.assertIs(
                    nodes.Comfly_zhenzhen_image_g2_lowprice.VALIDATE_INPUTS(
                        model=generator["widgets_values"][0],
                        prompt=generator["widgets_values"][1],
                        resolution=generator["widgets_values"][2],
                        ratio=generator["widgets_values"][3],
                        strict=True,
                    ),
                    True,
                )

                links = {link[0]: link for link in data["links"]}
                config_link = next(
                    link
                    for link in data["links"]
                    if link[1] == config["id"] and link[3] == generator["id"]
                )
                self.assertEqual(
                    config_link[1:],
                    [
                        config["id"],
                        1,
                        generator["id"],
                        0,
                        nodes.CONFIG_TYPE,
                    ],
                )
                image_output_link = next(
                    link
                    for link in data["links"]
                    if link[1] == generator["id"] and link[3] == save_image["id"]
                )
                self.assertEqual(image_output_link[2:], [0, save_image["id"], 0, "IMAGE"])

                image_links = [
                    link
                    for link in data["links"]
                    if link[3] == generator["id"] and link[5] == "IMAGE"
                ]
                self.assertEqual(bool(image_links), expected["image_link"])
                if image_links:
                    self.assertEqual(image_links[0][4], 1)

                for node in data["nodes"]:
                    for item in node.get("inputs", []):
                        if item.get("link") is not None:
                            self.assertIn(item["link"], links)
                            self.assertEqual(links[item["link"]][3], node["id"])
                    for slot, item in enumerate(node.get("outputs", [])):
                        for link_id in item.get("links") or []:
                            self.assertIn(link_id, links)
                            self.assertEqual(links[link_id][1:3], [node["id"], slot])
                self.assertEqual(set(by_id), {node["id"] for node in data["nodes"]})

    def test_registration_and_api_key_button_are_declared(self):
        source = (ROOT / "Comfly.py").read_text(encoding="utf-8")
        self.assertIn('"Comfly_zhenzhen_image_g2_lowprice": Comfly_zhenzhen_image_g2_lowprice', source)
        self.assertIn('"Comfly_zhenzhen_image_g2_lowprice": "zhenzhen-image-g2-lowprice"', source)

        frontend = (ROOT / "web" / "js" / "zhenzhen_image_g2_api_key_link.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("Comfly_zhenzhen_image_g2_lowprice", frontend)
        self.assertIn("贞贞的平价AI小屋（国内版）ApiKey获取", frontend)
        self.assertIn("https://api.seedance.nz/sign-up?aff=5f4w", frontend)


if __name__ == "__main__":
    unittest.main()
