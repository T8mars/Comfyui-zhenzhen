// Actual canvas checks only. No generation tasks are queued here.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const G26 = "T8Zhenzhen_Image_G26_LowPrice";
const KLING = "T8Zhenzhen_Kling_V4_Omni_LowPrice";
const OMNI = "T8Zhenzhen_Video_G_Omni_12_Flash_LowPrice";
const browser = await chromium.launch({ headless: true });
try {
    const page = await browser.newPage({ viewport: { width: 1800, height: 1200 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("http://127.0.0.1:8298", { waitUntil: "networkidle", timeout: 90000 });
    await page.evaluate(async () => { window.testApp = (await import("/scripts/app.js")).app; });
    await page.waitForFunction(() => window.testApp?.graph);
    await page.keyboard.press("Escape");
    const files = fs.readdirSync(path.join(ROOT, "workflow")).filter((name) => /^(zhenzhen-video-kling-v4-flash|zhenzhen-video-g-omni-1\.2-flash-lowprice|zhenzhen-image-g-v2\.6-lowprice-[24]k|nov08-flash-video-concurrent).*\.json$/.test(name));
    assert.equal(files.length, 11);
    files.push("kling-v4-omni-image-video-lowprice.json", "kling-v4-omni-connected-ids-lowprice.json");
    files.push(...fs.readdirSync(path.join(ROOT, "workflow")).filter((name) =>
        /^zhenzhen-image-g-v2\.6-(?:lowprice|flare|sunburst)-(?:text|edit|gif)-lowprice\.json$/.test(name)));
    files.push("image-g26-gif-concurrent-lowprice.json");
    for (const filename of files) {
        const workflow = JSON.parse(fs.readFileSync(path.join(ROOT, "workflow", filename), "utf8"));
        const report = await page.evaluate(async ({ workflow, keys }) => {
            const app = window.testApp;
            const settle = () => new Promise((resolve) => setTimeout(resolve, 130));
            await app.loadGraphData(workflow); await settle();
            const reports = [];
            for (const source of app.graph._nodes.filter((node) => keys.some((key) => node.comfyClass.includes(key)))) {
                const sockets = source.inputs.map((input) => input.name);
                const linkIds = source.inputs.map((input) => input.link);
                const widget = (key) => source.widgets.find((item) => item.name === key);
                const model = widget("model");
                const initial = model?.value;
                if (source.comfyClass.includes("Kling_V4_Omni")) {
                    for (const value of [...model.options.values, initial]) {
                        model.value = value; model.callback?.(value); await settle();
                    }
                }
                source.setSize([850, source.size[1]]); source.setSize([500, source.size[1]]);
                await settle();
                reports.push({ id: source.id, sockets, linkIds, initial, before: source.serialize().widgets_values,
                    originalWidgets: (workflow.nodes.find((item) => String(item.id) === String(source.id))
                        ?? workflow.nodes.find((item) => item.type === source.comfyClass && (!initial || item.widgets_values?.[0] === initial))).widgets_values,
                    button: source.widgets.filter((item) => item.name === "贞贞的平价小屋APIKEY获取").length });
            }
            const serialized = app.graph.serialize();
            await app.loadGraphData(serialized); await settle();
            const prompt = await app.graphToPrompt();
            for (const report of reports) {
                const restored = app.graph.getNodeById(report.id);
                report.restored = restored.inputs.map((input) => input.name);
                report.restoredLinks = restored.inputs.map((input) => input.link);
                report.after = restored.serialize().widgets_values;
                report.fixed = restored.widgets.find((item) => item.name === "control_after_generate").value;
                report.output = prompt.output[String(report.id)].inputs;
            }
            app.canvas.ds.scale = .65; app.canvas.ds.offset = [10, 25]; app.canvas.setDirty(true, true);
            return reports;
        }, { workflow, keys: [G26, KLING, OMNI] });
        assert.ok(report.length);
        for (const item of report) {
            assert.deepEqual(item.sockets, item.restored);
            assert.deepEqual(item.linkIds, item.restoredLinks);
            assert.deepEqual(item.before, item.after);
            assert.deepEqual(item.before.slice(0, item.originalWidgets.length), item.originalWidgets);
            assert.equal(item.fixed, "fixed");
            assert.equal(item.button, 1);
            assert.ok(Array.isArray(item.output.api_config));
            if (filename.startsWith("kling-v4")) assert.equal(item.output.model, "kling-v4-omni");
            if (filename.startsWith("zhenzhen-video-kling")) assert.equal(item.output.model, "zhenzhen-video-kling-v4-flash");
        }
        console.log(`PASS ${filename}: links, widgets, resize, reload, fixed cache controls, API button`);
    }
    for (const concurrent of [false, true]) {
        const report = await page.evaluate(async ({ G26, concurrent }) => {
            const app = window.testApp;
            app.graph.clear();
            const settle = () => new Promise((resolve) => setTimeout(resolve, 100));
            const source = window.LiteGraph.createNode("EmptyImage");
            const node = window.LiteGraph.createNode(concurrent ? `ComflyConcurrent_${G26}_Submit` : G26);
            const config = window.LiteGraph.createNode("T8Zhenzhen_API_Settings");
            for (const item of [source, node, config]) app.graph.add(item);
            source.pos = [30, 30]; config.pos = [30, 420]; node.pos = [450, 30];
            const slot = (key) => node.inputs.findIndex((input) => input.name === key);
            const input = (key) => node.inputs[slot(key)];
            const widget = (key) => node.widgets.find((item) => item.name === key);
            widget("prompt").value = "Combine sixteen references in order";
            widget("control_after_generate").value = "fixed";
            config.connect(1, node, slot("api_config"));
            if (concurrent) {
                const collector = window.LiteGraph.createNode("ComflyConcurrent_Image_Await");
                app.graph.add(collector); collector.pos = [1070, 30];
                node.connect(0, collector, 0);
            }
            await settle();
            const progressive = [];
            for (let i = 1; i <= 16; i++) {
                progressive.push(!input(`image${i}`).hidden);
                source.connect(0, node, slot(`image${i}`)); await settle();
            }
            const originalSlots = node.inputs.map((item) => item.name);
            widget("resolution").value = "4k";
            const visibleControls = ["resolution", "quality", "output_format"].every((name) => !widget(name).type.startsWith("converted-widget"));
            widget("mode").value = "gif"; widget("mode").callback?.("gif"); await settle();
            const retained = input("image16").link != null && !input("image16").hidden;
            for (let i = 1; i <= 16; i++) node.disconnectInput(slot(`image${i}`));
            await settle();
            const gifHidden = node.inputs.filter((item) => /^image\d+$/.test(item.name)).every((item) => item.hidden);
            widget("mode").value = "image"; widget("mode").callback?.("image");
            for (let i = 1; i <= 16; i++) source.connect(0, node, slot(`image${i}`));
            await settle();
            await app.loadGraphData(app.graph.serialize()); await settle();
            const restored = app.graph.getNodeById(node.id);
            const prompt = await app.graphToPrompt();
            app.canvas.ds.scale = .7; app.canvas.ds.offset = [80, 180]; app.canvas.setDirty(true, true);
            return { progressive, visibleControls, retained, gifHidden, originalSlots,
                slots: restored.inputs.map((item) => item.name), apiIndex: slot("api_config"),
                submitted: prompt.output[String(node.id)].inputs };
        }, { G26, concurrent });
        assert.ok(report.progressive.every(Boolean));
        for (const field of ["visibleControls", "retained", "gifHidden"]) assert.equal(report[field], true, field);
        assert.deepEqual(report.originalSlots, report.slots);
        assert.equal(report.apiIndex, 16);
        assert.equal(report.submitted.resolution, "4k");
        for (let i = 1; i <= 16; i++) assert.ok(Array.isArray(report.submitted[`image${i}`]));
        console.log(`PASS G26 ${concurrent ? "concurrent" : "serial"}: 16 references, new tiers, GIF text-only, stable slots`);
    }
    await page.screenshot({ path: path.join(os.tmpdir(), "zhenzhen-nov08-desktop.png") });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => {
        const app = window.testApp;
        const node = app.graph._nodes.find((item) => item.comfyClass.includes("Image_G26"));
        node.setSize([450, node.size[1]]);
        app.canvas.ds.scale = .68;
        app.canvas.ds.offset = [-node.pos[0] + 90, -node.pos[1] + 165];
        app.canvas.setDirty(true, true);
    });
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(os.tmpdir(), "zhenzhen-nov08-mobile.png") });
    assert.deepEqual(errors, []);
    console.log("CANVAS PASS zero page errors; no API generation submitted");
} finally {
    await browser.close();
}
