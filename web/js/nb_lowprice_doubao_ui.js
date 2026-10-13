import { app } from "../../../scripts/app.js";
import { resizeZhenzhenNode, setZhenzhenInputVisible, setZhenzhenWidgetVisible } from "./dynamic_widget_ui.js";

const NB = "T8Zhenzhen_NB_Dual_LowPrice";
const VOICE = "T8Zhenzhen_Doubao_Voice_Clone_ICL_LowPrice";
const STANDARD_SIZES = ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"];
const CLONE_FIELDS = ["audio_url", "custom_speaker_id", "language", "reference_text", "enable_audio_denoise", "disable_volume_normalization"];
const SYNTH_FIELDS = ["speaker", "voice_model", "output_format", "sample_rate", "speech_rate", "loudness_rate", "pitch", "explicit_language"];
const ADVANCED_FIELDS = ["bit_rate", "max_length_to_filter_parenthesis", "silence_duration", "enable_subtitle", "disable_markdown_filter",
    "disable_emoji_filter", "enable_latex_tn", "aigc_watermark", "disable_default_bit_rate", "tone_fidelity", "aigc_metadata_enable",
    "latex_parser", "section_id", "aigc_metadata_content_producer", "aigc_metadata_produce_id", "aigc_metadata_content_propagator", "aigc_metadata_propagate_id"];
const INSTALLED = Symbol("zhenzhenNBLowpriceDoubaoUI");
const originalName = (value) => String(value ?? "").replace(/^ComflyConcurrent_(.*)_Submit$/, "$1");

function refresh(node, kind) {
    const widget = (name) => node.widgets?.find((item) => item.name === name);
    if (kind === NB) {
        const sizes = widget("model")?.value === "zhenzhen-image-nb-2.1-lowprice"
            ? [...STANDARD_SIZES, "1:4", "4:1", "1:8", "8:1"] : STANDARD_SIZES;
        const size = widget("size");
        if (size && !String(size.type).startsWith("converted-widget")) {
            size.options ??= {};
            size.options.values = [...sizes];
            if (!sizes.includes(size.value)) size.value = "1:1";
        }
        const last = Math.max(0, ...(node.inputs ?? []).filter((slot) => /^image\d+$/.test(slot.name) && slot.link != null)
            .map((slot) => Number(slot.name.slice(5))));
        for (const input of node.inputs ?? []) {
            if (/^image\d+$/.test(input.name)) setZhenzhenInputVisible(node, input, Number(input.name.slice(5)) <= last + 1);
        }
    } else {
        const clone = widget("model")?.value !== "doubao-seed-icl-2.0";
        const advanced = Boolean(widget("advanced_mode")?.value);
        CLONE_FIELDS.forEach((name) => setZhenzhenWidgetVisible(widget(name), clone));
        SYNTH_FIELDS.forEach((name) => setZhenzhenWidgetVisible(widget(name), !clone));
        ADVANCED_FIELDS.forEach((name) => setZhenzhenWidgetVisible(widget(name), !clone && advanced));
        setZhenzhenWidgetVisible(widget("training_speaker_id"), clone && advanced);
        setZhenzhenWidgetVisible(widget("context_texts"), !clone && widget("voice_model")?.value === "api_default");
        for (const input of node.inputs ?? []) {
            if (input.name === "reference_audio") setZhenzhenInputVisible(node, input, clone);
        }
    }
    let row = 0;
    const start = Number(node.constructor?.slot_start_y) || 0;
    for (const input of node.inputs ?? []) {
        if (!input.hidden || input.link != null) input.pos = [10, start + (row++ + .7) * 20];
        else delete input.pos;
    }
    resizeZhenzhenNode(node, kind === NB ? 440 : 480);
}

function schedule(node, kind) {
    if (node.zhenzhenNBDoubaoFrame != null) cancelAnimationFrame(node.zhenzhenNBDoubaoFrame);
    node.zhenzhenNBDoubaoFrame = requestAnimationFrame(() => {
        node.zhenzhenNBDoubaoFrame = null;
        refresh(node, kind);
    });
}

function install(node, kind) {
    if (node[INSTALLED]) return;
    node[INSTALLED] = true;
    const compute = node.computeSize;
    node.computeSize = function () {
        // The modern inputs setter mutates arrays, so retain a complete copy.
        const all = [...(this.inputs ?? [])];
        try {
            this.inputs = all.filter((input) => !input.hidden || input.link != null);
            return compute?.apply(this, arguments);
        } finally {
            this.inputs = all;
        }
    };
    for (const name of ["model", "advanced_mode", "voice_model"]) {
        const widget = node.widgets?.find((item) => item.name === name);
        if (!widget) continue;
        const callback = widget.callback;
        widget.callback = function () {
            const result = callback?.apply(this, arguments);
            schedule(node, kind);
            return result;
        };
    }
    schedule(node, kind);
}

app.registerExtension({
    name: "ComfyuiZhenzhen.NBLowpriceDoubaoUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const kind = originalName(nodeData.name);
        if (![NB, VOICE].includes(kind)) return;
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
    nodeCreated(node) {
        const kind = originalName(node.comfyClass ?? node.constructor?.comfyClass ?? node.type);
        if ([NB, VOICE].includes(kind)) install(node, kind);
    },
});
