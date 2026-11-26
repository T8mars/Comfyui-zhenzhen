import { app } from "../../../scripts/app.js";
import { resizeZhenzhenNode, setZhenzhenInputVisible, setZhenzhenWidgetVisible } from "./dynamic_widget_ui.js";

const kindOf = (name) => {
    const key = String(name ?? "").replace(/^ComflyConcurrent_(.*)_Submit$/, "$1");
    if (key === "T8Zhenzhen_Kling_V4_Long_Image_LowPrice") return "long";
    if (key === "T8Zhenzhen_Miora_3D_LowPrice") return "miora";
    if (key === "T8Zhenzhen_HeyGen_Avatar_6_LowPrice") return "heygen";
    if (key === "Comfly_zhenzhen_image_gk_v15_lowprice") return "gk-v15";
    if (key === "T8Zhenzhen_Minimax_H3_ComfyUI_CharSwap_Token_LowPrice") return "h3-charswap";
    if (/^T8Zhenzhen_Minimax_H3_ComfyUI_.*_Token_LowPrice$/.test(key)) return "h3";
    return null;
};
const REFRESH = Symbol("zhenzhenNov21Refresh");

function refresh(node, kind) {
    const widget = (name) => node.widgets?.find((item) => item.name === name);
    const input = (name) => node.inputs?.find((item) => item.name === name);
    const connected = (name) => input(name)?.link != null;
    const show = (name, visible) => setZhenzhenWidgetVisible(widget(name), visible);
    const progressive = (family, enabled = true, limit = Infinity) => {
        const slots = (node.inputs ?? []).filter((slot) => new RegExp(`^${family}\\d+$`).test(slot.name));
        const index = (slot) => Number(slot.name.slice(family.length));
        const linked = slots.filter((slot) => slot.link != null);
        const last = Math.max(0, ...linked.map(index).filter((i) => i <= limit));
        for (const slot of slots) setZhenzhenInputVisible(node, slot,
            enabled && linked.length < limit && index(slot) <= Math.min(limit, last + 1));
        return linked.length > 0;
    };
    if (kind === "long") {
        const webpage = widget("skill")?.value === "webpage";
        progressive("image", !webpage || connected("skill"));
        for (const name of ["style_image", "subject_image"]) {
            setZhenzhenInputVisible(node, input(name), webpage || connected("skill"));
        }
        show("length", !webpage || connected("skill"));
    } else if (kind === "gk-v15") {
        progressive("image", widget("model")?.value === "zhenzhen-image-gk-v15-edit" || connected("model"));
    } else if (kind === "h3" || kind === "h3-charswap") {
        for (const family of ["image", "audio", "video"]) {
            progressive(family, true, kind === "h3-charswap" && family === "image" ? 3 : Infinity);
        }
        if (widget("duration_mode")) {
            const frames = widget("duration_mode").value === "frames";
            show("seconds", !frames || connected("duration_mode"));
            show("frames", frames || connected("duration_mode"));
        }
    } else if (kind === "heygen") {
        const driven = connected("audio") || Boolean(String(widget("audio_url")?.value ?? "").trim());
        show("prompt", !driven);
        show("voice", !driven);
    } else if (kind === "miora") {
        const hasImage = progressive("image");
        show("prompt", !hasImage);
        show("enable_pbr", widget("generate_type")?.value !== "geometry" || connected("generate_type"));
    }
    resizeZhenzhenNode(node, 500);
}

function install(node, kind) {
    if (node[REFRESH]) return;
    let frame;
    node[REFRESH] = () => {
        if (frame != null) cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => { frame = null; refresh(node, kind); });
    };
    for (const name of ["skill", "duration_mode", "audio_url", "generate_type", ...(kind === "gk-v15" ? ["model"] : [])]) {
        const widget = node.widgets?.find((item) => item.name === name);
        if (!widget) continue;
        const previous = widget.callback;
        widget.callback = function (...args) {
            const result = previous?.apply(this, args);
            node[REFRESH]();
            return result;
        };
    }
    node[REFRESH]();
}

app.registerExtension({
    name: "ComfyuiZhenzhen.NovemberLongImageVideo3D",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const kind = kindOf(nodeData.name);
        if (!kind) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args);
            install(this, kind);
            return result;
        };
        for (const hook of ["onConfigure", "onConnectionsChange", "onAfterGraphConfigured"]) {
            const previous = nodeType.prototype[hook];
            nodeType.prototype[hook] = function (...args) {
                const result = previous?.apply(this, args);
                this[REFRESH]?.();
                return result;
            };
        }
    },
    async nodeCreated(node) {
        const kind = kindOf(node.comfyClass ?? node.constructor?.comfyClass ?? node.type);
        if (kind) install(node, kind);
    },
});
