import { app } from "../../../scripts/app.js";
import {
    resizeZhenzhenNode,
    setZhenzhenInputVisible,
    setZhenzhenWidgetVisible,
} from "./dynamic_widget_ui.js";

const NODES = new Set([
    "T8Zhenzhen_NB_21_LowPrice",
    "T8Zhenzhen_Flux_3_Image_LowPrice",
    "T8Zhenzhen_Vidu_Q4_Preview_LowPrice",
]);
const INSTALLED = Symbol("zhenzhenNB21FluxViduUI");

function originalName(value) {
    return String(value ?? "").replace(/^ComflyConcurrent_(.*)_Submit$/, "$1");
}

function refresh(node, kind) {
    const vidu = kind === "T8Zhenzhen_Vidu_Q4_Preview_LowPrice";
    const reference = !vidu || String(node.widgets?.find((w) => w.name === "model")?.value).endsWith("-r2v");
    const highest = { image: 0, audio: 0 };
    for (const input of node.inputs ?? []) {
        const match = /^(image|audio)(\d+)$/.exec(input.name);
        if (match && input.link != null) {
            highest[match[1]] = Math.max(highest[match[1]], Number(match[2]));
        }
    }
    for (const input of node.inputs ?? []) {
        const match = /^(image|audio)(\d+)$/.exec(input.name);
        if (match) {
            const family = match[1];
            const visible = reference ? Number(match[2]) <= highest[family] + 1
                : family === "image" && Number(match[2]) === 1;
            setZhenzhenInputVisible(node, input, visible);
        }
    }
    if (vidu) {
        for (const widget of node.widgets ?? []) {
            if (widget.name === "ratio" || /^audio_url[123]$/.test(widget.name)) {
                setZhenzhenWidgetVisible(widget, reference);
            }
        }
    }
    const start = Number(node.constructor?.slot_start_y) || 0;
    let row = 0;
    for (const input of node.inputs ?? []) {
        if (!input.hidden || input.link != null) {
            input.pos = [10, start + (row + .7) * 20];
            row += 1;
        } else {
            delete input.pos;
        }
    }
    resizeZhenzhenNode(node, 440);
}

function schedule(node, kind) {
    if (node.zhenzhenNewModelsFrame != null) {
        cancelAnimationFrame(node.zhenzhenNewModelsFrame);
    }
    node.zhenzhenNewModelsFrame = requestAnimationFrame(() => {
        node.zhenzhenNewModelsFrame = null;
        refresh(node, kind);
    });
}

function install(node, kind) {
    if (node[INSTALLED]) return;
    node[INSTALLED] = true;
    const compute = node.computeSize;
    node.computeSize = function () {
        // Modern ComfyUI setters mutate inputs in place; preserve a copy.
        const all = [...(this.inputs ?? [])];
        try {
            this.inputs = all.filter((input) => !input.hidden || input.link != null);
            return compute?.apply(this, arguments);
        } finally {
            this.inputs = all;
        }
    };
    const model = node.widgets?.find((widget) => widget.name === "model");
    if (model) {
        const callback = model.callback;
        model.callback = (...args) => {
            const result = callback?.apply(model, args);
            schedule(node, kind);
            return result;
        };
    }
    schedule(node, kind);
}

app.registerExtension({
    name: "ComfyuiZhenzhen.NB21FluxViduUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const kind = originalName(nodeData.name);
        if (!NODES.has(kind)) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = created?.apply(this, arguments);
            install(this, kind);
            return result;
        };
        for (const name of ["onConfigure", "onConnectionsChange", "onAfterGraphConfigured"]) {
            const original = nodeType.prototype[name];
            nodeType.prototype[name] = function () {
                const result = original?.apply(this, arguments);
                schedule(this, kind);
                return result;
            };
        }
        const serialize = nodeType.prototype.onSerialize;
        nodeType.prototype.onSerialize = function (data) {
            const result = serialize?.apply(this, arguments);
            for (const input of data?.inputs ?? []) {
                delete input.hidden;
                delete input.pos;
            }
            return result;
        };
    },
    async nodeCreated(node) {
        const kind = originalName(node.comfyClass ?? node.constructor?.comfyClass ?? node.type);
        if (NODES.has(kind)) install(node, kind);
    },
});
