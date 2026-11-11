import { app } from "../../../scripts/app.js";
import { enableZhenzhenConcreteInputVisibility, resizeZhenzhenNode, setZhenzhenInputVisible, setZhenzhenWidgetVisible } from "./dynamic_widget_ui.js";

const FAMILIES = { T8Zhenzhen_Tripo_Generate_LowPrice: "generate", T8Zhenzhen_Tripo_Texture_LowPrice: "texture", T8Zhenzhen_Tripo_Retopology_LowPrice: "retopology",
    T8Zhenzhen_Tripo_Mesh_LowPrice: "mesh", T8Zhenzhen_Tripo_Convert_LowPrice: "convert", T8Zhenzhen_Tripo_Splat_LowPrice: "splat" };
const INSTALLED = Symbol("zhenzhenTripoUI");

function refresh(node, family) {
    const widgets = node.widgets ?? [];
    const widget = (name) => widgets.find((item) => item.name === name);
    const value = (name) => widget(name)?.value;
    const show = (names, visible) => names.forEach((name) => setZhenzhenWidgetVisible(widget(name), visible));
    const model = String(value("model") ?? "");
    let images = 0, minimum = 1, style = false;
    if (family === "generate") {
        const text = model.includes("text-to-3d"), multi = model.includes("multiview");
        const h3 = model.startsWith("tripo-h-v3.0") || model.startsWith("tripo-h-v3.1");
        const p1 = model.startsWith("tripo-p-p1"), p2 = model.startsWith("tripo-p-p2");
        const textured = value("texture") !== "false" || value("pbr") !== "false";
        show(["prompt", "negative_prompt", "image_seed"], text);
        show(["enable_image_autofix"], !text && !multi);
        show(["geometry_quality", "smart_low_poly", "generate_parts"], h3);
        show(["quad"], h3 || p2);
        show(["auto_size", "compress"], h3 || p1 || p2);
        show(["texture_quality"], (h3 || p1 || p2) && textured);
        show(["texture_alignment", "orientation"], !text && textured);
        show(["texture_seed"], textured);
        show(["input_mode"], multi);
        const reuse = multi && value("input_mode") === "multiviewTaskId";
        show(["multiview_task_id"], reuse);
        images = text || reuse ? 0 : multi ? 4 : 1;
        minimum = multi ? 2 : 1;
        const face = widget("face_limit");
        if (face?.options) {
            const quad = value("quad") === "true";
            face.options.max = p1 ? 20000 : p2 ? (quad ? 25000 : 50000) : h3 && quad ? 150000
                : h3 && value("geometry_quality") === "detailed" ? 2000000 : model.includes("v2.5") ? 500000
                : model.includes("v3.0") ? 1000000 : 1500000;
        }
    } else if (family === "texture") {
        const mode = value("texture_prompt_mode");
        show(["texture_prompt_text", "style_image_url"], mode === "text");
        show(["texture_image_url"], mode === "image");
        show(["texture_front_image_url", "texture_left_image_url", "texture_back_image_url", "texture_right_image_url"], mode === "images");
        show(["compress"], model.endsWith("v3.0"));
        style = mode === "text";
        images = mode === "image" ? 1 : mode === "images" ? 4 : 0;
        minimum = images;
    } else if (family === "retopology") {
        show(["bake", "part_names"], model.endsWith("v2"));
    } else if (family === "mesh") {
        const smart = model.endsWith("smartsegment"), complete = model.endsWith("complete"), v2 = model.endsWith("segment-v2");
        const image = smart && value("seg_type") !== "model";
        show(["model_url"], !complete && !image);
        show(["seg_type", "granularity", "hint"], smart);
        show(["image_url"], image);
        show(["transform"], smart && !image);
        show(["ref_image_url"], v2);
        const localRef = node.inputs?.some((input) => input.name === "image1" && input.link != null);
        show(["segmentation_granularity", "split_by_connectivity"], v2 && !value("ref_image_url") && !localRef);
        show(["tripo_segment_task_id", "completion_mode", "part_names"], complete);
        images = image || v2 ? 1 : 0;
    } else if (family === "convert") {
        show(["force_symmetry"], value("quad") === "true");
        show(["flatten_bottom_threshold"], value("flatten_bottom") === "true");
        show(["export_vertex_colors"], ["OBJ", "GLTF"].includes(value("format")));
        show(["fbx_preset"], value("format") === "FBX");
    } else if (family === "splat") {
        images = 1;
    }
    if (family === "generate" && images === 4) {
        for (const input of node.inputs ?? []) {
            if (/^image[1-4]$/.test(input.name) && input.link != null) minimum = Math.max(minimum, Number(input.name.slice(5)) + 1);
        }
    }
    for (const input of node.inputs ?? []) {
        if (/^image[1-4]$/.test(input.name)) setZhenzhenInputVisible(node, input, Number(input.name.slice(5)) <= Math.min(images, minimum));
        if (input.name === "style_image") setZhenzhenInputVisible(node, input, style);
    }
    let row = 0;
    for (const input of node.inputs ?? []) {
        if (!input.hidden || input.link != null) input.pos = [10, (row++ + .7) * 20];
        else delete input.pos;
    }
    resizeZhenzhenNode(node, 540);
}

function install(node, family) {
    if (node[INSTALLED]) return;
    node[INSTALLED] = true;
    enableZhenzhenConcreteInputVisibility(node);
    node.zhenzhenTripoRefresh = () => {
        if (node.zhenzhenTripoFrame != null) cancelAnimationFrame(node.zhenzhenTripoFrame);
        node.zhenzhenTripoFrame = requestAnimationFrame(() => { node.zhenzhenTripoFrame = null; refresh(node, family); });
    };
    for (const field of ["model", "texture_prompt_mode", "input_mode", "seg_type", "quad", "texture", "pbr", "geometry_quality", "format", "flatten_bottom", "ref_image_url"]) {
        const widget = node.widgets?.find((item) => item.name === field);
        if (!widget) continue;
        const callback = widget.callback;
        widget.callback = function (...args) { const result = callback?.apply(this, args); node.zhenzhenTripoRefresh(); return result; };
    }
    node.zhenzhenTripoRefresh();
}

app.registerExtension({
    name: "ComfyuiZhenzhen.TripoUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const family = FAMILIES[nodeData.name];
        if (!family) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () { const result = created?.apply(this, arguments); install(this, family); return result; };
        for (const hook of ["onConfigure", "onConnectionsChange", "onAfterGraphConfigured"]) {
            const previous = nodeType.prototype[hook];
            nodeType.prototype[hook] = function () { const result = previous?.apply(this, arguments); this.zhenzhenTripoRefresh?.(); return result; };
        }
    },
    async nodeCreated(node) {
        const family = FAMILIES[node.comfyClass ?? node.constructor?.comfyClass ?? node.type];
        if (family) install(node, family);
    },
});
