import { app } from "../../../scripts/app.js";
import {
    resizeZhenzhenNode,
    setZhenzhenInputVisible,
    setZhenzhenWidgetVisible,
} from "./dynamic_widget_ui.js";

const WAN_NODE_NAME = "Comfly_wan_2_7_global_image_lowprice";
const QWEN_TTS_NODE_NAME = "Comfly_qwen3_tts_lowprice";
const MINIMAX_AUDIO_NODE_NAME = "Comfly_minimax_audio_lowprice";

const MINIMAX_MUSIC_FIELDS = new Set([
    "model", "prompt", "lyrics", "is_instrumental", "lyrics_optimizer",
    "output_format", "sample_rate", "bitrate", "seed", "control_after_generate",
]);
const MINIMAX_SPEECH_FIELDS = new Set([
    "model", "prompt", "voice_id", "speed", "volume", "pitch",
    "language_boost", "output_format", "sample_rate", "bitrate", "channel",
    "seed", "control_after_generate",
]);
const MINIMAX_CLONE_FIELDS = new Set([
    "model", "prompt", "custom_voice_id", "clone_target_model",
    "need_noise_reduction", "need_volume_normalization", "seed",
    "control_after_generate",
]);

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

function refreshWan(node) {
    const model = String(widgetByName(node, "model")?.value ?? "wan-2.7-global-t2i");
    const isT2I = model.endsWith("-t2i");
    for (const name of ["width", "height", "thinking_mode"]) {
        setZhenzhenWidgetVisible(widgetByName(node, name), isT2I);
    }
    for (const input of node.inputs ?? []) {
        if (/^image[1-9]$/.test(input.name)) {
            setZhenzhenInputVisible(node, input, !isT2I);
        }
    }
    resizeZhenzhenNode(node, 400);
}

function refreshQwenTTS(node) {
    const model = String(widgetByName(node, "model")?.value ?? "qwen3-tts-flash");
    const isInstruct = model === "qwen3-tts-instruct-flash";
    setZhenzhenWidgetVisible(widgetByName(node, "instructions"), isInstruct);
    setZhenzhenWidgetVisible(widgetByName(node, "optimize_instructions"), isInstruct);
    resizeZhenzhenNode(node, 400);
}

function refreshMinimaxAudio(node) {
    const model = String(widgetByName(node, "model")?.value ?? "minimax-speech-2.8-turbo");
    const fields = model === "minimax-music-2.6"
        ? MINIMAX_MUSIC_FIELDS
        : (model === "minimax-voice-clone" ? MINIMAX_CLONE_FIELDS : MINIMAX_SPEECH_FIELDS);
    const dynamicNames = new Set([
        "lyrics", "is_instrumental", "lyrics_optimizer", "voice_id", "speed",
        "volume", "pitch", "language_boost", "output_format", "sample_rate",
        "bitrate", "channel", "custom_voice_id", "clone_target_model",
        "need_noise_reduction", "need_volume_normalization",
    ]);
    for (const widget of node.widgets ?? []) {
        if (["model", "prompt"].includes(widget.name) || fields.has(widget.name)) {
            setZhenzhenWidgetVisible(widget, true);
        } else if (dynamicNames.has(widget.name)) {
            setZhenzhenWidgetVisible(widget, false);
        }
    }
    for (const input of node.inputs ?? []) {
        if (input.name === "reference_audio") {
            setZhenzhenInputVisible(node, input, model === "minimax-voice-clone");
        }
    }
    resizeZhenzhenNode(node, 420);
}

function wrapRefreshWidget(node, name, refresh) {
    const widget = widgetByName(node, name);
    const marker = `zhenzhenLatestModelCallback_${name}`;
    if (!widget || widget[marker]) {
        return;
    }
    const originalCallback = widget.callback;
    widget.callback = (...args) => {
        const result = originalCallback?.apply(widget, args);
        refresh(node);
        return result;
    };
    widget[marker] = true;
}

function scheduleRefresh(node, refresh) {
    if (node.zhenzhenLatestModelRefreshFrame != null) {
        cancelAnimationFrame(node.zhenzhenLatestModelRefreshFrame);
    }
    node.zhenzhenLatestModelRefreshFrame = requestAnimationFrame(() => {
        node.zhenzhenLatestModelRefreshFrame = null;
        refresh(node);
    });
}

app.registerExtension({
    name: "ComfyuiZhenzhen.LatestImageAudioUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const refresh = {
            [WAN_NODE_NAME]: refreshWan,
            [QWEN_TTS_NODE_NAME]: refreshQwenTTS,
            [MINIMAX_AUDIO_NODE_NAME]: refreshMinimaxAudio,
        }[originalNodeName(nodeData.name)];
        if (!refresh) {
            return;
        }

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            wrapRefreshWidget(this, "model", refresh);
            scheduleRefresh(this, refresh);
            return result;
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalOnConfigure?.apply(this, arguments);
            scheduleRefresh(this, refresh);
            return result;
        };

        const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const result = originalOnConnectionsChange?.apply(this, arguments);
            scheduleRefresh(this, refresh);
            return result;
        };

        const originalOnAfterGraphConfigured = nodeType.prototype.onAfterGraphConfigured;
        nodeType.prototype.onAfterGraphConfigured = function () {
            const result = originalOnAfterGraphConfigured?.apply(this, arguments);
            scheduleRefresh(this, refresh);
            return result;
        };
    },
});
