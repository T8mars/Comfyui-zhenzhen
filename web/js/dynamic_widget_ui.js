const CONVERTED_WIDGET_PREFIX = "converted-widget";
const HIDDEN_WIDGET_TYPE = `${CONVERTED_WIDGET_PREFIX}:seedance-hidden`;
const HIDDEN_INPUT_WIDGET = "__seedance_hidden_input__";
const HIDDEN_OFFSET = -100000;
const ORIGINAL_WIDGET = Symbol("zhenzhenDynamicOriginalWidget");
const ORIGINAL_INPUT = Symbol("zhenzhenDynamicOriginalInput");
const ORIGINAL_CONCRETE_INPUT = Symbol("zhenzhenDynamicOriginalConcreteInput");
const INPUT_PATCHED = Symbol("zhenzhenDynamicInputPatched");
const CONCRETE_PATCHED = Symbol("zhenzhenDynamicConcretePatched");
const SERIALIZE_PATCHED = Symbol("zhenzhenDynamicSerializePatched");

function isExternallyConverted(widget) {
    const type = String(widget?.type ?? "");
    return Boolean(
        widget?.origType
        || (type.startsWith(CONVERTED_WIDGET_PREFIX) && type !== HIDDEN_WIDGET_TYPE)
    );
}

export function setSeedanceWidgetVisible(widget, visible) {
    if (!widget || isExternallyConverted(widget)) {
        return false;
    }
    if (!widget[ORIGINAL_WIDGET]) {
        widget[ORIGINAL_WIDGET] = {
            type: widget.type,
            computeSize: widget.computeSize,
        };
    }
    const original = widget[ORIGINAL_WIDGET];
    const nextType = visible ? original.type : HIDDEN_WIDGET_TYPE;
    const nextComputeSize = visible ? original.computeSize : (() => [0, -4]);
    const changed = widget.type !== nextType || widget.computeSize !== nextComputeSize;
    widget.type = nextType;
    widget.computeSize = nextComputeSize;
    return changed;
}

function installInputVisibility(node) {
    if (!node || node[INPUT_PATCHED]) {
        return;
    }
    const originalGetConnectionPos = node.getConnectionPos;
    if (typeof originalGetConnectionPos === "function") {
        node.getConnectionPos = function (isInput, slotNumber, out) {
            const input = isInput ? this.inputs?.[slotNumber] : null;
            if (input?.hidden && input.link == null) {
                const result = out ?? new Float32Array(2);
                result[0] = Number(this.pos?.[0] ?? 0) + HIDDEN_OFFSET;
                result[1] = Number(this.pos?.[1] ?? 0) + HIDDEN_OFFSET;
                return result;
            }
            if (isInput) {
                const inputs = this.inputs ?? [];
                const visible = inputs.filter((item) => !item.hidden || item.link != null);
                const visibleSlot = visible.indexOf(input);
                if (visibleSlot >= 0 && visible.length !== inputs.length) {
                    this.inputs = visible;
                    try {
                        return originalGetConnectionPos.call(this, true, visibleSlot, out);
                    } finally {
                        this.inputs = inputs;
                    }
                }
            }
            return originalGetConnectionPos.apply(this, arguments);
        };
    }

    const originalComputeSize = node.computeSize;
    if (typeof originalComputeSize === "function") {
        node.computeSize = function () {
            const inputs = this.inputs ?? [];
            const visible = inputs.filter((item) => !item.hidden || item.link != null);
            if (visible.length === inputs.length) {
                return originalComputeSize.apply(this, arguments);
            }
            this.inputs = visible;
            try {
                return originalComputeSize.apply(this, arguments);
            } finally {
                this.inputs = inputs;
            }
        };
    }
    node[INPUT_PATCHED] = true;
}

function syncConcreteInputVisibility(node) {
    const inputs = node?.inputs ?? [];
    const concreteInputs = node?._concreteInputs;
    if (!Array.isArray(concreteInputs)) {
        return;
    }
    concreteInputs.forEach((concreteInput, index) => {
        const input = inputs.find((candidate) => candidate?.name === concreteInput?.name)
            ?? inputs[index];
        if (!input || !concreteInput) {
            return;
        }
        if (!concreteInput[ORIGINAL_CONCRETE_INPUT]) {
            const hiddenPlaceholder = concreteInput.widget?.name === HIDDEN_INPUT_WIDGET;
            concreteInput[ORIGINAL_CONCRETE_INPUT] = {
                hadWidget: Boolean(concreteInput.widget && !hiddenPlaceholder),
                widget: hiddenPlaceholder ? undefined : concreteInput.widget,
                alwaysVisible: concreteInput.alwaysVisible,
                pos: concreteInput.pos,
            };
        }
        const original = concreteInput[ORIGINAL_CONCRETE_INPUT];
        if (input.hidden && input.link == null) {
            concreteInput.widget = { name: HIDDEN_INPUT_WIDGET };
            concreteInput.alwaysVisible = false;
            concreteInput.pos = [HIDDEN_OFFSET, HIDDEN_OFFSET];
        } else {
            if (original.hadWidget) {
                concreteInput.widget = original.widget;
            } else {
                delete concreteInput.widget;
            }
            concreteInput.alwaysVisible = original.hadWidget
                ? original.alwaysVisible
                : true;
            concreteInput.hidden = false;
            concreteInput.pos = input.pos ?? original.pos;
        }
    });
}

function installConcreteInputVisibility(node) {
    if (!node || node[CONCRETE_PATCHED]) {
        return;
    }
    const originalSetConcreteSlots = node._setConcreteSlots;
    if (typeof originalSetConcreteSlots === "function") {
        node._setConcreteSlots = function () {
            const result = originalSetConcreteSlots.apply(this, arguments);
            syncConcreteInputVisibility(this);
            return result;
        };
    }
    const originalDrawSlots = node.drawSlots;
    if (typeof originalDrawSlots === "function") {
        node.drawSlots = function () {
            syncConcreteInputVisibility(this);
            return originalDrawSlots.apply(this, arguments);
        };
    }
    node[CONCRETE_PATCHED] = true;
    syncConcreteInputVisibility(node);
}

function installSerializationCleanup(node) {
    if (!node || node[SERIALIZE_PATCHED]) {
        return;
    }
    const originalOnSerialize = node.onSerialize;
    node.onSerialize = function (serialized) {
        const result = originalOnSerialize?.apply(this, arguments);
        for (const [index, input] of (this.inputs ?? []).entries()) {
            const original = input?.[ORIGINAL_INPUT];
            const saved = serialized?.inputs?.[index];
            if (!original || !saved) {
                continue;
            }
            if (original.hadWidget) {
                saved.widget = original.widget;
            } else {
                delete saved.widget;
            }
            if (original.hadPosition) {
                saved.pos = [...original.position];
            } else {
                delete saved.pos;
            }
            delete saved.hidden;
        }
        return result;
    };
    node[SERIALIZE_PATCHED] = true;
}

export function setSeedanceInputVisible(node, input, visible) {
    if (!node || !input) {
        return false;
    }
    installInputVisibility(node);
    installConcreteInputVisibility(node);
    installSerializationCleanup(node);
    if (!input[ORIGINAL_INPUT]) {
        input[ORIGINAL_INPUT] = {
            hadWidget: Object.prototype.hasOwnProperty.call(input, "widget"),
            widget: input.widget,
            hadPosition: Array.isArray(input.pos) || ArrayBuffer.isView(input.pos),
            position: input.pos ? Array.from(input.pos) : null,
        };
    }
    const shouldShow = Boolean(visible || input.link != null);
    const hidden = !shouldShow;
    const changed = Boolean(input.hidden) !== hidden;
    const original = input[ORIGINAL_INPUT];
    input.hidden = hidden;
    if (hidden) {
        input.widget = { name: HIDDEN_INPUT_WIDGET };
        input.pos = [HIDDEN_OFFSET, HIDDEN_OFFSET];
    } else {
        if (original.hadWidget) {
            input.widget = original.widget;
        } else {
            delete input.widget;
        }
        if (original.hadPosition) {
            input.pos = [...original.position];
        } else {
            delete input.pos;
        }
    }
    syncConcreteInputVisibility(node);
    return changed;
}

export function resizeSeedanceNode(node, minimumWidth = 430) {
    if (!node) {
        return;
    }
    if (node.zhenzhenDynamicResizeFrame != null) {
        cancelAnimationFrame(node.zhenzhenDynamicResizeFrame);
    }
    node.zhenzhenDynamicResizeFrame = requestAnimationFrame(() => {
        node.zhenzhenDynamicResizeFrame = null;
        const computed = node.computeSize?.();
        if (!computed) {
            return;
        }
        node.setSize?.([
            Math.max(Number(node.size?.[0]) || 0, Number(computed[0]) || 0, minimumWidth),
            Math.max(Number(computed[1]) || 0, 120),
        ]);
        node.setDirtyCanvas?.(true, true);
    });
}
