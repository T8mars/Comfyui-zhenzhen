"""Generate credential-free image/GIF and native 3D examples."""

import importlib
import json
from pathlib import Path
import sys
import types
import uuid

ROOT = Path(__file__).resolve().parent
package = types.ModuleType("nov05_workflow_plugin")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
plugin = importlib.import_module(package.__name__ + ".nov05_low_price_nodes")
from generate_kling_v4_workflows import Workflow as BaseWorkflow
from generate_qwen21_animate_workflows import inp, out

CLASSES = {"Image_G26": plugin.T8ZhenzhenImageG26, "Z_Image_T2I": plugin.T8ZhenzhenZImage, "Krea_V3_Image": plugin.T8ZhenzhenKreaV3,
           "Hitem3D_V2": plugin.T8ZhenzhenHitem3DV2, "Hitem3D_Portrait_21": plugin.T8ZhenzhenHitem3DPortrait21, "Meshy_6_Global": plugin.T8ZhenzhenMeshy6Global}
KEYS = {name: "T8Zhenzhen_" + name + "_LowPrice" for name in CLASSES}
PROMPT = "An original small blue toy character in a bright mint studio, clean shapes and studio lighting."
GIF_PROMPT = "A red ball visibly bounces in a seamless looping animated GIF, fixed camera, plain white background."


class Workflow(BaseWorkflow):
    def generate(self, kind, values=None, x=440, y=40, concurrent=False):
        cls, values = CLASSES[kind], values or {}
        schema, inputs, widgets = cls.INPUT_TYPES(), [], []
        for group in ("required", "optional"):
            for name, spec in schema[group].items():
                if (kind == "Meshy_6_Global" and name in {"prompt", "art_style", "enable_prompt_expansion"}
                        and not values.get("model", plugin.geometry_contract.MESHY_MODELS[0]).endswith("-text-to-3d")):
                    continue
                if isinstance(spec[0], list) or spec[0] in {"STRING", "INT", "FLOAT", "BOOLEAN"}:
                    widgets.append(values.get(name, spec[1].get("default", "")))
                    if name == "seed":
                        widgets.append("fixed")
                else:
                    inputs.append(inp(name, str(spec[0]), None))
        key = f"ComflyConcurrent_{KEYS[kind]}_Submit" if concurrent else KEYS[kind]
        outputs = [out("task", "COMFLY_IMAGE_FUTURE")] if concurrent else [out(name, str(type_)) for name, type_ in zip(cls.RETURN_NAMES, cls.RETURN_TYPES)]
        item = self.add(key, x, y, inputs=inputs, outputs=outputs, widgets=widgets)
        self.connect(self.nodes[0], 1, item, "api_config")
        return item

    def save_image(self, source, x=1100, y=40):
        item = self.add("SaveImage", x, y, inputs=[inp("images", "IMAGE", None)], widgets=[self.name], core=True, width=310, height=260)
        self.connect(source, 0, item, "images")

    def save_model(self, source):
        preview = self.add("Preview3D", 1080, 40, inputs=[inp("model_file", "FILE_3D", None)], widgets=[], core=True, width=520, height=440)
        save = self.add("SaveGLB", 1080, 570, inputs=[inp("mesh", "FILE_3D", None)], widgets=["3d/" + self.name], core=True, width=370, height=210)
        self.connect(source, 0, preview, "model_file")
        self.connect(source, 0, save, "mesh")

    def document(self):
        result = super().document()
        result["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "zhenzhen-nov05:" + self.name))
        return result


def all_workflows():
    examples = {}
    def save(workflow):
        examples[workflow.name + "-lowprice.json"] = workflow.document()
    def reference(workflow, target, count=1):
        for i in range(1, count + 1):
            item = workflow.load("IMAGE", y=40+(i-1)*650, filename="select_reference.png" if i == 1 else "select_other_view.png")
            workflow.connect(item, 0, target, f"image{i}")
    for model in plugin.image_contract.G26_MODELS:
        for mode in ("text", "edit", "gif"):
            w = Workflow(model + "-" + mode)
            item = w.generate("Image_G26", {"model": model, "mode": "gif" if mode == "gif" else "image",
                "prompt": GIF_PROMPT if mode == "gif" else "Combine both references, preserve the character and blue shirt." if mode == "edit" else PROMPT,
                "quality": "low", "frame_count": 2, "filename_prefix": "zhenzhen/"+model})
            if mode == "edit": reference(w, item, 2)
            if mode != "gif": w.save_image(item)
            save(w)
    for model in plugin.image_contract.KREA_MODELS:
        w = Workflow(model)
        item = w.generate("Krea_V3_Image", {"model": model, "prompt": PROMPT, "seed": 42})
        if model.endswith("-i2i"): reference(w, item)
        w.save_image(item); save(w)
    w = Workflow("z-image-t2i")
    w.save_image(w.generate("Z_Image_T2I", {"prompt": PROMPT, "seed": 42})); save(w)
    w = Workflow("image-g26-gif-concurrent")
    collector = w.add("ComflyConcurrent_Image_Await", 1100, 40,
        inputs=[inp(f"task_{i}", "COMFLY_IMAGE_FUTURE", None) for i in range(1,31)],
        outputs=[out(f"image_{i}", "IMAGE") for i in range(1,31)]+[out("status", "STRING")],
        widgets=["placeholder"], width=650, height=1100)
    for i, model in enumerate(plugin.image_contract.G26_MODELS):
        item = w.generate("Image_G26", {"model": model, "mode": "gif", "prompt": GIF_PROMPT,
            "frame_count": 2, "quality": "low", "filename_prefix": "zhenzhen/"+model}, y=40+1000*i, concurrent=True)
        w.connect(item, 0, collector, f"task_{i+1}")
    save(w)
    for kind in ("Hitem3D_V2", "Hitem3D_Portrait_21", "Meshy_6_Global"):
        cls = CLASSES[kind]
        for model in plugin.geometry_contract.models(cls.FAMILY):
            w = Workflow(model)
            values = {"model": model}
            if cls.FAMILY != "meshy": values["face"] = 100000
            text = model.endswith("-text-to-3d")
            if text:
                values.update(prompt="A simple round ceramic teapot with a short spout, a single curved handle, and a fitted lid.",
                              art_style="realistic", enable_prompt_expansion=False)
            item = w.generate(kind, values)
            if not text:
                reference(w, item, 2 if "multi-image" in model else 1)
            w.save_model(item); save(w)
    return examples


if __name__ == "__main__":
    for name, workflow in all_workflows().items():
        (ROOT / "workflow" / name).write_text(json.dumps(workflow, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"Saved {len(all_workflows())} credential-free examples")
