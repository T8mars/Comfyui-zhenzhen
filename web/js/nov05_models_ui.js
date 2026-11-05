import { app } from "../../../scripts/app.js";
import { enableZhenzhenConcreteInputVisibility, resizeZhenzhenNode, setZhenzhenInputVisible, setZhenzhenWidgetVisible } from "./dynamic_widget_ui.js";

const G26 = "T8Zhenzhen_Image_G26_LowPrice";
const KREA = "T8Zhenzhen_Krea_V3_Image_LowPrice";
const TARGETS = new Set([G26, KREA, "T8Zhenzhen_Hitem3D_V2_LowPrice", "T8Zhenzhen_Hitem3D_Portrait_21_LowPrice", "T8Zhenzhen_Meshy_6_Global_LowPrice"]);
const INSTALLED = Symbol("zhenzhenNov05UI");
const original = (name) => String(name ?? "").replace(/^ComflyConcurrent_(.*)_Submit$/, "$1");

function refresh(node, name) {
    const widget = (key) => node.widgets?.find((item) => item.name === key);
    const value = (key) => widget(key)?.value;
    const show = (keys, visible) => keys.forEach((key) => setZhenzhenWidgetVisible(widget(key), visible));
    let maximum;
    if (name === G26) {
        const low = String(value("model")).endsWith("-lowprice"), gif = value("mode") === "gif", custom = value("size") === "custom";
        const size = widget("size"), sizes = ["auto", "1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16", "2:1", "1:2", "21:9", "9:21"];
        if (size?.options) size.options.values = low ? sizes : [...sizes, "custom"];
        if (low && custom && !node.inputs?.some((item) => item.name === "size" && item.link != null)) size.value = "1:1";
        show(["size"], low || !gif);
        show(["width", "height"], !low && !gif && custom);
        show(["resolution"], !low && !gif && !custom);
        show(["quality"], !low);
        show(["complexity", "n", "output_format", "mask_url", "markup_url"], !low && !gif);
        show(["output_compression"], !low && !gif && ["jpeg", "webp"].includes(value("output_format")));
        show(["frame_size", "frame_count", "frame_duration_ms"], !low && gif);
        show(["frame_width", "frame_height"], !low && gif && value("frame_size") === "custom");
        maximum = low ? 2 : gif ? 0 : 16;
    } else if (name === KREA) {
        show(["width", "height"], value("size") === "custom");
        maximum = String(value("model")).endsWith("-i2i") ? 8 : 0;
    } else {
        const text = name === "T8Zhenzhen_Meshy_6_Global_LowPrice" && String(value("model")).endsWith("-text-to-3d");
        show(["prompt", "art_style", "enable_prompt_expansion"], text);
        if (name === "T8Zhenzhen_Meshy_6_Global_LowPrice") show(["should_texture"], !text);
        maximum = text ? 0 : String(value("model")).includes("multi-image") ? 4 : 1;
    }
    const highest = Math.max(0, ...(node.inputs ?? []).filter((item) => /^image\d+$/.test(item.name) && item.link != null).map((item) => Number(item.name.slice(5))));
    const minimum = name !== G26 && name !== KREA && maximum === 4 ? 2 : 1;
    const visible = Math.min(maximum, Math.max(minimum, highest + 1));
    let row = 0;
    for (const input of node.inputs ?? []) {
        if (/^image\d+$/.test(input.name)) setZhenzhenInputVisible(node, input, Number(input.name.slice(5)) <= visible);
        if (!input.hidden || input.link != null) input.pos = [10, (row++ + .7) * 20];
        else delete input.pos;
    }
    resizeZhenzhenNode(node, 500);
}

function schedule(node, name) {
    if (node.zhenzhenNov05Frame != null) cancelAnimationFrame(node.zhenzhenNov05Frame);
    node.zhenzhenNov05Frame = requestAnimationFrame(() => { node.zhenzhenNov05Frame = null; refresh(node, name); });
}

function install(node, name) {
    if (node[INSTALLED]) return;
    node[INSTALLED] = true;
    enableZhenzhenConcreteInputVisibility(node);
    const compute = node.computeSize;
    node.computeSize = function () {
        const inputs = [...(this.inputs ?? [])];
        try { this.inputs = inputs.filter((input) => !input.hidden || input.link != null); return compute?.apply(this, arguments); }
        finally { this.inputs = inputs; }
    };
    for (const key of ["model", "mode", "size", "frame_size", "output_format"]) {
        const widget = node.widgets?.find((item) => item.name === key);
        if (!widget) continue;
        const previous = widget.callback;
        widget.callback = function () { const result = previous?.apply(this, arguments); schedule(node, name); return result; };
    }
    schedule(node, name);
}

app.registerExtension({
    name: "ComfyuiZhenzhen.Nov05ModelsUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const name = original(nodeData.name);
        if (!TARGETS.has(name)) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () { const result = created?.apply(this, arguments); install(this, name); return result; };
        for (const hook of ["onConfigure", "onConnectionsChange", "onAfterGraphConfigured"]) {
            const previous = nodeType.prototype[hook];
            nodeType.prototype[hook] = function () { const result = previous?.apply(this, arguments); schedule(this, name); return result; };
        }
        const serialize = nodeType.prototype.onSerialize;
        nodeType.prototype.onSerialize = function (data) {
            const result = serialize?.apply(this, arguments);
            for (const input of data?.inputs ?? []) { delete input.hidden; delete input.pos; }
            return result;
        };
    },
    nodeCreated(node) { const name = original(node.comfyClass ?? node.constructor?.comfyClass ?? node.type); if (TARGETS.has(name)) install(node, name); },
});
