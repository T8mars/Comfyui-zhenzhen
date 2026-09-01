import { app } from "../../../scripts/app.js";

const SUNO_NODE_NAME = "Comfly_suno_music_lowprice";
const CONVERTED_WIDGET_PREFIX = "converted-widget";
const ALWAYS_VISIBLE = new Set(["operation", "skip_error"]);
const AUDIO_FIELDS = [
    "audio1",
    "audio_url1",
    "audio2",
    "audio_url2",
    "audio3",
    "audio_url3",
    "audio4",
    "audio_url4",
];

function originalNodeName(name) {
    const prefix = "ComflyConcurrent_";
    const suffix = "_Submit";
    if (name.startsWith(prefix) && name.endsWith(suffix)) {
        return name.slice(prefix.length, -suffix.length);
    }
    return name;
}

const ACTION_FIELDS = {
    "suno-generation": ["prompt", "version", "custom", "instrumental", "title", "style", "vocal_gender"],
    "suno-lyrics": ["prompt"],
    "suno-upload": ["audio1", "audio_url1"],
    "suno-extend": ["version", "task_id", "audio_index", "continue_at"],
    "suno-cover-song": ["prompt", "version", "task_id", "audio_index"],
    "suno-inspo": ["version", ...AUDIO_FIELDS],
    "suno-mashup": ["prompt", "version", "task_id", "task_id_2"],
    "suno-upsample-tags": ["tags"],
    "suno-sounds": ["prompt", "version"],
    "suno-create-voice": ["audio1", "audio_url1"],
    "suno-stems": ["task_id", "audio_index"],
    "suno-stems-all": ["task_id", "audio_index"],
    "suno-wav": ["task_id", "audio_index"],
    "suno-generate-mp4": ["task_id", "audio_index"],
    "suno-concat": ["task_id", "audio_index"],
    "suno-crop": ["task_id", "audio_index", "start_s", "end_s"],
    "suno-fade-in": ["task_id", "audio_index", "duration_s"],
    "suno-fade-out": ["task_id", "audio_index", "duration_s"],
    "suno-remove-section": ["task_id", "audio_index", "start_s", "end_s"],
    "suno-replace-music": ["version", "task_id", "audio_index", "start_s", "end_s"],
    "suno-adjust-speed": ["task_id", "audio_index", "speed"],
    "suno-remaster": ["version", "task_id", "audio_index"],
    "suno-midi": ["task_id", "audio_index"],
    "suno-bpm": ["task_id", "audio_index"],
    "suno-aligned-lyrics": ["task_id", "audio_index"],
    "suno-persona": ["task_id", "audio_index", "name"],
    "suno-vox": ["task_id", "audio_index"],
    "suno-sample": ["prompt", "version", "task_id", "audio_index", "start_s", "end_s"],
    "suno-add-vocals": ["prompt", "version", "task_id", "audio_index"],
    "suno-add-instrumental": ["prompt", "version", "task_id", "audio_index"],
    "suno-add-stem": ["prompt", "version", "task_id", "audio_index"],
};

const MANAGED_FIELDS = new Set(
    Object.values(ACTION_FIELDS).flat().concat([...ALWAYS_VISIBLE]),
);

function setWidgetVisible(widget, visible) {
    if (!widget || !MANAGED_FIELDS.has(widget.name)) {
        return;
    }
    const isConvertedInput = (
        String(widget.type ?? "").startsWith(CONVERTED_WIDGET_PREFIX)
        || Object.prototype.hasOwnProperty.call(widget, "origType")
    );
    if (isConvertedInput) {
        return;
    }
    if (!widget.zhenzhenSunoOriginal) {
        widget.zhenzhenSunoOriginal = {
            type: widget.type,
            computeSize: widget.computeSize,
        };
    }
    if (visible) {
        widget.type = widget.zhenzhenSunoOriginal.type;
        widget.computeSize = widget.zhenzhenSunoOriginal.computeSize;
    } else {
        widget.type = "hidden";
        widget.computeSize = () => [0, -4];
    }
}

function refreshSunoNode(node) {
    const operationWidget = node.widgets?.find(
        (widget) => widget.name === "operation",
    );
    const operation = String(operationWidget?.value ?? "suno-generation");
    const visibleFields = new Set(ACTION_FIELDS[operation] ?? []);
    for (const name of ALWAYS_VISIBLE) {
        visibleFields.add(name);
    }

    for (const widget of node.widgets ?? []) {
        setWidgetVisible(widget, visibleFields.has(widget.name));
    }
    for (const input of node.inputs ?? []) {
        if (!MANAGED_FIELDS.has(input.name)) {
            continue;
        }
        input.hidden = !visibleFields.has(input.name) && input.link == null;
    }

    requestAnimationFrame(() => {
        const computed = node.computeSize?.();
        if (computed) {
            node.setSize?.([
                Math.max(node.size?.[0] ?? 360, computed[0], 360),
                Math.max(computed[1], 120),
            ]);
        }
        node.setDirtyCanvas?.(true, true);
    });
}

app.registerExtension({
    name: "ComfyuiZhenzhen.SunoActionUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (originalNodeName(nodeData.name) !== SUNO_NODE_NAME) {
            return;
        }

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            const operationWidget = this.widgets?.find(
                (widget) => widget.name === "operation",
            );
            if (operationWidget && !operationWidget.zhenzhenSunoCallback) {
                const originalCallback = operationWidget.callback;
                operationWidget.callback = (...args) => {
                    const callbackResult = originalCallback?.apply(operationWidget, args);
                    refreshSunoNode(this);
                    return callbackResult;
                };
                operationWidget.zhenzhenSunoCallback = true;
            }
            refreshSunoNode(this);
            return result;
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalOnConfigure?.apply(this, arguments);
            refreshSunoNode(this);
            return result;
        };

        const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const result = originalOnConnectionsChange?.apply(this, arguments);
            refreshSunoNode(this);
            return result;
        };
    },
});
