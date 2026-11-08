import { app } from "../../../scripts/app.js";
import { enableZhenzhenConcreteInputVisibility, resizeZhenzhenNode, setZhenzhenInputVisible, setZhenzhenWidgetVisible } from "./dynamic_widget_ui.js";

const NAME = "T8Zhenzhen_GPT_Image_2_6_Workshop";
const INSTALLED = Symbol("zhenzhenGpt26WorkshopUI");
const original = (value) => String(value ?? "").replace(/^ComflyConcurrent_(.*)_Submit$/, "$1");

function refresh(node) {
    const widget = (name) => node.widgets?.find((item) => item.name === name);
    const custom = widget("size")?.value === "custom";
    for (const name of ["custom_width", "custom_height"]) setZhenzhenWidgetVisible(widget(name), custom);
    const editing = node.inputs?.some((input) => /^image\d+$/.test(input.name) && input.link != null);
    setZhenzhenWidgetVisible(widget("output_compression"), !editing && ["jpeg", "webp"].includes(widget("output_format")?.value));
    for (const name of ["poll_interval", "max_poll_time"]) setZhenzhenWidgetVisible(widget(name), widget("async_mode")?.value !== false);
    const highest = Math.max(0, ...(node.inputs ?? []).filter((item) => /^image\d+$/.test(item.name) && item.link != null).map((item) => Number(item.name.slice(5))));
    let row = 0;
    for (const input of node.inputs ?? []) {
        if (/^image\d+$/.test(input.name)) setZhenzhenInputVisible(node, input, Number(input.name.slice(5)) <= Math.min(16, highest + 1));
        if (!input.hidden || input.link != null) input.pos = [10, (row++ + .7) * 20];
        else delete input.pos;
    }
    resizeZhenzhenNode(node, 540);
}

function schedule(node) {
    if (node.zhenzhenGpt26Frame != null) cancelAnimationFrame(node.zhenzhenGpt26Frame);
    node.zhenzhenGpt26Frame = requestAnimationFrame(() => { node.zhenzhenGpt26Frame = null; refresh(node); });
}

function install(node) {
    if (node[INSTALLED]) return;
    node[INSTALLED] = true;
    enableZhenzhenConcreteInputVisibility(node);
    const compute = node.computeSize;
    node.computeSize = function () {
        const all = [...(this.inputs ?? [])];
        try { this.inputs = all.filter((input) => !input.hidden || input.link != null); return compute?.apply(this, arguments); }
        finally { this.inputs = all; }
    };
    for (const name of ["size", "output_format", "async_mode"]) {
        const widget = node.widgets?.find((item) => item.name === name);
        if (!widget) continue;
        const callback = widget.callback;
        widget.callback = function () { const result = callback?.apply(this, arguments); schedule(node); return result; };
    }
    schedule(node);
}

app.registerExtension({
    name: "ComfyuiZhenzhen.GptImage26WorkshopUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (original(nodeData.name) !== NAME) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () { const result = created?.apply(this, arguments); install(this); return result; };
        for (const hook of ["onConfigure", "onConnectionsChange", "onAfterGraphConfigured"]) {
            const previous = nodeType.prototype[hook];
            nodeType.prototype[hook] = function () { const result = previous?.apply(this, arguments); schedule(this); return result; };
        }
        const serialize = nodeType.prototype.onSerialize;
        nodeType.prototype.onSerialize = function (data) {
            const result = serialize?.apply(this, arguments);
            for (const input of data?.inputs ?? []) { delete input.hidden; delete input.pos; }
            return result;
        };
    },
    nodeCreated(node) { if (original(node.comfyClass ?? node.type) === NAME) install(node); },
});
