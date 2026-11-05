const CONVERTED_WIDGET_PREFIX = "converted-widget";
const DYNAMIC_HIDDEN_WIDGET_TYPE = `${CONVERTED_WIDGET_PREFIX}:zhenzhen-hidden`;
const ORIGINAL_WIDGET_STATE = Symbol("zhenzhenDynamicWidgetOriginal");
const INPUT_POSITION_STATE = Symbol("zhenzhenDynamicInputPosition");
const HIDDEN_WIDGET_SIZE = () => [0, -4];
const HIDDEN_INPUT_OFFSET = -100000;
const CONCRETE_VISIBILITY_STATE = Symbol("zhenzhenConcreteVisibility");
const INPUT_WIDGET_STATE = Symbol("zhenzhenHiddenInputWidget");
const CONCRETE_WIDGET_STATE = Symbol("zhenzhenConcreteWidget");
const HIDDEN_INPUT_WIDGET = "__zhenzhen_hidden_input__";

function hasOwn(object, property) {
    return Object.prototype.hasOwnProperty.call(object ?? {}, property);
}

function isExternalConvertedWidget(widget) {
    const type = String(widget?.type ?? "");
    return (
        hasOwn(widget, "origType")
        || (
            type.startsWith(CONVERTED_WIDGET_PREFIX)
            && type !== DYNAMIC_HIDDEN_WIDGET_TYPE
        )
    );
}

export function setZhenzhenWidgetVisible(widget, visible) {
    if (!widget || isExternalConvertedWidget(widget)) {
        return false;
    }
    if (!widget[ORIGINAL_WIDGET_STATE]) {
        widget[ORIGINAL_WIDGET_STATE] = {
            type: widget.type,
            computeSize: widget.computeSize,
        };
    }
    const original = widget[ORIGINAL_WIDGET_STATE];
    const nextType = visible ? original.type : DYNAMIC_HIDDEN_WIDGET_TYPE;
    const nextComputeSize = visible ? original.computeSize : HIDDEN_WIDGET_SIZE;
    const changed = (
        widget.type !== nextType
        || widget.computeSize !== nextComputeSize
    );
    widget.type = nextType;
    widget.computeSize = nextComputeSize;
    return changed;
}

function installInputPositioning(node) {
    if (!node || node[INPUT_POSITION_STATE]) {
        return;
    }
    const originalGetConnectionPos = node.getConnectionPos;
    if (typeof originalGetConnectionPos !== "function") {
        return;
    }
    node.getConnectionPos = function (isInput, slotNumber, out) {
        const input = isInput ? this.inputs?.[slotNumber] : null;
        if (input?.hidden && input.link == null) {
            const result = out ?? new Float32Array(2);
            result[0] = Number(this.pos?.[0] ?? 0) + HIDDEN_INPUT_OFFSET;
            result[1] = Number(this.pos?.[1] ?? 0) + HIDDEN_INPUT_OFFSET;
            return result;
        }
        return originalGetConnectionPos.apply(this, arguments);
    };
    node[INPUT_POSITION_STATE] = true;
}

export function setZhenzhenInputVisible(node, input, visible) {
    if (!node || !input) {
        return false;
    }
    installInputPositioning(node);
    const shouldShow = Boolean(visible || input.link != null);
    const nextHidden = !shouldShow;
    const changed = Boolean(input.hidden) !== nextHidden;
    input.hidden = nextHidden;
    return changed;
}

export function enableZhenzhenConcreteInputVisibility(node) {
    // Opt-in for new nodes only; legacy nodes retain their existing UI behavior.
    if (!node || node[CONCRETE_VISIBILITY_STATE]) return;
    node[CONCRETE_VISIBILITY_STATE] = true;
    const sync = () => {
        const inputs = node.inputs ?? [];
        for (const input of inputs) {
            if (typeof input.hidden !== "boolean") continue;
            input[INPUT_WIDGET_STATE] ??= { widget: input.widget };
            if (input.hidden && input.link == null) {
                input.widget = { name: HIDDEN_INPUT_WIDGET };
                input.pos = [HIDDEN_INPUT_OFFSET, HIDDEN_INPUT_OFFSET];
            } else if (input.widget?.name === HIDDEN_INPUT_WIDGET) {
                if (input[INPUT_WIDGET_STATE].widget) input.widget = input[INPUT_WIDGET_STATE].widget;
                else delete input.widget;
            }
        }
        for (const concrete of node._concreteInputs ?? []) {
            const input = inputs.find((candidate) => candidate.name === concrete.name);
            if (!input || typeof input.hidden !== "boolean") continue;
            if (!concrete[CONCRETE_WIDGET_STATE]) {
                const widget = concrete.widget?.name === HIDDEN_INPUT_WIDGET ? input[INPUT_WIDGET_STATE]?.widget : concrete.widget;
                concrete[CONCRETE_WIDGET_STATE] = { widget, alwaysVisible: concrete.alwaysVisible };
            }
            const original = concrete[CONCRETE_WIDGET_STATE];
            if (input.hidden && input.link == null) {
                concrete.widget = { name: HIDDEN_INPUT_WIDGET };
                concrete.alwaysVisible = false;
                concrete.pos = [HIDDEN_INPUT_OFFSET, HIDDEN_INPUT_OFFSET];
            } else {
                if (original.widget) concrete.widget = original.widget;
                else delete concrete.widget;
                concrete.alwaysVisible = original.widget ? original.alwaysVisible : true;
                concrete.hidden = false;
                concrete.pos = input.pos;
            }
        }
    };
    for (const name of ["_setConcreteSlots", "drawSlots"]) {
        const original = node[name];
        if (typeof original !== "function") continue;
        node[name] = function () {
            if (name === "drawSlots") sync();
            const result = original.apply(this, arguments);
            if (name !== "drawSlots") sync();
            return result;
        };
    }
    const serialize = node.onSerialize;
    node.onSerialize = function (data) {
        const result = serialize?.apply(this, arguments);
        for (const saved of data?.inputs ?? []) {
            const input = (this.inputs ?? []).find((candidate) => candidate.name === saved.name);
            const original = input?.[INPUT_WIDGET_STATE];
            if (!original) continue;
            if (original.widget) saved.widget = { name: original.widget.name };
            else delete saved.widget;
            delete saved.hidden;
            delete saved.pos;
        }
        return result;
    };
    sync();
}

export function resizeZhenzhenNode(node, minimumWidth = 320) {
    if (!node) {
        return;
    }
    if (node.zhenzhenDynamicResizeFrame != null) {
        cancelAnimationFrame(node.zhenzhenDynamicResizeFrame);
    }
    node.zhenzhenDynamicResizeFrame = requestAnimationFrame(() => {
        node.zhenzhenDynamicResizeFrame = null;
        const computed = node.computeSize?.();
        if (computed) {
            const currentWidth = Number(node.size?.[0]) || minimumWidth;
            node.setSize?.([
                Math.max(currentWidth, Number(computed[0]) || 0, minimumWidth),
                Math.max(Number(computed[1]) || 0, 120),
            ]);
        }
        node.setDirtyCanvas?.(true, true);
    });
}

export const zhenzhenDynamicWidgetInternals = Object.freeze({
    convertedWidgetPrefix: CONVERTED_WIDGET_PREFIX,
    hiddenWidgetType: DYNAMIC_HIDDEN_WIDGET_TYPE,
    hiddenInputOffset: HIDDEN_INPUT_OFFSET,
});
