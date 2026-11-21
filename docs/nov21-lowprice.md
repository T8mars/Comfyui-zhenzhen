# 2026-11-21 平价小屋节点

对照 [平价小屋 API 文档](https://api.seedance.nz/docs/llms.txt) 和 ComfyUI_Seedance 的实现，仅改动本插件。新旧节点可共存，旧工作流没有改写。重启 ComfyUI 并刷新浏览器后，在节点菜单搜索：

| 节点 | 用法 |
| --- | --- |
| Kling 4 长图 | `kling-v4-long-image`。电商详情页接 1–3 张商品图，可选页面长度；网页模式可接风格图和主体图各一张，也可不接图。两种模式均可选 1k／2k，输出一张 PNG。 |
| Gemini 2.5 Pro/Flash TTS | `zhenzhen/gm-2.5-pro-tts` 和 `zhenzhen/gm-2.5-flash-tts`。有 30 个音色，可另填朗读指令。输出可直接连 SaveAudio。 |
| MiniMax H3 WF 漫剧 Token | `minimax-h3-comfyui-max-10020-token`。1–6 张图，可选最多 3 段音频。 |
| MiniMax H3 JY 特调 Token | `minimax-h3-comfyui-max-10021-token`。1–6 张图，可选最多 3 段音频和 1 段 MP4。 |
| MiniMax H3 角色替换 Token | `minimax-h3-comfyui-charswap-token`。1–5 张新角色图加 1 段源 MP4，可按秒数或帧数选时长。 |
| MiniMax H3 数字人 Token | `minimax-h3-comfyui-digital-human-token`。接 1 张人物图和 1 段语音，设置的视频时长应覆盖音频。 |
| HeyGen Avatar 6 / Turbo | `heygen-avatar-6` 和 `heygen-avatar-6-turbo`。从文稿加音色、本地音频、公开 HTTPS 音频地址三种输入中选一种。形象名称请参照渠道的 Playground。 |
| Miora 3D | `miora-3d`。不接图时为文生 3D；接图时从正面起，可依次接左、右、后、上、下、左前、右前视图。首个可预览的 GLB／OBJ 可连原生 Preview3D 和 Save 3D Model；`files_json` 列出服务返回的各文件及保存位置。 |
| Zhenzhen LLM API | `model_preset` 新增 `zhenzhen/gm-4-hydrogen`、`zhenzhen/gm-4-carbon`、`zhenzhen/gm-4-neon`、`zhenzhen/hy-4-flash`。默认 `custom` 保持原行为。Hy4 预设用文档中实际可用的 `tencent/hy4-flash` 请求。 |

## 示例

`workflow/` 新增 26 份工作流，API Key 均留空；涉及本地图像、音频、视频的示例，运行前请在加载节点选择实际素材。Kling 长图、H3 Token、HeyGen 同时提供普通和并发提交入口。这些模型的 seed 是 ComfyUI 缓存控制，不会发送给上游。

## 实测范围

- 用小屋 Key 实际提交 Gemini Flash TTS 及 LLM 请求，并查询参考项目已有的媒体任务，通过本插件验证轮询、下载与解码，没有重新创建这些媒体任务。Kling 两种模式、Gemini Pro／Flash、四种 H3 Token、Miora 文生／单图均拿到了可用产物。Miora 文生任务返回 4 个文件，全部保存。
- Gemini 4 Hydrogen、Neon 和 Hy4 返回了文本。Carbon 同步和流式都遇到上游 HTTP 524；11 月 22 日发布前复查，HeyGen 两个任务仍显示处理中 50%，没有成片。
- 26 份示例实际在 ComfyUI 画布加载、缩放并重载，验证了 31 路逐个展开的图像接口。真实 Miora GLB 使用原生节点保存后字节一致，桌面和窄屏预览均可渲染，拖拽可旋转。
