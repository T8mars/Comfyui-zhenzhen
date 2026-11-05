import { app } from "../../../scripts/app.js";
import { enableZhenzhenConcreteInputVisibility, resizeZhenzhenNode, setZhenzhenInputVisible, setZhenzhenWidgetVisible } from "./dynamic_widget_ui.js";

const HY = "T8Zhenzhen_HY_Image_35_Preview_LowPrice";
const FLUX = "T8Zhenzhen_Flux_3_Image_Variants_LowPrice";
const NAMES = new Set([HY, FLUX, "T8Zhenzhen_Muse_Image_LowPrice", "T8Zhenzhen_Muse_Video_LowPrice"]);
const INSTALLED = Symbol("zhenzhenPreviewModelsUI");
const originalName = (value) => String(value ?? "").replace(/^ComflyConcurrent_(.*)_Submit$/, "$1");

function refresh(node, name) {
    const widget = (key) => node.widgets?.find((item) => item.name === key);
    const model = String(widget("model")?.value ?? "flux-3-image-t2i");
    if (name === HY) {
        const custom = widget("size")?.value === "custom";
        for (const key of ["width", "height"]) setZhenzhenWidgetVisible(widget(key), custom);
        setZhenzhenWidgetVisible(widget("resolution"), !custom);
    }
    if (name === FLUX) {
        const klein = model.includes("-klein-");
        setZhenzhenWidgetVisible(widget("grounding"), !klein);
        for (const key of ["steps", "output_format"]) setZhenzhenWidgetVisible(widget(key), klein);
    }
    const maximum = name === HY ? 5 : name === FLUX ? 10 : 9;
    const highest = Math.max(0, ...(node.inputs ?? []).filter((input) => /^image\d+$/.test(input.name) && input.link != null)
        .map((input) => Number(input.name.slice(5))));
    const visible = Math.min(maximum, highest + 1);
    let row = 0;
    const start = Number(node.constructor?.slot_start_y) || 0;
    for (const input of node.inputs ?? []) {
        if (/^image\d+$/.test(input.name)) {
            setZhenzhenInputVisible(node, input, (name !== FLUX || model.endsWith("-i2i")) && Number(input.name.slice(5)) <= visible);
        }
        if (!input.hidden || input.link != null) input.pos = [10, start + (row++ + .7) * 20];
        else delete input.pos;
    }
    resizeZhenzhenNode(node, 500);
}

function schedule(node, name) {
    if (node.zhenzhenPreviewFrame != null) cancelAnimationFrame(node.zhenzhenPreviewFrame);
    node.zhenzhenPreviewFrame = requestAnimationFrame(() => {
        node.zhenzhenPreviewFrame = null;
        refresh(node, name);
    });
}

function install(node, name) {
    if (node[INSTALLED]) return;
    node[INSTALLED] = true;
    enableZhenzhenConcreteInputVisibility(node);
    const compute = node.computeSize;
    node.computeSize = function () {
        const all = [...(this.inputs ?? [])];
        try {
            this.inputs = all.filter((input) => !input.hidden || input.link != null);
            return compute?.apply(this, arguments);
        } finally {
            this.inputs = all;
        }
    };
    for (const key of ["model", "size"]) {
        const widget = node.widgets?.find((item) => item.name === key);
        if (!widget) continue;
        const previous = widget.callback;
        widget.callback = function () {
            const result = previous?.apply(this, arguments);
            schedule(node, name);
            return result;
        };
    }
    schedule(node, name);
}

app.registerExtension({
    name: "ComfyuiZhenzhen.PreviewMuseFluxUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const name = originalName(nodeData.name);
        if (!NAMES.has(name)) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = created?.apply(this, arguments);
            install(this, name);
            return result;
        };
        for (const hook of ["onConfigure", "onConnectionsChange", "onAfterGraphConfigured"]) {
            const previous = nodeType.prototype[hook];
            nodeType.prototype[hook] = function () {
                const result = previous?.apply(this, arguments);
                schedule(this, name);
                return result;
            };
        }
        const serialize = nodeType.prototype.onSerialize;
        nodeType.prototype.onSerialize = function (data) {
            const result = serialize?.apply(this, arguments);
            for (const input of data?.inputs ?? []) { delete input.hidden; delete input.pos; }
            return result;
        };
    },
    nodeCreated(node) {
        const name = originalName(node.comfyClass ?? node.constructor?.comfyClass ?? node.type);
        if (NAMES.has(name)) install(node, name);
    },
});
