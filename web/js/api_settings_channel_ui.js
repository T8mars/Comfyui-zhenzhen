import { app } from "../../../scripts/app.js";
import {
    resizeZhenzhenNode,
    setZhenzhenWidgetVisible,
} from "./dynamic_widget_ui.js";

const PRIMARY_SETTINGS_NODE_NAME = "T8Zhenzhen_API_Settings";
const INTERMEDIATE_SETTINGS_NODE_NAME = "Zhenzhen_api_set";
const LEGACY_SETTINGS_NODE_NAME = "Comfly_api_set";
const SETTINGS_NODE_NAMES = new Set([
    PRIMARY_SETTINGS_NODE_NAME,
    INTERMEDIATE_SETTINGS_NODE_NAME,
    LEGACY_SETTINGS_NODE_NAME,
]);
const ZHENZHEN_CHANNELS = new Set(["zhenzhen", "seedance_low_price", "ip"]);
const API_BASE_WIDGET_NAME = "api_base";
const SIGNUP_BUTTON_MARKER = "zhenzhenApiSettingsSignupLink";
const DEFAULT_CHANNEL = "seedance_low_price";

const CHANNEL_SIGNUP = Object.freeze({
    seedance_low_price: Object.freeze({
        label: "注册平价小屋 API ↗",
        url: "https://api.seedance.nz/sign-up?aff=5f4w",
    }),
    zhenzhen: Object.freeze({
        label: "注册 AI 工坊 API ↗",
        url: "https://ai.t8star.org/register?aff=dP7j",
    }),
});

function widgetByName(node, name) {
    return node.widgets?.find((widget) => widget.name === name);
}

function serializedChannel(node) {
    return String(node?.widgets_values?.[0] ?? "");
}

function hasZhenzhenMetadata(node) {
    const properties = node?.properties ?? {};
    const packageId = String(properties.cnr_id ?? properties.aux_id ?? "").toLowerCase();
    if (packageId.includes("zhenzhen")) {
        return true;
    }
    return node?.outputs?.some((output) => (
        output?.name === "api_config"
        || output?.type === "ZHENZHEN_SEEDANCE2_CONFIG"
    )) ?? false;
}

function isZhenzhenLegacyNode(node) {
    if (node?.type === INTERMEDIATE_SETTINGS_NODE_NAME) {
        return true;
    }
    if (node?.type !== LEGACY_SETTINGS_NODE_NAME) {
        return false;
    }

    const channel = serializedChannel(node);
    if (channel === "comfly" || channel === "hk" || channel === "us") {
        return false;
    }
    return ZHENZHEN_CHANNELS.has(channel) && channel !== "ip"
        ? true
        : hasZhenzhenMetadata(node);
}

function migrateLegacySettingsNodes(graphData) {
    for (const node of graphData?.nodes ?? []) {
        if (!isZhenzhenLegacyNode(node)) {
            continue;
        }
        node.type = PRIMARY_SETTINGS_NODE_NAME;
        if (node.properties?.["Node name for S&R"]) {
            node.properties["Node name for S&R"] = PRIMARY_SETTINGS_NODE_NAME;
        }
    }
}

function apiBaseChoices(nodeData) {
    const definition = nodeData?.input?.required?.api_base;
    const choices = Array.isArray(definition) ? definition[0] : null;
    return Array.isArray(choices) ? choices : [];
}

function isOwnSettingsDefinition(nodeData) {
    if (!SETTINGS_NODE_NAMES.has(nodeData?.name)) {
        return false;
    }
    if (nodeData.name !== LEGACY_SETTINGS_NODE_NAME) {
        return true;
    }
    const choices = new Set(apiBaseChoices(nodeData));
    return choices.has("seedance_low_price") && !choices.has("comfly");
}

function signupForNode(node) {
    const apiBase = String(widgetByName(node, API_BASE_WIDGET_NAME)?.value ?? DEFAULT_CHANNEL);
    return CHANNEL_SIGNUP[apiBase] ?? null;
}

function updateButtonLabel(button, label) {
    button.name = label;
    button.label = label;
}

function syncSignupButton(node) {
    const button = node.widgets?.find((widget) => widget[SIGNUP_BUTTON_MARKER]);
    if (!button) {
        return;
    }

    const signup = signupForNode(node);
    const visibilityChanged = setZhenzhenWidgetVisible(button, Boolean(signup));
    if (signup) {
        updateButtonLabel(button, signup.label);
    }

    if (visibilityChanged) {
        resizeZhenzhenNode(node);
    } else {
        node.setDirtyCanvas?.(true, true);
    }
}

function installChannelCallback(node) {
    const apiBaseWidget = widgetByName(node, API_BASE_WIDGET_NAME);
    if (!apiBaseWidget || apiBaseWidget.zhenzhenSignupCallbackInstalled) {
        return;
    }

    const originalCallback = apiBaseWidget.callback;
    apiBaseWidget.callback = function () {
        const result = originalCallback?.apply(this, arguments);
        syncSignupButton(node);
        return result;
    };
    apiBaseWidget.zhenzhenSignupCallbackInstalled = true;
}

function installSignupButton(node) {
    if (node.widgets?.some((widget) => widget[SIGNUP_BUTTON_MARKER])) {
        return;
    }

    const button = node.addWidget("button", CHANNEL_SIGNUP[DEFAULT_CHANNEL].label, null, () => {
        const signup = signupForNode(node);
        if (signup) {
            window.open(signup.url, "_blank", "noopener,noreferrer");
        }
    });
    button.serialize = false;
    button[SIGNUP_BUTTON_MARKER] = true;
}

app.registerExtension({
    name: "ComfyuiZhenzhen.ApiSettingsChannelUi",
    async beforeConfigureGraph(graphData) {
        migrateLegacySettingsNodes(graphData);
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!isOwnSettingsDefinition(nodeData)) {
            return;
        }

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            installSignupButton(this);
            installChannelCallback(this);
            syncSignupButton(this);
            return result;
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalOnConfigure?.apply(this, arguments);
            installChannelCallback(this);
            syncSignupButton(this);
            return result;
        };
    },
});
