// Test the real ComfyUI canvas without queuing generation.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const key = "T8Zhenzhen_Magi_2_Video_LowPrice";
const url = "http://127.0.0.1:8298";

(async () => {
    const browser = await chromium.launch();
    try {
        const page = await browser.newPage({ viewport: { width: 1660, height: 1100 } });
        const errors = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.route("**/*", (route) => {
            const request = route.request(), target = new URL(request.url());
            return request.method() === "POST" && (target.origin !== url || ["/prompt", "/api/prompt"].includes(target.pathname))
                ? route.abort() : route.continue();
        });
        await page.goto(url, { waitUntil: "networkidle" });
        await page.evaluate(async () => { window.magiCheckApp = (await import("/scripts/app.js")).app; });
        await page.waitForFunction((key) => window.magiCheckApp?.graph && LiteGraph.registered_node_types[key], key);
        await page.keyboard.press("Escape");
        const directory = path.join(__dirname, "..", "workflow");
        const files = fs.readdirSync(directory).filter((name) => /^zhenzhen-magi-2-.*-lowprice\.json$/.test(name));
        assert.equal(files.length, 8);
        for (const name of files) {
            const workflow = JSON.parse(fs.readFileSync(path.join(directory, name), "utf8"));
            const state = await page.evaluate(async (workflow) => {
                const app = window.magiCheckApp;
                const settle = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                const snapshot = () => {
                    const node = app.graph.getNodeById(2);
                    return { sockets: node.inputs.map(({ name, link, hidden }) => [name, link, Boolean(hidden)]),
                        widgets: node.serialize().widgets_values,
                        footer: node.widgets.filter((widget) => widget.zhenzhenApiKeyAcquisitionLink).map((widget) => widget.name) };
                };
                await app.loadGraphData(workflow); await settle();
                const before = snapshot();
                const node = app.graph.getNodeById(2);
                node.setSize([830, 800]); node.setSize([520, 650]);
                await app.loadGraphData(app.graph.serialize()); await settle();
                const prompt = await app.graphToPrompt();
                return { before, after: snapshot(), inputs: prompt.output[2]?.inputs };
            }, workflow);
            assert.deepEqual(state.before, state.after, name);
            assert.deepEqual(state.before.footer, ["贞贞的平价小屋APIKEY获取"], name);
            assert.deepEqual(state.inputs.api_config, ["1", 1], name);
            assert.equal(state.inputs.seed, 0, name);
        }
        const count = await page.evaluate(async (key) => {
            const app = window.magiCheckApp;
            const settle = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
            let count = 0;
            for (const type of [key, `ComflyConcurrent_${key}_Submit`]) {
                app.graph.clear();
                let node = LiteGraph.createNode(type);
                app.graph.add(node); node.pos = [510, 60];
                const port = (name) => node.inputs.find((input) => input.name === name);
                const setMode = async (mode) => {
                    const widget = node.widgets.find((widget) => widget.name === "generation_type");
                    widget.value = mode; widget.callback?.(mode); await settle();
                };
                await setMode("text");
                if (["image1", "audio1", "video1"].some((name) => !port(name).hidden)) throw Error("Text mode shows references");
                await setMode("frame");
                if (port("image1").hidden || !port("image1").label.includes("首帧") || !port("audio1").hidden || !port("video1").hidden)
                    throw Error("Frame mode has incorrect sockets");
                await setMode("reference");
                for (const [family, max, sourceType] of [["image", 10, "EmptyImage"], ["video", 5, "LoadVideo"], ["audio", 5, "LoadAudio"]]) {
                    const source = LiteGraph.createNode(sourceType);
                    app.graph.add(source);
                    for (let i = 1; i <= max; i++) {
                        const name = family + i, slot = node.findInputSlot(name);
                        const xy = node.getConnectionPos(true, slot);
                        if (port(name).hidden || node.getSlotInPosition(...xy)?.input?.name !== name) throw Error(`${type}: ${name} is not connectable`);
                        if (i < max && !port(family + (i + 1)).hidden) throw Error(`${type}: ${family + (i + 1)} appeared too soon`);
                        if (!source.connect(0, node, slot)) throw Error(`${type}: failed to connect ${name}`);
                        await settle();
                        count++;
                    }
                }
                await setMode("text");
                if (["image10", "video5", "audio5"].some((name) => port(name).hidden || port(name).link == null))
                    throw Error("Changing mode lost an existing reference link");
                const links = node.inputs.map((input) => input.link), id = node.id;
                await app.loadGraphData(app.graph.serialize()); await settle();
                node = app.graph.getNodeById(id);
                if (JSON.stringify(links) !== JSON.stringify(node.inputs.map((input) => input.link))) throw Error("Reload shifted links");
                await setMode("reference");
                node.disconnectInput(node.findInputSlot("image10")); await settle();
                if (port("image10").hidden || port("image10").link != null) throw Error("Disconnect did not restore the next usable socket");
            }
            return count;
        }, key);
        assert.equal(count, 40);
        assert.deepEqual(errors, []);
        console.log("PASS: 8 workflow round trips, 40 progressive media connections, zero page errors");
    } finally {
        await browser.close();
    }
})().catch((error) => { console.error(error); process.exitCode = 1; });
