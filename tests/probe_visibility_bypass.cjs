// Compare published bypass handlers with their replacement in the same real frontend.
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const path = require("node:path");
const { chromium } = require("playwright");
const ROOT = path.join(__dirname, "..");
const BASELINE = "c28e8eb59dc9d1eade831c7e682322e28001cf74";
const files = ["midjourney_action_ui.js", "suno_action_ui.js", "zhenzhen_nb_v31_ui.js"];
const old = Object.fromEntries(files.map((file) => [file, execFileSync("git", ["show", `${BASELINE}:web/js/${file}`], { cwd: ROOT, encoding: "utf8" })]));

(async () => {
    const browser = await chromium.launch({ headless: true });
    try {
        const reports = [];
        for (const baseline of [true, false]) {
            const page = await browser.newPage();
            await page.route("**/*", (route) => {
                const request = route.request(), file = new URL(request.url()).pathname.split("/").at(-1);
                if (request.method() === "POST") return route.abort();
                if (baseline && old[file]) return route.fulfill({ status: 200, contentType: "application/javascript", body: old[file] });
                return route.continue();
            });
            await page.goto("http://127.0.0.1:8298", { waitUntil: "networkidle" });
            reports.push(await page.evaluate(async () => {
                const app = (await import("/scripts/app.js")).app;
                const rows = [];
                for (const [key, field, value, media] of [
                    ["Comfly_suno_music_lowprice", "operation", "suno-generation", "audio1"],
                    ["Comfly_midjourney_lowprice", "operation", "midjourney-upscale", "image1"],
                    ["Comfly_zhenzhen_video_v31_lowprice", "model", "zhenzhen-video-v31-lite", "image1"],
                ]) {
                    app.graph.clear(); const node = LiteGraph.createNode(key); app.graph.add(node); node.pos = [500, 100];
                    const widget = node.widgets.find((item) => item.name === field); widget.value = value; widget.callback?.(value);
                    await new Promise((resolve) => setTimeout(resolve, 150));
                    const index = node.inputs.findIndex((input) => input.name === media), input = node.inputs[index];
                    const position = Array.from(node.getConnectionPos(true, index));
                    rows.push({ key, hidden: input.hidden, actuallyHidden: position[0] < -50000 && position[1] < -50000 });
                }
                return rows;
            }));
            await page.close();
        }
        assert.ok(reports[0].every((row) => row.hidden && !row.actuallyHidden), "v2.5.8 bypass handlers must reproduce the hidden-but-accessible defect");
        assert.ok(reports[1].every((row) => row.hidden && row.actuallyHidden), "All three handlers must now hide their inactive material ports");
        console.log("PASS three additional defects reproduced against v2.5.8 handlers and corrected in the same ComfyUI canvas");
    } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
