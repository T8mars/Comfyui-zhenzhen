import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";


const testDir = path.dirname(fileURLToPath(import.meta.url));
const sourcePath = path.join(
    testDir,
    "..",
    "web",
    "js",
    "api_settings_channel_ui.js",
);
const source = fs.readFileSync(sourcePath, "utf8").replace(
    /^import[\s\S]*?;\s*/gm,
    "",
);

let extension = null;
const context = {
    app: {
        registerExtension(value) {
            extension = value;
        },
    },
    resizeZhenzhenNode() {},
    setZhenzhenWidgetVisible() {
        return false;
    },
    window: { open() {} },
};

vm.runInNewContext(
    `${source}\n;globalThis.__zhenzhenApiSettingsProbe = {`
    + "migrateLegacySettingsNodes, isOwnSettingsDefinition};",
    context,
    { filename: sourcePath },
);

const {
    migrateLegacySettingsNodes,
    isOwnSettingsDefinition,
} = context.__zhenzhenApiSettingsProbe;
const graph = {
    nodes: [
        {
            type: "Zhenzhen_api_set",
            widgets_values: ["seedance_low_price"],
            properties: { "Node name for S&R": "Zhenzhen_api_set" },
        },
        {
            type: "Comfly_api_set",
            widgets_values: ["zhenzhen"],
            outputs: [{ name: "apikey" }, { name: "api_config" }],
        },
        {
            type: "Comfly_api_set",
            widgets_values: ["ip"],
            outputs: [
                { name: "apikey" },
                { type: "ZHENZHEN_SEEDANCE2_CONFIG" },
            ],
        },
        {
            type: "Comfly_api_set",
            widgets_values: ["comfly"],
            outputs: [{ name: "apikey" }],
        },
        {
            type: "Comfly_api_set",
            widgets_values: ["ip"],
            outputs: [{ name: "apikey" }],
        },
        { type: "T8Zhenzhen_API_Settings" },
    ],
};

migrateLegacySettingsNodes(graph);
assert.equal(graph.nodes[0].type, "T8Zhenzhen_API_Settings");
assert.equal(
    graph.nodes[0].properties["Node name for S&R"],
    "T8Zhenzhen_API_Settings",
);
assert.equal(graph.nodes[1].type, "T8Zhenzhen_API_Settings");
assert.equal(graph.nodes[2].type, "T8Zhenzhen_API_Settings");
assert.equal(graph.nodes[3].type, "Comfly_api_set");
assert.equal(graph.nodes[4].type, "Comfly_api_set");
assert.equal(graph.nodes[5].type, "T8Zhenzhen_API_Settings");

const ownLegacyDefinition = {
    name: "Comfly_api_set",
    input: { required: { api_base: [["zhenzhen", "seedance_low_price", "ip"]] } },
};
const externalDefinition = {
    name: "Comfly_api_set",
    input: { required: { api_base: [["comfly", "ip", "hk", "us"]] } },
};
assert.equal(isOwnSettingsDefinition(ownLegacyDefinition), true);
assert.equal(isOwnSettingsDefinition(externalDefinition), false);
assert.equal(typeof extension?.beforeConfigureGraph, "function");
assert.equal(typeof extension?.beforeRegisterNodeDef, "function");

console.log("api_settings_ui_probe=ok");
