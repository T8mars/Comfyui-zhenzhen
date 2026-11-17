// Canvas-only checks: generation and upload POSTs are explicitly blocked.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
const ROOT = path.join(__dirname, "..");

(async () => {
    const browser = await chromium.launch({ headless: true });
    try {
        const page = await browser.newPage({ viewport: { width: 1700, height: 1100 } });
        const errors = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.route("**/*", (route) => route.request().method() === "POST" ? route.abort() : route.continue());
        await page.goto("http://127.0.0.1:8298", { waitUntil: "networkidle" });
        await page.evaluate(async () => { window.__nov17 = (await import("/scripts/app.js")).app; });
        await page.keyboard.press("Escape");
        const files = fs.readdirSync(path.join(ROOT, "workflow")).filter((name) => /2\.5-(global-)?flash-|comfyui-(charswap|wuxi|max-1002[01])-|doubao-seed-tts-2\.0-/.test(name));
        assert.equal(files.length, 26);
        for (const file of files) {
            const report = await page.evaluate(async (data) => {
                const app = window.__nov17, settle = () => new Promise((resolve) => setTimeout(resolve, 120));
                await app.loadGraphData(data); await settle();
                const nodes = app.graph._nodes.filter((node) => node.comfyClass !== "T8Zhenzhen_API_Settings" && /T8Zhenzhen|Comfly_seedance25/.test(node.comfyClass));
                const state = () => nodes.map((node) => ({ key: node.comfyClass, inputs: node.inputs.map(({ name, link }) => ({ name, link })), values: node.serialize().widgets_values }));
                const before = state();
                const ids = nodes.map((node) => node.id);
                for (const node of nodes) { node.setSize([850, node.size[1]]); node.setSize([540, node.size[1]]); }
                await app.loadGraphData(app.graph.serialize()); await settle();
                const after = ids.map((id) => app.graph.getNodeById(id)).map((node) => ({ key: node.comfyClass, inputs: node.inputs.map(({ name, link }) => ({ name, link })), values: node.serialize().widgets_values }));
                return { before, after, footers: ids.map((id) => app.graph.getNodeById(id).widgets.filter((widget) => widget.name === "贞贞的平价小屋APIKEY获取").length) };
            }, JSON.parse(fs.readFileSync(path.join(ROOT, "workflow", file), "utf8")));
            assert.deepEqual(report.after, report.before, file + ": reload changed links or widget values");
            assert.ok(report.footers.every((count) => count === 1), file + ": API button missing or duplicated");
        }
        console.log("PASS 26 workflows: native load, resize, linked reload, stable widget values and single channel footer");
        const flash = await page.evaluate(async () => {
            const app = window.__nov17; app.graph.clear();
            const node = LiteGraph.createNode("Comfly_seedance25_standard_low_price"); app.graph.add(node);
            const widget = (name) => node.widgets.find((item) => item.name === name);
            const change = (name, value) => { widget(name).value = value; widget(name).callback?.(value); };
            change("resolution", "4k"); change("draft", true); change("model", "seedance-2.5-flash-multi");
            await new Promise((resolve) => setTimeout(resolve, 200));
            const limited = { resolutions: widget("resolution").options.values, resolution: widget("resolution").value, draft: widget("draft").value, draftType: widget("draft").type };
            change("model", "seedance-2.5-standard-multi"); await new Promise((resolve) => setTimeout(resolve, 150));
            return { limited, restored: widget("resolution").options.values, draftType: widget("draft").type };
        });
        assert.deepEqual(flash.limited.resolutions, ["480p", "720p"]);
        assert.equal(flash.limited.resolution, "480p"); assert.equal(flash.limited.draft, false);
        assert.match(flash.limited.draftType, /zhenzhen-hidden/); assert.doesNotMatch(flash.draftType, /zhenzhen-hidden/);
        assert.ok(flash.restored.includes("native1080p"));
        console.log("PASS Standard/Flash switching: resolution contract, draft visibility and restoration");
        await page.evaluate(async () => {
            const app = window.__nov17; app.graph.clear();
            const node = LiteGraph.createNode("T8Zhenzhen_Doubao_Seed_TTS_20_LowPrice"); app.graph.add(node); node.pos = [80, 80];
            await new Promise((resolve) => setTimeout(resolve, 150));
            node.widgets.find((widget) => widget.name === "Voice Library").callback();
        });
        const dialog = page.getByRole("dialog", { name: "Doubao voice library" });
        await dialog.waitFor();
        const options = dialog.getByRole("listbox", { name: "Voices" }).getByRole("option");
        assert.equal(await options.count(), 473);
        await dialog.getByRole("searchbox", { name: "Search voices" }).fill("en_male_tim_uranus_bigtts");
        assert.equal(await options.count(), 1);
        const output = process.env.ZHENZHEN_NOV17_SCREENSHOTS;
        if (output) { fs.mkdirSync(output, { recursive: true }); await page.screenshot({ path: path.join(output, "tts-voice-desktop.png") }); }
        await options.click();
        const speaker = await page.evaluate(async () => {
            const app = window.__nov17; await app.loadGraphData(app.graph.serialize());
            await new Promise((resolve) => setTimeout(resolve, 120));
            const node = app.graph._nodes[0];
            const value = node.widgets.find((widget) => widget.name === "speaker").value;
            node.widgets.find((widget) => widget.name === "Voice Library").callback();
            return value;
        });
        assert.equal(speaker, "en_male_tim_uranus_bigtts");
        await dialog.waitFor();
        await page.setViewportSize({ width: 390, height: 844 });
        const bounds = await dialog.evaluate((element) => ({ width: element.getBoundingClientRect().width, scroll: element.scrollWidth, client: element.clientWidth }));
        assert.ok(bounds.width <= 390 && bounds.scroll <= bounds.client + 1);
        if (output) await page.screenshot({ path: path.join(output, "tts-voice-mobile.png") });
        await page.keyboard.press("Escape");
        assert.deepEqual(errors, []);
        console.log("PASS 473-voice picker: ID search, selection, persistent speaker, desktop/mobile fit, zero page errors; no generation POSTs");
    } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
