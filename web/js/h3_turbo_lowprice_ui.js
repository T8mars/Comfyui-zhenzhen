import { app } from "../../../scripts/app.js";
import { enableZhenzhenConcreteInputVisibility, resizeZhenzhenNode, setZhenzhenInputVisible } from "./dynamic_widget_ui.js";

const originalName = (name) => String(name ?? "").replace(/^ComflyConcurrent_(.*)_Submit$/, "$1");
const KEYS = new Set(["T8Zhenzhen_Minimax_H3_ComfyUI_Max_LowPrice", "T8Zhenzhen_Minimax_H3_Image_LowPrice", "T8Zhenzhen_Qwen_Image_21_Turbo_LowPrice"]);
const INSTALLED = Symbol("zhenzhenH3Turbo");

function refresh(node, key) {
    for (const prefix of ["image", "audio"]) {
        const inputs = (node.inputs ?? []).filter((input) => new RegExp(`^${prefix}\\d+$`).test(input.name));
        const last = Math.max(0, ...inputs.filter((input) => input.link != null).map((input) => Number(input.name.slice(prefix.length))));
        for (const input of inputs) setZhenzhenInputVisible(node, input, Number(input.name.slice(prefix.length)) <= last + 1);
    }
    if (key === "T8Zhenzhen_Qwen_Image_21_Turbo_LowPrice") {
        const resolution = node.widgets?.find((widget) => widget.name === "resolution");
        if (resolution && !String(resolution.type).startsWith("converted-widget") && !Object.hasOwn(resolution, "origType")) {
            const edit = node.inputs?.some((input) => /^image\d+$/.test(input.name) && input.link != null);
            resolution.options ??= {};
            resolution.options.values = edit ? ["1k", "2k", "720p"] : ["1k", "2k"];
            if (!resolution.options.values.includes(resolution.value)) { resolution.value = "1k"; resolution.callback?.("1k"); }
        }
    }
    resizeZhenzhenNode(node, 500);
}

function install(node, key) {
    if (node[INSTALLED]) return;
    node[INSTALLED] = true;
    enableZhenzhenConcreteInputVisibility(node);
    node.zhenzhenH3TurboRefresh = () => {
        if (node.zhenzhenH3TurboFrame != null) cancelAnimationFrame(node.zhenzhenH3TurboFrame);
        node.zhenzhenH3TurboFrame = requestAnimationFrame(() => { node.zhenzhenH3TurboFrame = null; refresh(node, key); });
    };
    node.zhenzhenH3TurboRefresh();
}

app.registerExtension({
    name: "ComfyuiZhenzhen.H3TurboUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const key = originalName(nodeData.name);
        if (!KEYS.has(key)) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () { const result = created?.apply(this, arguments); install(this, key); return result; };
        for (const hook of ["onConfigure", "onConnectionsChange", "onAfterGraphConfigured"]) {
            const previous = nodeType.prototype[hook];
            nodeType.prototype[hook] = function () { const result = previous?.apply(this, arguments); this.zhenzhenH3TurboRefresh?.(); return result; };
        }
    },
    async nodeCreated(node) {
        const key = originalName(node.comfyClass ?? node.constructor?.comfyClass ?? node.type);
        if (KEYS.has(key)) install(node, key);
    },
});
