import { app } from "../../../scripts/app.js";
import { enableZhenzhenConcreteInputVisibility, resizeZhenzhenNode, setZhenzhenInputVisible, setZhenzhenWidgetVisible } from "./dynamic_widget_ui.js";

const PREFIX = "T8Zhenzhen_Kling_V4_";
const NAMES = new Set(["T2V", "I2V", "Omni", "Custom_Element", "Custom_Voice"].map((kind) => `${PREFIX}${kind}_LowPrice`));
const INSTALLED = Symbol("zhenzhenKling4UI");
const originalName = (value) => String(value ?? "").replace(/^ComflyConcurrent_(.*)_Submit$/, "$1");

function progressive(node, prefix, max, minimum = 1) {
    const pattern = new RegExp(`^${prefix}[1-9][0-9]*$`);
    const highest = Math.max(minimum - 1, ...(node.inputs ?? [])
        .filter((input) => pattern.test(input.name) && input.link != null).map((input) => Number(input.name.slice(prefix.length))));
    const visible = Math.min(max, highest + 1);
    for (const input of node.inputs ?? []) {
        if (pattern.test(input.name)) setZhenzhenInputVisible(node, input, Number(input.name.slice(prefix.length)) <= visible);
    }
}

function refresh(node, name) {
    const widget = (key) => node.widgets?.find((item) => item.name === key);
    if (name === `${PREFIX}Custom_Element_LowPrice`) {
        const video = widget("reference_type")?.value === "video_refer";
        for (const input of node.inputs ?? []) {
            if (/^image[1-4]$/.test(input.name)) setZhenzhenInputVisible(node, input, !video);
            if (input.name === "input_video") setZhenzhenInputVisible(node, input, video);
        }
        setZhenzhenWidgetVisible(widget("video_url"), video);
        if (!video) progressive(node, "image", 4, 2);
    } else if (name === `${PREFIX}Custom_Voice_LowPrice`) {
        const audio = widget("source_mode")?.value !== "video_id";
        setZhenzhenWidgetVisible(widget("audio_url"), audio);
        setZhenzhenWidgetVisible(widget("video_id"), !audio);
        for (const input of node.inputs ?? []) {
            if (input.name === "audio") setZhenzhenInputVisible(node, input, audio);
        }
    } else if (name === `${PREFIX}Omni_LowPrice`) {
        progressive(node, "image", 10);
        progressive(node, "video", 5);
    }
    let row = 0;
    const start = Number(node.constructor?.slot_start_y) || 0;
    for (const input of node.inputs ?? []) {
        if (!input.hidden || input.link != null) input.pos = [10, start + (row++ + .7) * 20];
        else delete input.pos;
    }
    resizeZhenzhenNode(node, 500);
}

function schedule(node, name) {
    if (node.zhenzhenKling4Frame != null) cancelAnimationFrame(node.zhenzhenKling4Frame);
    node.zhenzhenKling4Frame = requestAnimationFrame(() => {
        node.zhenzhenKling4Frame = null;
        refresh(node, name);
    });
}

function install(node, name) {
    if (node[INSTALLED]) return;
    node[INSTALLED] = true;
    enableZhenzhenConcreteInputVisibility(node);
    const compute = node.computeSize;
    node.computeSize = function () {
        // Modern input setters mutate arrays, so restore a separate complete copy.
        const all = [...(this.inputs ?? [])];
        try {
            this.inputs = all.filter((input) => !input.hidden || input.link != null);
            return compute?.apply(this, arguments);
        } finally {
            this.inputs = all;
        }
    };
    for (const key of ["reference_type", "source_mode"]) {
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
    name: "ComfyuiZhenzhen.Kling4UI",
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
            for (const input of data?.inputs ?? []) {
                delete input.hidden;
                delete input.pos;
            }
            return result;
        };
    },
    nodeCreated(node) {
        const name = originalName(node.comfyClass ?? node.constructor?.comfyClass ?? node.type);
        if (NAMES.has(name)) install(node, name);
    },
});
