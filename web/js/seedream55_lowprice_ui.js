import { app } from "../../../scripts/app.js";
const originalSeedanceNodeName = (value) => String(value ?? "").replace(/^ComflyConcurrent_(.*)_Submit$/, "$1");
import { enableZhenzhenConcreteInputVisibility, resizeZhenzhenNode, setZhenzhenInputVisible, setZhenzhenWidgetVisible } from "./dynamic_widget_ui.js";

const KEYS = new Set(["T8Zhenzhen_Seedream_55_Image_LowPrice", "T8Zhenzhen_Seedream_55_Layers_LowPrice", "Comfly_seedance25_standard_low_price", "T8Zhenzhen_Seedance_25_Draft_To_Video_LowPrice"]);
const INSTALLED = Symbol("zhenzhen55UI");

function restoreLegacyDraftWidgets(node, data) {
    const values = data?.widgets_values;
    // Older exports omitted ComfyUI's automatically inserted seed control.
    if (!Array.isArray(values) || typeof values[8] !== "boolean") return;
    const widget = (name) => node.widgets?.find((item) => item.name === name);
    const control = widget("control_after_generate");
    if (!control) return;
    control.value = "fixed";
    widget("skip_error").value = values[8];
    widget("draft").value = typeof values[9] === "boolean" ? values[9] : false;
}

function refresh(node, key) {
    const widget = (name) => node.widgets?.find((item) => item.name === name);
    const value = (name) => widget(name)?.value;
    if (key === "T8Zhenzhen_Seedream_55_Image_LowPrice") {
        const edit = String(value("model")).endsWith("-i2i");
        let last = 0;
        for (const input of node.inputs ?? []) {
            if (/^image\d+$/.test(input.name) && input.link != null) last = Math.max(last, Number(input.name.slice(5)));
        }
        for (const input of node.inputs ?? []) {
            if (/^image\d+$/.test(input.name)) setZhenzhenInputVisible(node, input, edit && Number(input.name.slice(5)) <= Math.min(10, last + 1));
        }
        const custom = value("resolution") === "custom";
        for (const name of ["width", "height"]) setZhenzhenWidgetVisible(widget(name), custom);
        const format = widget("output_format");
        if (format && !String(format.type).startsWith("converted-widget") && !Object.hasOwn(format, "origType")) {
            const allowed = value("background") === "transparent" ? ["png"] : ["png", "jpeg"];
            format.options ??= {};
            format.options.values = allowed;
            if (!allowed.includes(format.value)) { format.value = "png"; format.callback?.("png"); }
        }
    } else if (key === "Comfly_seedance25_standard_low_price") {
        setZhenzhenWidgetVisible(widget("resolution"), !value("draft"));
    }
    resizeZhenzhenNode(node, key === "T8Zhenzhen_Seedance_25_Draft_To_Video_LowPrice" ? 430 : key === "Comfly_seedance25_standard_low_price" ? 440 : 500);
}

function install(node, key) {
    if (node[INSTALLED]) return;
    node[INSTALLED] = true;
    if (key !== "Comfly_seedance25_standard_low_price") enableZhenzhenConcreteInputVisibility(node);
    node.zhenzhen55Refresh = () => {
        if (node.zhenzhen55Frame != null) cancelAnimationFrame(node.zhenzhen55Frame);
        node.zhenzhen55Frame = requestAnimationFrame(() => { node.zhenzhen55Frame = null; refresh(node, key); });
    };
    for (const name of ["model", "resolution", "background", "draft"]) {
        const widget = node.widgets?.find((item) => item.name === name);
        if (!widget) continue;
        const previous = widget.callback;
        widget.callback = function (...args) { const result = previous?.apply(this, args); node.zhenzhen55Refresh(); return result; };
    }
    node.zhenzhen55Refresh();
}

app.registerExtension({
    name: "ComfyuiZhenzhen.Seedream55DraftUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const key = originalSeedanceNodeName(nodeData.name);
        if (!KEYS.has(key)) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () { const result = created?.apply(this, arguments); install(this, key); return result; };
        for (const hook of ["onConfigure", "onConnectionsChange", "onAfterGraphConfigured"]) {
            const previous = nodeType.prototype[hook];
            nodeType.prototype[hook] = function () {
                const result = previous?.apply(this, arguments);
                if (hook === "onConfigure" && key === "Comfly_seedance25_standard_low_price") restoreLegacyDraftWidgets(this, arguments[0]);
                this.zhenzhen55Refresh?.();
                return result;
            };
        }
    },
    async nodeCreated(node) {
        const key = originalSeedanceNodeName(node.comfyClass ?? node.constructor?.comfyClass ?? node.type);
        if (KEYS.has(key)) install(node, key);
    },
});
