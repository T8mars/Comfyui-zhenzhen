import { app } from "../../../scripts/app.js";
const originalSeedanceNodeName = (value) => String(value ?? "").replace(/^ComflyConcurrent_(.*)_Submit$/, "$1");
import { resizeZhenzhenNode, setZhenzhenInputVisible, setZhenzhenWidgetVisible } from "./dynamic_widget_ui.js";

const KEYS = new Set(["T8Zhenzhen_Minimax_H3_ComfyUI_CharSwap_LowPrice", "T8Zhenzhen_Minimax_H3_ComfyUI_Wuxi_LowPrice", "T8Zhenzhen_Minimax_H3_ComfyUI_Max_10020_LowPrice", "T8Zhenzhen_Minimax_H3_ComfyUI_Max_10021_LowPrice"]);
const INSTALLED = Symbol("seedanceH3ComfyUI");

function refresh(node, key) {
    const widget = (name) => node.widgets?.find((item) => item.name === name);
    const charswap = key === "T8Zhenzhen_Minimax_H3_ComfyUI_CharSwap_LowPrice";
    for (const family of ["image", "video", "audio"]) {
        const inputs = (node.inputs ?? []).filter((input) => new RegExp(`^${family}\\d+$`).test(input.name));
        const index = (input) => Number(input.name.slice(family.length));
        const limit = charswap && family === "image" ? 3 : Infinity;
        const linked = inputs.filter((input) => input.link != null);
        const last = Math.max(0, ...linked.map(index).filter((i) => i <= limit));
        for (const input of inputs) setZhenzhenInputVisible(node, input, linked.length < limit && index(input) <= Math.min(limit, last + 1));
    }
    if (charswap) {
        const frames = widget("duration_mode")?.value === "frames";
        setZhenzhenWidgetVisible(widget("seconds"), !frames);
        setZhenzhenWidgetVisible(widget("frames"), frames);
        const resolution = widget("resolution")?.value, ratio = widget("ratio");
        const values = resolution === "auto" ? ["auto"] : ["auto", "16:9", "9:16", ...(resolution === "768p" ? ["1:1", "4:3", "3:4", "21:9"] : [])];
        if (ratio) {
            ratio.options ??= {}; ratio.options.values = values;
            if (!values.includes(ratio.value) && !Object.hasOwn(ratio, "origType") && !node.inputs?.some((input) => input.name === "ratio" && input.link != null)) ratio.value = "auto";
        }
    }
    resizeZhenzhenNode(node, 500);
}

function install(node, key) {
    if (node[INSTALLED]) return;
    node[INSTALLED] = true;
    node.seedanceH3ComfyRefresh = () => {
        if (node.seedanceH3ComfyFrame != null) cancelAnimationFrame(node.seedanceH3ComfyFrame);
        node.seedanceH3ComfyFrame = requestAnimationFrame(() => { node.seedanceH3ComfyFrame = null; refresh(node, key); });
    };
    for (const field of ["duration_mode", "resolution"]) {
        const widget = node.widgets?.find((item) => item.name === field);
        if (!widget) continue;
        const previous = widget.callback;
        widget.callback = function (...args) { const result = previous?.apply(this, args); node.seedanceH3ComfyRefresh(); return result; };
    }
    node.seedanceH3ComfyRefresh();
}

app.registerExtension({
    name: "ComfyuiZhenzhen.H3ComfyUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const key = originalSeedanceNodeName(nodeData.name);
        if (!KEYS.has(key)) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () { const result = created?.apply(this, arguments); install(this, key); return result; };
        for (const hook of ["onConfigure", "onConnectionsChange", "onAfterGraphConfigured"]) {
            const previous = nodeType.prototype[hook];
            nodeType.prototype[hook] = function () { const result = previous?.apply(this, arguments); this.seedanceH3ComfyRefresh?.(); return result; };
        }
    },
    async nodeCreated(node) {
        const key = originalSeedanceNodeName(node.comfyClass ?? node.constructor?.comfyClass ?? node.type);
        if (KEYS.has(key)) install(node, key);
    },
});
