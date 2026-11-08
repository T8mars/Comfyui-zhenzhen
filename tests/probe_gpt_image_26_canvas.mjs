// Canvas-only checks: never queue an API generation.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const { chromium } = createRequire(import.meta.url)("playwright");
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const NAME = "T8Zhenzhen_GPT_Image_2_6_Workshop";
const browser = await chromium.launch({ headless: true });
try {
    const page = await browser.newPage({ viewport: { width: 1800, height: 1200 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("http://127.0.0.1:8298", { waitUntil: "networkidle", timeout: 90000 });
    await page.evaluate(async () => { window.testApp = (await import("/scripts/app.js")).app; });
    await page.waitForFunction(() => window.testApp?.graph);
    await page.keyboard.press("Escape");
    const files = fs.readdirSync(path.join(ROOT, "workflow")).filter((name) => /^zhenzhen-gpt-image-2\.6-.*-workshop\.json$/.test(name));
    assert.equal(files.length, 16);
    files.push(...fs.readdirSync(path.join(ROOT, "workflow")).filter((name) => /^zhenzhen-GPT-Image-2\.5-/.test(name)));
    assert.equal(files.length, 18);
    for (const filename of files) {
        const workflow = JSON.parse(fs.readFileSync(path.join(ROOT, "workflow", filename), "utf8"));
        const reports = await page.evaluate(async (workflow) => {
            const app = window.testApp;
            const settle = () => new Promise((resolve) => setTimeout(resolve, 120));
            await app.loadGraphData(workflow); await settle();
            const result = app.graph._nodes.filter((node) => /GPT_Image_2_[56]_Workshop/.test(node.comfyClass)).map((node) => ({
                id: node.id, slots: node.inputs.map((item) => item.name), links: node.inputs.map((item) => item.link),
                widgets: node.serialize().widgets_values,
                footer: node.widgets.filter((item) => item.name === "贞贞的AI工坊APIKEY获取").length,
                original: (workflow.nodes.find((item) => String(item.id) === String(node.id))
                    ?? workflow.nodes.find((item) => item.type === node.comfyClass && item.widgets_values?.includes(node.widgets.find((widget) => widget.name === "model")?.value)))?.widgets_values,
            }));
            for (const item of result) {
                const node = app.graph.getNodeById(item.id);
                const open = window.open;
                try {
                    window.open = (url) => { item.footerUrl = url; };
                    node.widgets.find((widget) => widget.name === "贞贞的AI工坊APIKEY获取").callback();
                } finally { window.open = open; }
                node.setSize([850, node.size[1]]); node.setSize([540, node.size[1]]);
                const model = node.widgets.find((widget) => widget.name === "model");
                const initial = model.value;
                for (const value of [...model.options.values, initial]) { model.value = value; model.callback?.(value); await settle(); }
            }
            await app.loadGraphData(app.graph.serialize()); await settle();
            const prompt = await app.graphToPrompt();
            for (const item of result) {
                const node = app.graph.getNodeById(item.id);
                item.after = node.serialize().widgets_values;
                item.restoredSlots = node.inputs.map((input) => input.name);
                item.restoredLinks = node.inputs.map((input) => input.link);
                item.output = prompt.output[String(item.id)]?.inputs;
                item.fixed = node.widgets.find((widget) => widget.name === "control_after_generate")?.value;
            }
            return result;
        }, workflow);
        assert.ok(reports.length, filename);
        for (const item of reports) {
            assert.deepEqual(item.slots, item.restoredSlots, filename);
            assert.deepEqual(item.links, item.restoredLinks, filename);
            assert.deepEqual(item.widgets, item.after, filename);
            assert.deepEqual(item.widgets.slice(0, item.original.length), item.original, filename);
            assert.equal(item.footer, 1, filename);
            assert.equal(item.footerUrl, "https://ai.t8star.org/register?aff=dP7j", filename);
            assert.equal(item.fixed, "fixed", filename);
            assert.ok(Array.isArray(item.output.api_key), filename);
        }
        console.log(`PASS ${filename}: links, widget prefix, resize, reload, fixed seed, Workshop button`);
    }
    for (const concurrent of [false, true]) {
        const result = await page.evaluate(async ({ NAME, concurrent }) => {
            const app = window.testApp;
            const settle = () => new Promise((resolve) => setTimeout(resolve, 110));
            app.graph.clear();
            const node = window.LiteGraph.createNode(concurrent ? `ComflyConcurrent_${NAME}_Submit` : NAME);
            const image = window.LiteGraph.createNode("EmptyImage");
            const text = window.LiteGraph.createNode("PrimitiveStringMultiline");
            for (const item of [node, image, text]) app.graph.add(item);
            node.pos = [360, 50]; image.pos = [20, 50]; text.pos = [20, 400];
            const widget = (name) => node.widgets.find((item) => item.name === name);
            const slot = (name) => node.inputs.findIndex((item) => item.name === name);
            const input = (name) => node.inputs[slot(name)];
            const hidden = (name) => widget(name).type.endsWith(":zhenzhen-hidden");
            widget("prompt").value = "A ceramic teapot";
            widget("control_after_generate").value = "fixed";
            widget("output_format").value = "jpeg"; widget("output_format").callback?.("jpeg");
            await settle();
            const textCompression = !hidden("output_compression");
            const progressive = [];
            const count = node.inputs.filter((item) => /^image\d+$/.test(item.name)).length;
            for (let i = 1; i <= count; i++) {
                progressive.push(!input(`image${i}`).hidden);
                image.connect(0, node, slot(`image${i}`)); await settle();
            }
            const editCompression = hidden("output_compression");
            widget("size").value = "custom"; widget("size").callback?.("custom"); await settle();
            const custom = !hidden("custom_width") && !hidden("custom_height");
            widget("size").value = "auto"; widget("size").callback?.("auto"); await settle();
            const auto = hidden("custom_width") && hidden("custom_height");
            widget("async_mode").value = false; widget("async_mode").callback?.(false); await settle();
            const synchronous = hidden("poll_interval") && hidden("max_poll_time");
            widget("async_mode").value = true; widget("async_mode").callback?.(true);
            const conversion = await import("/extensions/core/widgetInputs.js");
            conversion.convertToInput(node, widget("prompt"));
            text.connect(0, node, slot("prompt"));
            const slots = node.inputs.map((item) => item.name);
            const links = node.inputs.map((item) => item.link);
            node.setSize([900, node.size[1]]); node.setSize([540, node.size[1]]);
            await settle();
            const serialized = app.graph.serialize();
            const clean = serialized.nodes.find((item) => String(item.id) === String(node.id)).inputs.every((item) => !("hidden" in item) && !("pos" in item));
            await app.loadGraphData(serialized); await settle();
            const restored = app.graph.getNodeById(node.id);
            const prompt = await app.graphToPrompt();
            app.canvas.ds.scale = .68; app.canvas.ds.offset = [0, 25]; app.canvas.setDirty(true, true);
            return { progressive, textCompression, editCompression, custom, auto, synchronous, clean, slots, links,
                restoredSlots: restored.inputs.map((item) => item.name), restoredLinks: restored.inputs.map((item) => item.link),
                output: prompt.output[String(restored.id)]?.inputs ?? {}, outputs: restored.outputs.length };
        }, { NAME, concurrent });
        for (const key of ["textCompression", "editCompression", "custom", "auto", "synchronous", "clean"]) assert.equal(result[key], true, key);
        assert.ok(result.progressive.every(Boolean));
        assert.deepEqual(result.slots, result.restoredSlots);
        assert.deepEqual(result.links, result.restoredLinks);
        assert.equal(result.outputs, concurrent ? 1 : 4);
        assert.ok(Array.isArray(result.output.prompt));
        console.log(`PASS ${concurrent ? "concurrent" : "serial"}: progressive references, external prompt, conditional controls, stable sockets`);
    }
    await page.evaluate(async (workflow) => {
        const app = window.testApp;
        await app.loadGraphData(workflow);
        const node = app.graph._nodes.find((item) => /GPT_Image_2_6/.test(item.comfyClass));
        node.pos = [520, 120]; node.setSize([600, node.size[1]]);
        for (const item of app.graph._nodes) {
            if (item.comfyClass === "SaveImage") item.pos = [1300, 120];
            if (item.comfyClass === "T8Zhenzhen_API_Settings") item.pos = [90, 450];
        }
        app.canvas.ds.scale = .85; app.canvas.ds.offset = [0, 70]; app.canvas.setDirty(true, true);
    }, JSON.parse(fs.readFileSync(path.join(ROOT, "workflow", "zhenzhen-gpt-image-2.6-flare-text-workshop.json"), "utf8")));
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(os.tmpdir(), "zhenzhen-gpt26-workshop-desktop.png") });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => {
        const app = window.testApp;
        const node = app.graph._nodes.find((item) => /GPT_Image_2_6/.test(item.comfyClass));
        for (const item of app.graph._nodes) if (item !== node) item.pos = [-1500, -1500];
        node.pos = [90, 240]; node.setSize([540, node.size[1]]);
        app.canvas.ds.scale = .61; app.canvas.ds.offset = [0, 0]; app.canvas.setDirty(true, true);
    });
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(os.tmpdir(), "zhenzhen-gpt26-workshop-mobile.png") });
    assert.deepEqual(errors, []);
    console.log("PASS desktop/mobile screenshots; zero page errors; no API task queued");
} finally { await browser.close(); }
