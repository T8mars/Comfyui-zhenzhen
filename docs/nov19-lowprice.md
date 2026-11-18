# 2026-11-19 平价小屋节点更新

按[平价小屋 API 文档](https://api.seedance.nz/docs/llms.txt)及本机 ComfyUI_Seedance 参考实现接入。只修改本插件，这组更新纳入 v2.6.1。

| 搜索名称 | 模型与用法 |
| --- | --- |
| Kling 4 图片/组图 | `kling-v4-image`，0–10 张参考图，2k／4k，普通模式输出 1–9 张或组图模式请求 2–4 张。图片和链接均按实际返回顺序逐项输出，即使上游张数不同也不丢图。使用原生 SaveImage 逐项保存；不套用只支持单路图像的并发接收器。 |
| MAI Image 2.7 | `mai-image-2-7`、`mai-image-2-7-flash`，0–5 张参考图。文生图支持 1k／2k、比例或精确尺寸，编辑按上游决定尺寸。支持普通和并发入口；不转发 2.6 的网页检索或自动宽高比参数。 |
| Qwen Audio 3.1 TTS | `qwen-audio-3.1-tts-flash`（69 个系统音色）、`qwen-audio-3.1-tts-plus`（4 个系统音色）、`qwen-audio-3.1-tts-next`（最多 3 段本地或 URL 参考，用 `@voice1` 等引用）。输出原生 AUDIO，可接 SaveAudio。 |
| Zhenzhen LLM API | 在原节点的 model_preset 选择 `zhenzhen/g6.2-astra` 或 `zhenzhen/g6.2-sol`。预设支持文本、单图和流式响应；接平价小屋 API Settings，或填写小屋 Key。默认 custom 保留旧节点原行为。 |

## 示例与验证

- workflow 目录新增 15 份空密钥示例：Kling 3 份（文生、参考、组图），MAI 6 份（每模型文生、编辑、并发），Qwen 4 份（Flash／Plus、Next 无参考／有参考），LLM 2 份（Astra 文本、Sol 图片流式）。加载器中的素材名称是占位，运行前请选择实际素材。
- 使用指定的小屋 API Key 通过本插件实际运行 9 次请求：Kling 参考图和组图完成提交、轮询、下载和解码，分别得到 1 张和 2 张 2048×2048 图；MAI 标准文生与 Flash 编辑各得到一张 1024×1024 图。
- Qwen Flash／Plus 得到 22050 Hz 单声道音频，Next 带参考得到 24000 Hz 双声道音频，均验证非空、非静音。Astra 文本、Sol 图片流式均取得最终文本；Sol 对测试图识别为蓝色。
- 15 份新示例在 ComfyUI 画布完成加载、缩放和带连线重载，三份旧 LLM 示例验证原控件顺序及默认 custom。可灵、MAI 普通／并发和 Qwen Next 共连接 23 路素材，检查逐路展开、接口可命中和索引不移位。画布检查不发送生成请求。
- 4k、所有音色、所有格式、最大素材数量组合未逐一请求 API。14 项新离线测试通过，既有 18 项全仓测试失败／错误未增加。旧示例未改写，也未添加依赖或把测试密钥、任务号、结果链接写入仓库。

更新后重启 ComfyUI，并刷新浏览器页面。
