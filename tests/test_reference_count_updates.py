"""GK edit and H3 CharSwap reference limits and legacy wiring."""

from unittest import TestCase
from unittest.mock import patch

from nov08_fixture import api, module

comfy_h3 = module("h3_comfy_low_price_nodes")
token_h3 = module("nov21_low_price_nodes")
GK = api.Comfly_zhenzhen_image_gk_v15_lowprice
IMAGE = api.torch.zeros((1, 16, 16, 3))
VIDEO_URL = "https://example.test/source.mp4"


class ReferenceCountTests(TestCase):
    def test_gk_payload_requires_one_to_five_for_edit_only(self):
        build = api.build_zhenzhen_image_gk_v15_payload
        urls = [f"https://example.test/image{i}.png" for i in range(1, 7)]
        edit, text = api.ZHENZHEN_IMAGE_GK_V15_EDIT_MODEL, api.ZHENZHEN_IMAGE_GK_V15_MODEL
        for count in (1, 5):
            self.assertEqual(build(edit, "Edit", "1:1", 1, urls[:count])["images"], urls[:count])
        for items in ([], urls):
            with self.assertRaisesRegex(api.SeedanceLowPriceError, "1-5 reference images"):
                build(edit, "Edit", "1:1", 1, items)
        self.assertNotIn("images", build(text, "Create", "1:1", 1))
        with self.assertRaisesRegex(api.SeedanceLowPriceError, "does not accept reference images"):
            build(text, "Create", "1:1", 1, urls[:1])
        self.assertTrue(GK.VALIDATE_INPUTS(model=edit, prompt=None, size="1:1", image1=None))

    def test_gk_node_uploads_five_images_in_socket_order(self):
        urls = [f"https://example.test/image{i}.png" for i in range(1, 6)]
        final = {"data": {"status": "SUCCESS", "result_url": "https://example.test/result.png"}}
        with (patch.object(api, "resolve_config", return_value={}),
              patch.object(api, "upload_media", side_effect=urls) as upload,
              patch.object(api, "submit_image_task", return_value=("test-task", {})) as submit,
              patch.object(api, "poll_image_task", return_value=final),
              patch.object(api, "download_image", return_value=IMAGE)):
            output = GK().generate_image(api.ZHENZHEN_IMAGE_GK_V15_EDIT_MODEL, "Edit", "1:1", 1,
                                         **{f"image{i}": IMAGE for i in range(5, 0, -1)})
        self.assertEqual([call.args[1] for call in upload.call_args_list],
                         [f"zhenzhen_image_gk_v15_reference_{i}.png" for i in range(1, 6)])
        self.assertEqual(submit.call_args.args[0]["images"], urls)
        self.assertIs(output[0], IMAGE)
        self.assertEqual(list(GK.INPUT_TYPES()["optional"])[:2], ["image1", "api_config"])

    def test_charswap_receives_three_images_and_keeps_legacy_video_slots(self):
        for cls, last in [(comfy_h3.CLASSES["charswap"], 9), (token_h3.CLASSES["charswap"], 5)]:
            with self.subTest(node=cls.__name__):
                optional = cls.INPUT_TYPES()["optional"]
                self.assertEqual(list(optional).index("video1"), last)
                values = {"prompt": "Replace the character using <Picture 3>.", "image1": IMAGE,
                          "image3": IMAGE, f"image{last}": IMAGE, "video_urls": VIDEO_URL}
                self.assertIs(cls.VALIDATE_INPUTS(**values, strict=True), True)
                self.assertIn("At most 3", cls.VALIDATE_INPUTS(**values, image2=IMAGE, strict=True))
                if last == 9:
                    encoded = comfy_h3.contracts.encode_media("charswap", values)
                    self.assertEqual([entry[0] for entry in encoded], ["image1", "image3", "image9"])
                    urls = [f"https://example.test/r{i}.png" for i in (1, 3, 9)]
                    body = comfy_h3.contracts.payload("charswap", values, urls, [], [VIDEO_URL])
                    self.assertEqual(body["images"], urls)
                else:
                    body, encoded = cls().prepare(values)
                    self.assertEqual([entry[1] for entry in encoded], ["image1.png", "image3.png", "image5.png"])
                    self.assertEqual(body["metadata"]["video_url"], [VIDEO_URL])
