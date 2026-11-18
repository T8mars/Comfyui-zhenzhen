import { app } from "../../../scripts/app.js";
const originalSeedanceNodeName = (value) => String(value ?? "").replace(/^ComflyConcurrent_(.*)_Submit$/, "$1");
import {
    resizeZhenzhenNode, setZhenzhenInputVisible, setZhenzhenWidgetVisible,
} from "./dynamic_widget_ui.js";

const KEYS = new Set(["T8Zhenzhen_Kling_V4_Image_LowPrice", "T8Zhenzhen_MAI_Image_27_LowPrice", "T8Zhenzhen_Qwen_Audio_31_TTS_LowPrice"]);
const INSTALLED = Symbol("seedanceNov19Controls");

function progressive(node, family, enabled = true) {
    const slots = (node.inputs ?? []).filter((slot) => new RegExp(`^${family}[0-9]+$`).test(slot.name));
    const index = (slot) => Number(slot.name.slice(family.length));
    const last = Math.max(0, ...slots.filter((slot) => slot.link != null).map(index));
    for (const slot of slots) setZhenzhenInputVisible(node, slot, slot.link != null || enabled && index(slot) <= last + 1);
    return last !== 0;
}

function refresh(node, key, voiceProfiles) {
    const widget = (name) => node.widgets?.find((item) => item.name === name);
    const editable = (name) => {
        const item = widget(name), type = String(item?.type ?? "");
        return item && !Object.hasOwn(item, "origType")
            && (!type.startsWith("converted-widget") || type === "converted-widget:zhenzhen-hidden")
            && !node.inputs?.some((input) => input.name === name && input.link != null);
    };
    const show = (name, visible) => setZhenzhenWidgetVisible(widget(name), visible);
    const combo = (name, values, fallback = values[0]) => {
        const item = widget(name);
        if (!item) return;
        item.options ??= {};
        item.options.values = values;
        if (editable(name) && !values.includes(item.value)) item.value = fallback;
    };
    if (key === "T8Zhenzhen_Kling_V4_Image_LowPrice") {
        progressive(node, "image");
        const grouped = widget("sequential_image_generation")?.value === "auto";
        show("n", !grouped);
        show("max_images", grouped);
    } else if (key === "T8Zhenzhen_MAI_Image_27_LowPrice") {
        const edit = progressive(node, "image"), size = widget("size")?.value;
        show("size", !edit);
        show("resolution", !edit && size !== "custom_pixels");
        show("custom_ratio", !edit && size === "custom_ratio");
        for (const field of ["width", "height"]) show(field, !edit && size === "custom_pixels");
    } else {
        const model = String(widget("model")?.value ?? "qwen-audio-3.1-tts-flash");
        const next = model.endsWith("-next"), plus = model.endsWith("-plus");
        const def = "api_default";
        progressive(node, "audio", next);
        const voices = voiceProfiles[model];
        if (voices) combo("voice", [def, ...voices]);
        combo("language_hint", [def, ...(plus ? "zh en fr de ja ko ru pt th id vi es it ms fil ar".split(" ") : ["zh", "en"])]);
        combo("output_format", next ? [def, "wav", "mp3", "pcm"] : [def, "mp3", "wav", "pcm", "opus"]);
        const format = widget("output_format")?.value;
        const rates = next ? [def, "8000", "16000", "24000", "44100", "48000"]
            : [def, "8000", "12000", "16000", "22050", "24000", "44100", "48000"];
        combo("sample_rate", format === "opus" ? rates.filter((rate) => ![def, "22050", "44100"].includes(rate)) : rates,
            format === "opus" ? "24000" : def);
        for (const field of ["voice", "instruction", "language_hint", "pitch", "enable_ssml"]) show(field, !next);
        show("channels", next);
        show("enable_cbr", next && format === "mp3");
        show("audio_urls", next || Boolean(String(widget("audio_urls")?.value ?? "").trim()));
        const seed = widget("seed");
        if (seed) {
            seed.options ??= {};
            seed.options.max = next ? 2147483647 : 65535;
            if (editable("seed") && seed.value > seed.options.max) seed.value = -1;
        }
    }
    resizeZhenzhenNode(node, 510);
}

app.registerExtension({
    name: "ComfyuiZhenzhen.NovemberImageAudioUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const key = originalSeedanceNodeName(nodeData.name);
        if (!KEYS.has(key)) return;
        const profiles = nodeData.input?.required?.voice?.[1]?.zhenzhen_voice_profiles ?? {};
        const schedule = (node) => {
            if (node.seedanceNov19Frame != null) cancelAnimationFrame(node.seedanceNov19Frame);
            node.seedanceNov19Frame = requestAnimationFrame(() => {
                node.seedanceNov19Frame = null;
                refresh(node, key, profiles);
            });
        };
        const previous = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = previous?.apply(this, args);
            if (!this[INSTALLED]) {
                this[INSTALLED] = true;
                for (const name of ["model", "size", "sequential_image_generation", "output_format", "audio_urls"]) {
                    const widget = this.widgets?.find((item) => item.name === name);
                    if (!widget) continue;
                    const callback = widget.callback;
                    widget.callback = (...args) => {
                        const result = callback?.apply(widget, args);
                        schedule(this);
                        return result;
                    };
                }
            }
            schedule(this);
            return result;
        };
        for (const name of ["onConfigure", "onConnectionsChange", "onAfterGraphConfigured"]) {
            const previous = nodeType.prototype[name];
            nodeType.prototype[name] = function (...args) {
                const result = previous?.apply(this, args);
                schedule(this);
                return result;
            };
        }
    },
});
