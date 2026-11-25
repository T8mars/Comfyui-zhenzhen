import { app } from "../../../scripts/app.js";
import { resizeZhenzhenNode, setZhenzhenInputVisible } from "./dynamic_widget_ui.js";

const KEY = "T8Zhenzhen_Magi_2_Video_LowPrice";
const matches = (name) => String(name ?? "").replace(/^ComflyConcurrent_(.*)_Submit$/, "$1") === KEY;
const REFRESH = Symbol("zhenzhenMagi2Refresh");
const REFERENCE = /^(image|video|audio)(\d+)$/;

function refresh(node) {
    const linked = node.inputs?.some((slot) => slot.name === "generation_type" && slot.link != null);
    const mode = linked ? "auto" : node.widgets?.find((widget) => widget.name === "generation_type")?.value;
    const slots = (node.inputs ?? []).flatMap((slot) => {
        const match = REFERENCE.exec(slot.name);
        return match ? [{ slot, family: match[1], index: Number(match[2]) }] : [];
    });
    const last = { image: 0, video: 0, audio: 0 };
    for (const { slot, family, index } of slots) {
        if (slot.link != null) last[family] = Math.max(last[family], index);
    }
    for (const { slot, family, index } of slots) {
        const cap = mode === "text" ? 0 : mode === "frame" ? (family === "image" ? 2 : 0) : Infinity;
        slot.label = mode === "frame" && family === "image" && index <= 2
            ? `${slot.name} (${index === 1 ? "首帧" : "尾帧"})` : slot.name;
        setZhenzhenInputVisible(node, slot, index <= Math.min(cap, last[family] + 1));
    }
    resizeZhenzhenNode(node, 500);
}

function install(node) {
    if (node[REFRESH]) return;
    let frame;
    node[REFRESH] = () => {
        if (frame != null) cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => { frame = null; refresh(node); });
    };
    const widget = node.widgets?.find((item) => item.name === "generation_type");
    if (widget) {
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
    name: "ComfyuiZhenzhen.Magi2",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!matches(nodeData.name)) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args);
            install(this);
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
        if (matches(node.comfyClass ?? node.constructor?.comfyClass ?? node.type)) install(node);
    },
});
