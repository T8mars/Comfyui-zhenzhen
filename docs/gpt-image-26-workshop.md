# GPT Image 2.6（贞贞的AI工坊）

## 节点与工作流

- 搜索 `gpt-image-2.6`，选择 `zhenzhen-gpt-image-2.6（生成/编辑·6合1·AI工坊）`。注册名为 `T8Zhenzhen_GPT_Image_2_6_Workshop`，不会替换旧 2.5 或平价小屋的 Image G 2.6。
- 包含 Flare、Flare 2K、Flare 4K、Sunburst、Sunburst 2K、Sunburst 4K 六个模型。另有共享图片并发提交版，接原有 30 路图片接收节点。
- 已保存 16 份空密钥工作流：六模型各一份文生、一份双图编辑，另有蒙版、透明标注、透明结果保存、双模型并发各一份。文件名为 `workflow/zhenzhen-gpt-image-2.6-*-workshop.json`。
- Settings 使用 `T8Zhenzhen_API_Settings` 的 `zhenzhen` 渠道，连接 `apikey` 输出到本节点 `api_key`。空密钥立即报错，不读取或创建 Comflyapi.json。底部按钮进入 https://ai.t8star.org/register?aff=dP7j。
- 输出为 IMAGE、image_urls、response、MASK。透明图使用 IMAGE 和 MASK 接原生 JoinImageWithAlpha 后再保存。原生 SaveImage 保存 PNG，即使 API 请求的是 JPEG/WebP。
- seed 仅控制 ComfyUI 缓存，不发送给 API。固定种子且输入未变时复用缓存；随机化会改变缓存输入，不代表上游提供可复现随机种子。

## 官方参数与渠道差异

参数依据 [OpenAI 生成接口](https://developers.openai.com/api/reference/resources/images/methods/generate)、[编辑接口](https://developers.openai.com/api/reference/resources/images/methods/edit) 和 [图像生成指南](https://developers.openai.com/api/docs/guides/image-generation) 核对。这里的六个名称是工坊渠道别名，不是 OpenAI 官方模型 ID。

- prompt 最多 32000 字符；quality 为 auto/low/medium/high/xhigh/max；complexity 可省略或选 low/medium/high；n 为 1-10。
- size 支持 auto、预设或自定义。显式宽高必须为 16 的倍数，最大边 3840，宽高比 1:3 至 3:1，总像素 655360 至 8294400。
- 仅开放 PNG/JPEG/WebP 静态图片，不提供 GIF、SVG、帧数或帧时长。透明背景不允许 JPEG。不发送 input_fidelity。
- 官方参考图上限 16，批次按实际帧数计数，并按插口数字顺序遍历，不截断。mask 与 markup 互斥；markup 必须是匹配首图尺寸、包含透明像素的单张 RGBA PNG。
- 工坊文生走 `/v1/images/generations` JSON，编辑走 `/v1/images/edits` multipart；默认加 `?async=true` 并轮询 `/v1/images/tasks/{id}`，与原 2.5 路由一致。`response_format=url` 和异步查询是渠道扩展，不冒充官方参数。
- 实测文生 JPEG 的 `output_compression=80` 成功；编辑 JPEG/WebP 带该字段返回任务失败，不带则成功。因此编辑模式隐藏压缩控件，且显式设置非默认压缩值时在请求前报错。编辑请保持 `output_compression=-1`。
- 实测带 `-2k/-4k` 的文生别名有时被网关重复追加分辨率后缀，明确 HTTP503 拒绝路由。本节点仅在错误准确包含重复后缀且没有任务号或图片时，用同系列基础别名、原始 size 和其余参数重试一次。response 记录 selected_model/wire_model。其他提交失败、超时、已有任务、编辑请求都不会自动重投。
- 图片逐项下载和解码，保留透明通道为 MASK；使用共享下载恢复和 300 秒下载超时。轮询有总时限和连续失败上限，不会无限挂起。

## 2026-11-09 实测

使用用户授权的工坊密钥、合成茶壶参考素材，经本插件 generate 方法完成提交、轮询、下载及张量解码。以下是测得结果，不保证所有提示词输出相同尺寸。未保存密钥、真实任务号或结果 URL。

| 模型 | 文生 | 编辑 |
| --- | --- | --- |
| gpt-image-2.6-flare | 1024x1024，32.1s | 双图，1024x1024，28.5s |
| gpt-image-2.6-flare-2k | 2048x2048，32.1s | 蒙版，2048x2048，54.5s |
| gpt-image-2.6-flare-4k | 3840x2160，35.8s | RGBA 标注，3840x2160，62.5s |
| gpt-image-2.6-sunburst | 1024x1024，18.9s | 透明 PNG，1024x1024，27.4s |
| gpt-image-2.6-sunburst-2k | 2048x2048，36.0s | 请求 JPEG、不传压缩值，2048x2048，45.7s |
| gpt-image-2.6-sunburst-4k | 3840x2160，36.5s | 请求 WebP、不传压缩值，3840x2160，62.8s |

另测 Flare 文生 JPEG、compression80，1024x1024，34.6s。透明编辑结果 MASK 范围 0-1。全部成功结果均解码为有限数值的 IMAGE/MASK，所有返回条目都遍历；本次实际生成的 n 均为 1，n>1 遍历用离线多结果测试覆盖，不能称为实际多输出测试。

**大数量多图仍有上游问题，不能声称 16 张已跑通。** 14/15/16 张 multipart 请求返回 `images supports at most 16 reference images`，其中 16 张也测试了官方 `image[]` 表单形式；8 张最终返回 `Generation timed out`。官方 JSON `images` 数组形式也被工坊任务明确拒绝为 `failed to parse multipart form`，因此未采用该方式。最终保留已跑通的 multipart 双图流程、官方 16 张插口上限和完整错误提示，不猜测实际容量、不丢弃输入、不在失败后重新生成。高数量参考图需要上游修复后重新验证。

## 离线与画布验证

- 新增 22 项专项测试通过，覆盖参数边界、参考图顺序/批次溢出、透明/蒙版/标注、外接 prompt 的预校验占位值、空密钥、端点、资源关闭、轮询边界、禁止模糊重投、精确路由恢复、所有返回图片、四输出、并发包装和工作流接线。
- 全仓 227 项测试中 209 项通过，另有 9 failure、9 error，与本次前已记录的 18 项相同：历史生成脚本缺失、Hailuo/Suno/NanoBanana/Seedream 过期断言及旧 Wan 测试冲突标记。本次未修改这些不相关文件。
- Playwright 实际 ComfyUI 画布加载 16 份新示例和 2 份旧 2.5 示例，检查模型切换、插口/连线/控件值、缩放、重载、固定 seed、唯一工坊获取按钮。另测普通/并发 16 插口逐步显示、外接文本、条件控件。零页面脚本错误，UI 检查未提交生成请求。
- 全部 509 份工作流进行 JSON/接线/密钥审计。旧工作流和旧 2.5 实现未改动，无新依赖。开发验证时版本为 2.5.6；根据用户明确发布请求，仅递增一次至 2.5.7，并将 README 本次更新标为正式版本。

## 2.5.7 发布前复核

- 重跑全仓 227 项离线测试：209 通过，仍为原有 9 failure、9 error；22 项本次专项测试无失败。工作流完整性 3 项检查通过。
- Python 编译、28 个运行时 JavaScript 语法检查、18 份新旧示例的实际画布检查通过。获取按钮链接为 AI 工坊注册地址，控件与连线保存重载正常。
- Registry 校验在 Windows UTF-8 环境下完成；仍提示既有代码格式、exec/eval 及旧 Wan 测试冲突标记，不能称为全仓零告警。
- 使用标准 Registry 打包器并保持 core.quotepath=false。包内 647 个文件，含全部 509 份工作流及本次 16 份示例；运行模块齐全，无编译缓存、本地 skill、Comflyapi.json 或密钥。暂存文件密钥扫描通过。
- 仅为发布重跑离线、画布和包检查，没有重复提交已经成功的实际生成任务。保留原发布 Action 的触发条件和 Registry secret 引用，不修改其他插件。
