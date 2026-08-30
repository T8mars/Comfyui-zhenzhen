import { app } from "../../../scripts/app.js";
import {
    resizeZhenzhenNode,
    setZhenzhenInputVisible,
    setZhenzhenWidgetVisible,
} from "./dynamic_widget_ui.js";

const FLOWMUSIC_NODE_NAME = "Comfly_flowmusic_lowprice";
const ALWAYS_VISIBLE = new Set(["operation", "skip_error"]);
const ACTION_FIELDS = {
    "flowmusic-generation": [
        "version", "sound_prompt", "lyrics", "title", "bpm", "length", "seed",
        "control_after_generate",
    ],
    "flowmusic-lyrics": ["prompt"],
    "flowmusic-upload-audio": ["audio", "audio_url"],
    "flowmusic-extend": [
        "version", "clip_id", "extend_from_s", "extend_s", "instruction", "title",
        "seed", "control_after_generate",
    ],
    "flowmusic-replace": [
        "version", "clip_id", "start_s", "end_s", "instruction", "title", "seed",
        "control_after_generate",
    ],
    "flowmusic-cover": [
        "version", "clip_id", "instruction", "strength", "title", "seed",
        "control_after_generate",
    ],
    "flowmusic-stems": ["clip_id"],
    "flowmusic-download-audio": ["clip_id", "format"],
    "flowmusic-video-clip": ["clip_id", "preset"],
};
const MANAGED_FIELDS = new Set(
    Object.values(ACTION_FIELDS).flat().concat([...ALWAYS_VISIBLE]),
);

function originalNodeName(name) {
    const prefix = "ComflyConcurrent_";
    const suffix = "_Submit";
    if (name.startsWith(prefix) && name.endsWith(suffix)) {
        return name.slice(prefix.length, -suffix.length);
    }
    return name;
}

function widgetByName(node, name) {
    return node.widgets?.find((widget) => widget.name === name);
}

function refreshFlowMusicNode(node) {
    const operation = String(
        widgetByName(node, "operation")?.value ?? "flowmusic-generation",
    );
    const visible = new Set(ACTION_FIELDS[operation] ?? []);
    for (const field of ALWAYS_VISIBLE) {
        visible.add(field);
    }
    for (const widget of node.widgets ?? []) {
        if (MANAGED_FIELDS.has(widget.name)) {
            setZhenzhenWidgetVisible(widget, visible.has(widget.name));
        }
    }
    for (const input of node.inputs ?? []) {
        if (MANAGED_FIELDS.has(input.name)) {
            setZhenzhenInputVisible(node, input, visible.has(input.name));
        }
    }
    resizeZhenzhenNode(node, 420);
}

function wrapRefresh(node) {
    const widget = widgetByName(node, "operation");
    if (!widget || widget.zhenzhenFlowMusicCallback) {
        return;
    }
    const originalCallback = widget.callback;
    widget.callback = (...args) => {
        const result = originalCallback?.apply(widget, args);
        refreshFlowMusicNode(node);
        return result;
    };
    widget.zhenzhenFlowMusicCallback = true;
}

function scheduleRefresh(node) {
    if (node.zhenzhenFlowMusicRefreshFrame != null) {
        cancelAnimationFrame(node.zhenzhenFlowMusicRefreshFrame);
    }
    node.zhenzhenFlowMusicRefreshFrame = requestAnimationFrame(() => {
        node.zhenzhenFlowMusicRefreshFrame = null;
        refreshFlowMusicNode(node);
    });
}

app.registerExtension({
    name: "ComfyuiZhenzhen.FlowMusicActionUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (originalNodeName(nodeData.name) !== FLOWMUSIC_NODE_NAME) {
            return;
        }

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            wrapRefresh(this);
            scheduleRefresh(this);
            return result;
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalOnConfigure?.apply(this, arguments);
            scheduleRefresh(this);
            return result;
        };

        const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const result = originalOnConnectionsChange?.apply(this, arguments);
            scheduleRefresh(this);
            return result;
        };

        const originalOnAfterGraphConfigured = nodeType.prototype.onAfterGraphConfigured;
        nodeType.prototype.onAfterGraphConfigured = function () {
            const result = originalOnAfterGraphConfigured?.apply(this, arguments);
            scheduleRefresh(this);
            return result;
        };
    },
});
