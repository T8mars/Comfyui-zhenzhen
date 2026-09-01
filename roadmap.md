# Comfyui-zhenzhen Roadmap

## 2026-08-04 图片 30 路 / 视频 10 路并发改造

Status: implemented_verified

### 目标

- 在不替换、不修改现有节点类型和工作流的前提下，为可并发的图片 API 节点提供最多 30 路并发，为视频 API 节点提供最多 10 路并发。
- 保留原节点的全部输入、校验、错误语义、API 配置和结果类型；并发能力以新增“发射/接收”节点提供，旧工作流继续按原方式串行执行。
- 默认并发数为图片 30、视频 10，同时允许部署方通过环境变量降低上限。
- 不增加第三方依赖，不保存 APIKEY、任务 ID、签名链接或测试生成结果。

### 已核对的用户修改版

参考路径：`G:\Comfyui-zhenzhen(1)`。

- 新增 `ComflyConcurrent.py`，在 `__init__.py` 中把并发节点映射合并到原 `NODE_CLASS_MAPPINGS`。
- 使用两个全局 `ThreadPoolExecutor`：图片默认 30 workers，视频默认 10 workers。
- 根据原节点第一个输出是否为 `IMAGE` / `VIDEO` 自动生成发射节点；发射节点立即返回 `Future`。
- 图片和视频各有一个接收节点，分别等待最多 30 / 10 个 Future，并按输入槽位输出结果。
- 每个后台任务创建独立原节点实例；若原函数返回 awaitable，则在线程内用 `asyncio.run` 执行。
- 原节点仍保留，因此用户版的核心思路不会直接破坏旧工作流。

### 当前版本兼容性审计结果

- 当前项目共有 144 个注册节点；用户版规则会生成 117 个发射节点，其中图片 60、视频 57。
- 覆盖来源包括 `Comfly.py` 72 个、`fal_batch_nodes.py` 26 个、`seedance_low_price_nodes.py` 18 个、`midjourney_low_price_nodes.py` 1 个。
- 117 个包装节点的 `INPUT_TYPES` 均能在当前 ComfyUI 环境构建，没有发现注册冲突。
- 被包装节点中有 42 个原本声明了 `OUTPUT_NODE`；19 个节点提供 `VALIDATE_INPUTS`。
- 当前前端扩展通过原始 `nodeData.name` 精确匹配，用户版生成的新节点不会自动获得 Hailuo H3、Midjourney、Suno、NB/V3.1 等动态控件，也不会自动获得对应 ApiKey 按钮。

### 用户版中需要补强的问题

1. **包装范围**：只按首输出类型自动包装，未来新增本地工具节点时也可能被误判。正式实现需有模块/类别准入规则、显式 opt-out 和注册快照测试。
2. **输入校验**：生成的发射类没有代理原节点的 `VALIDATE_INPUTS`，19 个节点可能绕过 ComfyUI 队列前校验。必须完整转发校验结果，运行时校验仍保留。
3. **错误语义**：接收器当前无条件吞掉 Future 异常并返回占位结果，会改变原节点默认失败行为。正式实现默认应 fail-fast，并提供显式“失败转占位”选项。
4. **输出信息**：当前只保留原节点第一个 IMAGE/VIDEO 输出，会丢失 URL、task id、response 等辅助输出。并发任务载体应保留完整原始结果，并由接收器至少提供脱敏状态汇总。
5. **进度上下文**：`executor.submit` 不会自动复制 ComfyUI 的 `contextvars`。后台 ProgressBar 可能错误归属到最后执行的节点。提交时需复制执行上下文，接收器再按完成数量提供聚合进度。
6. **配置并发**：用户版只锁住 `Comfly.py` 的 `get_config/save_config`；`fal_batch_nodes.py` 仍可并发写同一个 `Comflyapi.json`。应统一为带进程内锁和原子替换的配置存储。
7. **HTTP 会话**：`seedance_low_price_nodes.py` 当前共享一个全局 `requests.Session`，不适合 40 个工作线程直接共用。并发路径需改为 thread-local session，并设置足够的连接池大小，同时保持现有 TLS 证书策略。
8. **线程池生命周期**：全局 executor 没有显式 shutdown，插件重载可能遗留线程池。需提供幂等初始化、`atexit` 回收和重载保护。
9. **队列背压与取消**：`ThreadPoolExecutor` 内部等待队列无界；ComfyUI 中断后已排队 Future 也不会自动取消。需限制待执行数量，并对未开始任务执行 best-effort cancel；运行中的外部 API 任务只能按接口能力停止轮询。
10. **前端一致性**：并发包装节点必须复用原节点的动态显隐、模型联动和 ApiKey 获取按钮，不能退化为全部参数同时显示。
11. **工作流与测试**：用户版没有并发示例工作流和自动化测试，无法持续证明 30/10 上限、顺序、失败处理及旧功能兼容。

### 目标架构

#### 1. 非侵入注册

- 新增独立并发模块，由 `__init__.py` 在原映射加载完成后追加注册。
- 原节点 key、display name、类对象和现有工作流 JSON 均不改动。
- 新节点使用稳定命名：`ComflyConcurrent_<原节点 key>_Submit`、`ComflyConcurrent_Image_Await`、`ComflyConcurrent_Video_Await`。
- 并发资格同时检查首输出类型、允许模块/类别、显式禁用标记；新增节点导致包装集合变化时由快照测试提醒人工核对。

#### 2. 受控执行器

- 图片池默认 30 workers，视频池默认 10 workers。
- 支持 `COMFLY_IMAGE_CONCURRENCY`、`COMFLY_VIDEO_CONCURRENCY`，取值限制为 1-128，修改后重启 ComfyUI 生效。
- 为等待队列增加有界背压，避免多个工作流瞬间堆积大量付费任务。
- 每个任务创建独立原节点实例，并复制 ComfyUI 执行上下文；同步函数在线程内执行，awaitable 使用独立事件循环安全收尾。
- 注册进程退出和模块重载清理，确保线程池只初始化一次。

#### 3. 兼容原节点契约

- 深拷贝原 `INPUT_TYPES`，代理 `VALIDATE_INPUTS`，保留 hidden inputs 和原函数的关键类级约束。
- 发射节点固定输出内部 `ConcurrentTask`，其中保存 Future、原节点 key、媒体类型、槽位和完整原始返回值，不把敏感运行数据写入磁盘。
- `IS_CHANGED` 保持每次执行，避免缓存已完成 Future 后重复使用旧结果。
- 原节点仍可单独运行；不要求用户把旧工作流迁移为并发版本。

#### 4. 接收与错误处理

- 图片接收器支持最多 30 路，视频接收器支持最多 10 路。
- 内部使用完成顺序更新聚合进度，最终按输入槽位恢复固定输出顺序。
- 默认 `fail_fast=true`，任一任务失败时按原节点语义抛错；可显式选择 `placeholder` 模式继续其余任务。
- 占位模式输出类型安全的图片/视频占位结果，并额外输出不含密钥和签名链接的状态摘要。
- 断开输入不应生成付费任务；缺失槽位只生成空输出，不占用 worker。

#### 5. 配置、网络与前端

- 抽取共享的原子配置读写器，统一覆盖 `Comfly.py`、`fal_batch_nodes.py` 和低价节点，同时保持现有字段兼容。
- 国内 Seedance/Midjourney 等请求使用 thread-local session；连接池容量至少覆盖对应 worker 上限，不关闭 TLS 验证，不重新引入 `truststore`。
- 前端增加并发节点到原节点名称的规范化映射，使动态模型 UI 和 ApiKey 按钮同时支持原节点与发射节点。
- 显示名使用“并发发射 | 原显示名”和“并发接收图片/视频”，不修改原显示名。

### 实施阶段

1. **运行时骨架**：实现受控 executor、任务载体、发射类工厂、图片/视频接收器和幂等注册。
2. **契约兼容**：代理校验与 hidden inputs，补齐错误策略、完整结果保存、聚合进度和取消/回收。
3. **线程安全**：统一配置原子写入，改造共享 Session，核对所有 117 个候选节点的实例状态和全局可变对象。
4. **前端适配**：让 Hailuo H3、Midjourney、Suno、NB/V3.1 等动态控件及国内/海外 ApiKey 按钮识别并发别名。
5. **示例工作流**：新增一个图片并发示例和一个视频并发示例，APIKEY 为空，不保存任务号、签名链接或生成结果。
6. **回归与压力验证**：通过本地延迟假节点证明真实并行度，再用少量真实 API 任务验证网络和结果类型；不默认发起 30+10 个付费任务。

### 测试矩阵

- 注册：原 144 个节点映射保持不变；并发节点无 key 冲突，插件正常加载和重载。
- 并发：本地假节点观测图片最大 active=30、视频最大 active=10，完成时间明显低于串行基线。
- 上限：环境变量 1、默认值、非法值、128 上限均有测试；等待队列不会无限增长。
- 顺序：任务乱序完成时，输出仍严格对应 `future_1..N`。
- 返回值：覆盖 tuple/list、`{"ui": ..., "result": (...)}`、IMAGE batch、VIDEO adapter 和多输出节点。
- 校验：19 个现有 `VALIDATE_INPUTS` 节点在原节点和并发发射节点上返回一致结果。
- 错误：fail-fast、placeholder、部分失败、全部失败、Future 取消和 ComfyUI interrupt。
- 配置：并发读写 `Comflyapi.json` 后仍为有效 JSON，不丢失国内/海外和 FAL 配置字段。
- 网络：thread-local Session、TLS 证书、连接池容量、上传/轮询/下载并发及超时。
- 前端：模型切换动态显隐、ApiKey 按钮、旧工作流加载、新并发工作流加载。
- 回归：运行现有全部单元/工作流测试、Python 编译、JavaScript 语法检查和 ComfyUI 自定义节点加载。
- 安全：扫描源码与工作流，确保没有 APIKEY、任务 ID、签名链接和测试媒体。

### 验收标准

- 原节点和旧工作流行为、输入、输出、错误语义完全不变。
- 30 个图片假任务和 10 个视频假任务均达到配置并发上限，没有超过上限。
- 任意单个任务失败不会造成结果错位；默认能明确报错，容错模式能继续返回其余结果。
- ComfyUI 中断或关闭时不再接收新任务，未开始 Future 被取消，线程池可正常退出。
- 并发节点获得与原节点一致的动态 UI 和 ApiKey 入口。
- 所有本地测试、插件加载、配置竞争测试和少量真实 API 冒烟测试通过后，状态才能从 `planned_only` 改为 `implemented_verified`。

### 实施与验证结果

- 新增 `ComflyConcurrent.py`，保留原 144 个节点类与 key，并增量注册 117 个发射节点、2 个接收节点；合并后共 263 个节点，映射无冲突。
- 图片池默认 30 workers、视频池默认 10 workers，等待队列有界；支持环境变量调低或调高到 1-128，进程退出和模块重载都会回收旧执行器。
- 发射节点深拷贝原输入并转发全部 19 个原节点自定义校验；后台任务使用独立节点实例和复制后的 ComfyUI 执行上下文。
- 接收节点按完成顺序更新进度、按输入槽位输出，默认 fail-fast，可显式选择 placeholder；兼容用户修改版工作流中的原始 `Future`。
- `Comfly.py`、`fal_batch_nodes.py`、Seedance 低价节点统一使用工作流内 API Key；Seedance/Midjourney 请求使用 thread-local Session 和 30 容量连接池，TLS 验证策略保持不变。
- Hailuo H3、Midjourney、Suno、NB/V3.1 动态前端和国内 ApiKey 按钮能够识别并发包装节点；同时修复了基线中这四类节点缺少 ApiKey 按钮注册的问题。
- 新增图片、视频并发示例工作流，APIKEY 为空，无任务号、签名链接和生成结果。

### 验证记录

- 自动化测试：69/69 通过；修改前已有的 4 个前端注册失败已修复。
- 本地压力测试：图片最大同时活跃 30，视频最大同时活跃 10，乱序完成后槽位顺序正确。
- 配置禁用测试：旧配置不会被读取或改写，文件不存在时任何兼容写入调用也不会创建它。
- 真实插件映射：原节点 144、发射节点 117、总节点 263，19 个校验代理结果一致。
- ComfyUI `--quick-test-for-ci`：插件成功加载全部并发节点；测试机已有 ComfyUI 占用数据库和 8080 端口的提示不影响插件导入。
- 真实 API：两路图片请求重叠 25.93 秒并返回 IMAGE；两路视频请求重叠 79.17 秒并返回 VIDEO；无 443/TLS/Session 错误。
- 实测下载视频已清理；本次新增和修改文件未写入测试 APIKEY。仓库历史工作流中原本存在的内嵌 Key 不属于本轮改动，未擅自修改。

## 2026-08-05 禁用 Comflyapi.json

Status: implemented

- 禁止插件读取、写入或创建 `Comflyapi.json`；保留同名 Python helper 仅用于兼容旧调用，实际固定返回空配置且写入为 no-op。
- API Key 只取当前工作流节点中明确填写的值；Settings 节点会把 Key 保存在工作流 JSON 的 widget 中，不再落地为独立配置文件。
- Settings 中填写空白 Key 时保持空白，国内低价节点不会回退到磁盘旧 Key，也不会越过已连接的空白 Settings 去读取环境 Key。
- 对旧节点统一安装执行前 Key 重置：同一节点实例上一次使用过 Key 后，下一次把输入清空也会立即清除内存值，不会沿用旧请求凭据。
- `AiHelper` 的配置接口固定返回空对象，不再访问配置文件；缺少 Key 的错误信息改为提示在当前工作流或 Settings 节点中填写。
- 验证：69/69 自动化测试通过；真实插件映射为 263 个节点，其中 121 个含 Key 参数的执行入口已启用空白重置；ComfyUI 快速加载成功，运行前后均不存在 `Comflyapi.json`。

## 2026-08-06 Qwen Image 3.0 / MiniMax H3 OW

Status: implemented_verified

- 新增 `Comfly_qwen_image_3_0_lowprice` 统一图片节点，包含 Qwen Image 3.0 国内/海外、标准/Pro 的 4 个 T2I 与 4 个 I2I 模型；I2I 接受 1-3 张参考图。
- Qwen 尺寸模式保持互斥：`auto` 不发送尺寸，`ratio` 发送 `metadata.ratio` 与 `metadata.resolution`，`custom_size` 仅发送顶层 `size`；同时支持负面提示词、提示词扩写、`n=1..6` 与非负 seed。
- 新增 `Comfly_minimax_h3_ow_video_lowprice` 统一视频节点，包含 T2V、I2V、R2V；支持 5/10/15 秒、480p/720p 和文档列出的 8 种画幅。T2V 不发送图片，I2V/R2V 只上传 `image1`。
- 两个节点自动注册配套并发提交节点，分别进入 30 路图片池和 10 路视频池；动态前端同时覆盖原节点与并发节点，并保留已连接的隐藏输入。
- 新增 11 份逐模型工作流及 2 份并发示例工作流。所有示例 API Key 为空，不含任务号、签名结果 URL 或运行产物。
- 离线验证：80/80 自动化测试通过；真实插件映射为 146 个原节点、119 个并发提交节点、267 个总节点，21 个自定义校验器代理一致。
- 真实 API 验证：8 个 Qwen 模型均通过并发提交节点完成并下载为四维 ComfyUI IMAGE；3 个 MiniMax 模型在同一并发批次完成，下载 MP4 均可解码为 864x480、24 fps、124 帧。
- 实测临时媒体已清理，测试 API Key 未写入源码、测试、roadmap 或工作流。

## 2026-08-06 Nano Banana 2 编辑结果下载修复

Status: implemented_verified

- 实测确认 `/v1/images/edits` 的编辑响应仍为 `200 + data[].url`；原故障风险位于结果图下载阶段：旧实现只请求一次，CDN 文件暂未就绪、临时网络错误或返回非图片内容时会吞掉下载异常，最终表现为后台任务成功但节点没有有效图片。
- 新增 `media_download.py` 公共下载器：最多重试 5 次，分别限制连接/读取超时，每次完整解码并校验图片；最终错误只保留错误类型或 HTTP 状态，不回显签名 URL。
- `Zhenzhen_nano_banana2_edit` 的两份兼容定义、S2A 异步版及自动生成的并发提交节点共用同一下载逻辑。同步提交格式、模型列表、输入输出和旧工作流 key 均未修改。
- 审计并收口同类标准图片结果路径，包括 Nano Banana、Qwen、Gemini/GPT Image S2A、Doubao Seedream/Seededit、Flux、Jimeng、FAL 图片及 Seedream v5 Pro；已有专用重试或鉴权请求头的实现保持原样。
- 新增 3 个离线回归测试，覆盖“URL 首次尚不可解码后成功”“临时 HTTP 503 后成功”“最终错误不泄露签名 URL”。完整自动化测试为 83/83，通过 Python 编译、`git diff --check`、真实插件映射检查。
- 真实 API 双路验证：非并发 `nano-banana-2` 编辑与并发 `nano-banana-pro` 编辑均返回有效 `1 x 1024 x 1024 x 3` ComfyUI IMAGE，结果 URL 存在且无下载/解码错误。
- ComfyUI `--quick-test-for-ci` 白名单加载成功，原节点 146、并发提交节点 119、总节点 267；测试机现有数据库锁和 AiHelper 8080 端口占用不影响本插件导入。
- 测试 API Key 未写入源码、测试、roadmap、工作流或配置；仓库中仍不存在 `Comflyapi.json`。

## 2026-08-09 Seedream v5 Pro 图层拆分

Status: implemented_verified

- 新增独立节点 `Comfly_seedream_v5_pro_layer_decomposition_lowprice`，固定调用 `seedream-v5-pro-layer-decomposition`；要求恰好一张输入图，提示词可空，支持 `auto / 1k / 1.5k / 2k` 与 PNG/JPEG。
- 成功后优先完整读取 `data.data.content.image_urls`，严格保留 API 顺序和重复项，不排序、不去重、不限制结果数量；缺少数组时才兼容回退单图 URL。
- 输出为同索引的 ComfyUI `IMAGE` 与反向 alpha `MASK` 列表。各图层保持原尺寸，未接入现有单图并发收集器，避免异尺寸结果被拼批、缩放或只保留第一张。
- 不新增辅助节点。示例工作流通过 ComfyUI 原生 `JoinImageWithAlpha` 配对 IMAGE/MASK，再由 `SaveImage` 逐项保存底图和全部透明图层；工作流 API Key 为空。
- 离线验证：新增图层拆分与透明下载覆盖后，全量 116 项自动化测试通过；Python 编译通过。
- ComfyUI 0.30 白名单快速加载成功；新节点进入原节点映射，并通过 `COMFLY_CONCURRENT_DISABLED` 保持为独立列表输出节点。
- 真实 API 验证：`auto + png + 空提示词` 一次返回 7 个 URL，节点输出 7 个 IMAGE 和 7 个 MASK；底图为 1024×1024，其余 6 张为不同尺寸透明图层，所有张量均可解码且数值有限。
- 测试 API Key、任务号、签名 URL 和生成媒体均未写入源码、测试、roadmap、工作流或配置。

## 2026-08-09 MiniMax H3 OW Fast / Hailuo H3 768P

Status: implemented_live_blocked_by_upstream_and_balance

- 按最新 `llms.txt` 与参考项目实现新增独立 `Comfly_minimax_h3_ow_fast_video_lowprice` 节点，严格包含 I2V Fast 与 R2V Fast 两个模型；前者必须且只能连接 `image1`，后者支持 1-9 张参考图并按槽位顺序压缩空洞。
- Fast 节点支持 5/10/15 秒、480p/720p 与 8 种文档画幅，复用 `/v1/files/upload`、`POST /v1/videos`、轮询和本地 MP4 下载链路；自动进入现有 10 路视频并发池。
- Hailuo H3 的分辨率枚举保持精确大写 `768P / 2K`，节点默认值与国内 T2V/I2V/Multi 三份工作流统一更新为 `768P`，旧工作流保存的 `2K` 仍可继续加载。
- 新增两个 Fast 安全示例工作流，API Key 为空，未保存任务号、签名 URL 或运行媒体；工作流生成器同步覆盖新模型。
- 离线验证：120/120 自动化测试通过；插件探针确认新节点进入原节点映射和视频并发映射；ComfyUI 0.30 白名单快速加载成功。
- 真实健康检查：同一 Key 的旧 `minimax-h3-ow-t2v` 与 `minimax-h3-ow-i2v` 均完成并下载为可解码 MP4，后者还覆盖了与 Fast 相同的本地图片上传和 I2V 素材链路；两个 Fast 模型多轮提交仍均由上游返回 Cloudflare HTTP 502，当前无法诚实标记为生成成功。
- Hailuo H3 国内 `768P` 请求已通过模型、参数与计价解析，但提供的测试 Key 在预扣费阶段因余额不足被 HTTP 403 拒绝，无法完成三次实际生成。待上游 Fast 恢复且 Key 余额足够后，使用 `tests/live_qwen_minimax_lowprice.py` 与 `tests/live_hailuo_h3_lowprice.py` 可直接复验。
- 测试 API Key、任务号、签名 URL 和生成媒体未写入本次源码、测试、roadmap 或工作流；仓库根目录仍不存在 `Comflyapi.json`。

## 2026-08-09 生成节点执行种子与 fixed 缓存

Status: implemented_verified

- 新增无第三方依赖的 `execution_seed.py` 注册兼容层。它只处理返回 `IMAGE / VIDEO / AUDIO / FILE_3D`、且原 `INPUT_TYPES` 中完全没有 `seed` 的节点；当前精准覆盖 52 个生成节点，API Settings 等非媒体节点自动排除，Upscaler 与背景移除等确定性处理工具显式排除。
- 执行 seed 以可选输入追加在原控件末尾，使用 ComfyUI 原生 `control_after_generate`，支持 `fixed / increment / decrement / randomize`。默认值为 0、默认模式由 ComfyUI 使用 `randomize`。
- 兼容 seed 在调用原函数前被消费，不加入上游 payload；已有原生 seed 的节点不改定义、不改默认值、不重复添加控件。
- `fixed` 依赖 ComfyUI 标准输入签名缓存：seed 与其他输入不变时缓存 key 相同，seed 变化时 key 不同。并发发射节点取消无条件 `IS_CHANGED=NaN`，因此 fixed 会复用已有 Future/结果而不再次提交付费任务；图片/视频接收节点仍刷新接收状态。
- 旧工作流兼容性通过逐节点反查验证：52 个节点的 required、hidden 和全部旧 optional 定义保持一致，新增 seed 仅位于 optional 尾部；旧 JSON 无需批量改写。
- 验证：新增 5 项 seed/缓存测试后全量 `125/125` 通过；真实插件映射为 150 个原节点、122 个并发发射节点、274 个总节点；ComfyUI 0.31 白名单快速加载成功。
- 前端实测：Hailuo H3 节点显示 `seed=0` 和默认 `randomize`，菜单完整包含四种模式并可切换到 `fixed`；`/object_info` 同时确认 seed 位于 optional 最末端。
- 本次未调用真实生成 API，不消耗用户额度；源码、测试、工作流和配置中未写入 API Key、任务号或生成结果，仓库根目录仍不存在 `Comflyapi.json`。

## 2026-08-10 贞贞海外 API 双域名容灾

Status: implemented_verified

- 保持 `https://ai.t8star.org` 为旧工作流和 Settings 的默认值，新增无第三方依赖的 `zhenzhen_http.py`，仅为 `ai.t8star.org` 与 `ai.t8star.cn` 提供自动可达性选择。
- 首次访问以无鉴权 `GET /v1/models` 检查 DNS、TCP 和 TLS，任意 HTTP 响应均视为链路可用；优先 `.org`，失败后选择 `.cn`，进程内缓存 10 分钟。
- 普通 `requests`、持久 Session、图片下载、FAL 海外代理、旧版 Midjourney 异步节点和 OpenAI 兼容 LLM 节点均接入同一选择结果；国内小屋、FAL 官方地址、自定义 IP 与 CDN 不改写。
- POST 只在确认位于 DNS、代理连接、TCP 或 TLS 握手阶段失败时切换重试一次；普通读取超时和 HTTP 业务错误不重发。GET/HEAD 等幂等请求允许连接失败后切换一次。
- 本地模拟覆盖 `.org` 探测失败、附件所示 TLS 握手重置及其多层异常包装、轮询切换、Session 改写、非官方域名隔离、HTTP 错误不切换和普通 POST 连接错误不重发；相关测试 13/13。全量回归 134 项通过，系统 Python 下唯一失败为 ComfyUI 本体缺少 `comfy_aimdo`；整合包 Python 的插件探针另行通过。
- 真实无鉴权健康检查确认两个域名的 `/v1/models` 均可建立 TLS 并返回预期 HTTP 401；整合包 Python 插件探针通过，原节点 150、并发节点 122、总节点 274。未调用生成接口、未使用或保存 API Key。

## 2026-08-10 生成结果下载最低超时 120 秒

Status: implemented_verified

- 公共图片下载器将连接超时下限从 15 秒提高到 120 秒，读取超时低于 120 秒时同步抬高；显式设置为 180、300、600、1200 秒等更长值时原样保留。
- 国内低价视频下载原 `(15, 45)` 秒连接/读取超时统一提高到 `(120, 120)` 秒，原 180 秒整次流下载保护不缩短。
- 两个旧版 GPT Image 下载入口对旧工作流中的 30、60、100 秒值统一应用 120 秒下限，已有 120 秒以上设置保持不变。
- 针对后台任务成功但节点从结果 CDN 立即报 `ConnectionError` 的地区环境，在原连接失败后增加无环境代理直连；该回退仅处理连接/代理异常，避免 HTTP 业务错误或媒体解码错误误切换。
- 并发节点直接执行原生成节点，因此自动复用相同策略；任务提交、轮询、上传、健康检查和 FFmpeg 超时保持原样。
- 验证：全量回归 `138` 项通过；整合包 Python 下 seed 缓存 `6/6` 通过，插件探针确认 150 个原节点、122 个并发发射节点、274 个总节点均可加载。另在报错来源插件中模拟失效环境代理，图片和视频均由无代理直连成功接管，其全量 `288` 项测试及 58 个节点导入通过。

## 2026-08-11 MiniMax H3 Context IR 提示词增强

Status: implemented_verified

- 按最新 `llms.txt` 与参考项目实现新增 `Comfly_minmax_h3_context_ir_lowprice` 三合一节点，精确包含 `minmax-h3-context-ir-text`、`minmax-h3-context-ir-image`、`minmax-h3-context-ir-multimodal`，不把模型名误写为 `minimax-*`。
- 节点调用兼容端点 `POST /v1/video/generations` 并轮询 `GET /v1/video/generations/{id}`，完成后读取 `result_text`；它只增强视频提示词，不生成或下载视频。
- Text 要求固定文档画幅；Image 使用 1-2 张首尾帧且不发送 ratio；Multimodal 支持最多 9 图、3 视频、3 音频，图片走顶层 `images`，视频走 `metadata.video_urls`，音频走 `metadata.audio_url`。
- 前端按模型动态显隐输入：Text 隐藏全部素材，Image 只显示 `image1/image2` 并隐藏 ratio，Multimodal 显示全部素材和 ratio。节点接入国内 ApiKey 获取按钮与 `Comfly_api_set` 的 `seedance_low_price` 配置。
- 节点原生附带只参与 ComfyUI 缓存的执行 seed，不进入上游 payload；因返回 STRING 且显式禁用并发包装，不会错误生成图片或视频并发节点。
- 新增 8 项契约测试及 3 份无密钥工作流，分别覆盖文本、首尾帧和图/视频/音频多模态模式。插件探针确认原节点 151、并发提交节点 122、总节点 275，新增节点没有并发别名。
- 真实 API 验证：三个模型均成功并返回非空 `result_text`；Image 使用 512×512 图片，Multimodal 使用 512×512 图片、4 秒 H.264 MP4 与 4 秒 WAV，素材上传、提交、轮询和结果解析全部通过。
- 测试 API Key、任务号、响应文本、上传地址和生成结果未写入源码、测试、roadmap、工作流或配置，仓库根目录仍不存在 `Comflyapi.json`。

## 2026-08-12 GK v2、Wan 2.7 Global、Qwen3 TTS、MiniMax Audio 与 Mureka BGM

Status: implemented_verified

- 新增五个分组节点，覆盖 `zhenzhen-image-gk-v2`、3 个 Wan 2.7 Global 图片模型、2 个 Qwen3 TTS、4 个 MiniMax 音频模型和 2 个 Mureka BGM，保持参考项目的模型分组与接口契约。
- Wan 文生图提交宽高与思考模式，编辑模式按插槽顺序上传 1～9 张图片；Qwen 指令模型、MiniMax 音乐/语音/克隆和 Mureka 提示词/素材 ID 均使用模型感知的动态参数。
- 两个纯图片节点接入现有并发提交包装；音频节点和 Mureka 多结果列表节点保持原始输出类型，避免被单图并发收集器错误处理。
- 新增 12 份逐模型示例工作流，图像编辑和声音克隆使用本地加载节点，所有 API Key 与运行时字段保持空白。
- 真实验证：12 个模型均完成节点级提交、轮询、素材上传、结果下载和媒体解码；Wan 两个编辑模型返回 2048×2048 图片，Qwen/MiniMax 返回有效非静音语音，Mureka v8/v9 均返回并解码完整双声道音频。
- 修复无音频后端的 `torchaudio` 无法解码 MP3/aLAC 的问题：通用音频下载会自动使用一键包内置 FFmpeg 兜底，不增加 Python 依赖，并清理临时文件。
- 验证：全量 `159/159` 自动化测试通过；插件探针为 156 个原节点、124 个并发提交节点、282 个总节点；14 份本次相关工作流及测试密钥扫描均通过，仓库根目录不存在 `Comflyapi.json`。

## 2026-08-12 Dola Seedream v5 Pro 图层拆分

Status: implemented_verified

- 按最新版 `llms.txt` 与参考项目 `skill.md`，在现有 `Comfly_seedream_v5_pro_layer_decomposition_lowprice` 节点内新增 `dola-seedream-5.0-pro-layer-decomposition`；原国内模型继续默认，不新增重复节点、不改节点 key。
- 保留更新前所有控件顺序，在 `skip_error` 后显式保留缓存 seed 及其 linked control，再追加 `model`。旧工作流缺少尾部 model 时继续使用国内默认值；seed 由执行兼容层消费，不进入 API payload。
- 两个模型共用文档规定的 `POST /v1/image/generations` 与轮询接口，均要求恰好一张图片，提示词可空，支持 `auto / 1k / 1.5k / 2k` 和 PNG/JPEG。
- 继续完整遍历 `data.data.content.image_urls`，严格保留顺序、重复项和不同尺寸；每个结果解码为 RGB IMAGE 与反向 alpha MASK，不接入单图并发收集器。
- 国内与 Dola 各有一份无密钥示例工作流，通过 `JoinImageWithAlpha` 和 `SaveImage` 逐项恢复、保存全部图层。
- 验证：全量 `159/159` 自动化测试通过；插件探针为 156 个原节点、124 个并发提交节点、282 个总节点，图层列表节点未生成并发别名。
- 真实 Dola 调用使用 `auto + png` 成功返回 5 个有序 URL：1 张 1024×1024 底图和 4 张不同尺寸图层；5 个 IMAGE 与 5 个 MASK 全部下载、解码且索引匹配。
- 测试 API Key、任务号、签名 URL、上传地址和生成媒体未写入源码、测试、roadmap、工作流或配置，仓库根目录仍不存在 `Comflyapi.json`。

## 2026-08-14 MiniMax H3 OW Fast 五合一

Status: implemented_verified

- 按最新版 `llms.txt` 与参考项目 `skill.md`，在现有 `Comfly_minimax_h3_ow_fast_video_lowprice` 节点新增 `minimax-h3-ow-t2v-fast`、`minimax-h3-ow-fl2va-audio-drive-fast`、`minimax-h3-ow-ref2va-audio-drive-fast`，不新增重复节点。
- T2V Fast 要求提示词且禁止图片和音频；两种 Audio Drive Fast 要求且只接受 `image1` 与一段 ComfyUI AUDIO，音频转 WAV 上传后以单元素数组写入 `metadata.audio_urls`。
- 保留 `image1..image9` 为输入索引 0..8、`api_config` 为索引 9；新增 `audio` 位于索引 10。旧 I2V/R2V Fast 工作流无需重连，并继续分别支持单首帧和最多 9 张有序参考图。
- 前端与自动生成的视频并发提交节点均按模型显示 0、1 或 9 个图片插槽，只对 Audio Drive 显示音频入口。
- 新增三份空 API Key 示例工作流：T2V、aL2VA Audio Drive、REa2VA Audio Drive；两个音频工作流连接本地 LoadAudio，全部运行时字段保持空白。
- 真实节点验证：三个新模型均以 5 秒、480p 完成素材转换、上传、提交、轮询、结果下载和 MP4 解码；每条结果均为 864×480、24 fps、124 帧。
- 验证：完整离线回归 `163/163` 通过；插件探针为 156 个原节点、124 个并发提交节点、282 个总节点；全部前端脚本及三份新增工作流通过语法和敏感信息检查。
- 测试 API Key、任务号、签名 URL、上传地址和生成媒体未写入源码、测试、roadmap、工作流或配置。

## 2026-08-18 FlashVSR 视频超分 / Seedance 2.5 Native 1080P

Status: implemented_verified

- 实际请求模型名按上游修正为精确大小写 `FlashVSR_video_upscale`；内部节点键继续保留 `Comfly_fashvsr_video_upscale_lowprice`，仅用于兼容已经保存的工作流。
- 请求体严格只包含 `model` 与一个 `metadata.video_url`，调用 `POST /v1/video/generations` 并轮询 `GET /v1/video/generations/{task_id}`；支持恰好一个本地 VIDEO 或公网 HTTP(S) URL。
- 本地视频复用共享上传器，生成结果复用最低 120 秒超时与代理失败直连回退的公共 MP4 下载器。节点带缓存 seed，并自动进入现有 10 路视频并发提交框架。
- Seedance 2.5 国内/Global 的 T2V、I2V、Multi 共 6 个模型追加精确枚举 `native1080p`；未添加文档不存在的 `native1080` 或 `native4k`，原默认 `480p` 不变。
- 新增空 API Key 的 FlashVSR 工作流和环境变量驱动的付费验证脚本；离线契约覆盖精确 payload、素材互斥、上传/提交/轮询/下载、注册与工作流安全检查。
- 按用户要求不付费实测 Seedance 2.5 `native1080p`，通过 6 个模型逐项 payload 回归确认该值原样发送。
- 视频超分链路此前已用 854×480、3 秒 H.264 输入完成本地上传、兼容端点提交、轮询、共享下载和 FFprobe 校验，输出为 1920×1024 H.264 MP4、69 帧、2.875 秒、863910 字节；本次仅修正模型拼写，不重复产生付费任务。
- 完整离线回归 `170/170` 通过；插件探针确认 157 个普通节点、125 个并发提交节点、284 个合并节点，FlashVSR 明确进入 10 路视频池。Python/JavaScript 语法、327 份工作流 JSON、差异格式与本次文件敏感信息检查均通过。
- 测试 API Key、任务号、签名 URL、上传地址和生成媒体均未写入源码、测试、README、roadmap、工作流或配置。

## 2026-08-21 GK v2 Edit 与 FlowMusic 九合一

Status: implemented_verified

- 按最新版 `llms.txt` 与参考项目 `skill.md` 新增独立 `Comfly_zhenzhen_image_gk_v2_edit_lowprice`，精确调用 `zhenzhen-image-gk-v2-edit`。节点支持 1～3 张顶层 `images`、`auto` 与 13 种固定画幅、`1k / 2k`、`n=1..10` 和可选 `nsfw_check`，不发送该接口不存在的 `quality`。
- 保持原 `Comfly_zhenzhen_image_gk_v2_lowprice` 类型和工作流不变，并将其文生图规格同步为文档当前的 7 种画幅及 `n=1..12`；GK v2 Edit 作为纯图片节点自动进入现有 30 路图片并发框架。
- 新增 `Comfly_flowmusic_lowprice` 九合一节点，精确覆盖 `flowmusic-generation`、`flowmusic-lyrics`、`flowmusic-upload-audio`、`flowmusic-extend`、`flowmusic-replace`、`flowmusic-cover`、`flowmusic-stems`、`flowmusic-download-audio`、`flowmusic-video-clip`。
- FlowMusic 生成使用 `POST /v1/music/generations`，其余动作使用对应 action 路由并统一轮询 `/v1/music/tasks/{task_id}`；请求体固定发送 `model=flowmusic`，仅按动作白名单发送字段，`lyria-3.5` 只用于文档允许的动作。
- 本地 AUDIO 复用共享上传器；结果解析递归保留歌词和 `music[].clip_id`，下载器按接口顺序处理全部音频、视频和 ZIP，并同时输出主结果与完整 URL/路径 JSON。该多媒体节点显式不进入单一 IMAGE/VIDEO 并发收集器。
- 新增动态前端显隐和国内 ApiKey 按钮；新增 1 份 GK v2 Edit 与 9 份 FlowMusic 空密钥工作流，所有串联连线、节点类型、动作值、JSON 结构及敏感信息扫描通过。
- 真实节点验证：GK v2 Edit 返回并解码 `1024×1024 RGB`；FlowMusic 的生成、歌词、上传、续写、替换、Cover、Stems、音频导出和 MP4 视频全部完成。编辑链使用 FlowMusic 自生成音乐的 `clip_id`，替换使用已验证的 `lyria-3.5`。
- 完整离线回归 `184/184` 通过；插件探针为 159 个普通节点、126 个并发提交节点、287 个合并节点，执行 seed 覆盖 59 个生成节点。测试 API Key、任务号、clip ID、结果 URL 和测试媒体均未写入仓库。

## 2026-08-22 Omni Lowprice、Hunyuan 3D 与 GK V2 区域工具

Status: implemented_verified_with_upstream_reference_video_issue

- 保留原 `Comfly_zhenzhen_video_g_omni_flash_lowprice` 节点 key、类与工作流契约，新增 `Comfly_zhenzhen_video_g_omni_flash_lowprice_v2` 精确调用 `zhenzhen-video-g-omni-flash-lowprice`；旧节点仅调整显示名为旧版兼容，避免把两个不同上游模型混为一体。
- 新 Omni 节点统一支持 text、frame、reference_images、reference_video 四种模式。文生不传素材；首帧发送 `generation_type=frame` 和恰好一张图；参考图发送 `generation_type=reference` 和 1/3 张连续图片；参考视频发送 `metadata.video_url` 并省略 `seconds`。
- 新增 Hunyuan 3D v3.1 二合一节点，支持 text-to-3d 与 image-to-3d。图生最多 8 张视图，严格按正、左、右、后、上、下、左前、右前排序；GLB 下载使用独立长任务链路并校验 magic、版本和声明长度。
- 3D 节点输出原生 `FILE_3D_GLB`，同时保留 URL、本地路径、任务 ID 与响应。示例工作流直接连接 ComfyUI 内置 `Preview3D` 和 `SaveGLB`；执行 seed 扩展识别 `FILE_3D_GLB`，fixed 输入不变时可复用缓存。
- 新增 GK V2 Segment 与 Region Edit 两个工具节点。Segment 读取 `image_id`、对象列表和完整结果；Region Edit 支持 object_indices、boxes、selection_regions，输入 JSON 由后端结构化解析并强制三种选择互斥。
- 前端按 Omni 模式、3D 模型与区域选择模式动态显隐有效控件，并同时适配自动生成的 Omni 视频并发提交节点和 Region Edit 图片并发提交节点。四个新节点均接入国内 ApiKey 获取按钮。
- 新增 8 份空密钥工作流：Omni 四种模式、Hunyuan 文生/图生 3D、GK 智能分割及完整的 GK 生成→分割→区域编辑链路。
- 真实节点验证：GK 生成、Segment、Region Edit 全链路通过；Omni text、frame、三图 reference_images 均完成并下载有效 H.264 MP4；Hunyuan 文生与图生均返回有效 GLB，并实际通过内置 Preview3D 与 SaveGLB。
- Omni reference_video 使用有效 H.264 参考视频连续两次被服务端接受并进入生成，但最终由上游返回 FAILED。最新版文档与参考项目均确认当前 payload 正确，因此不改写协议；节点保留该模式并透传上游失败。
- 完整离线回归 `199/199` 通过；插件探针为 163 个普通节点、128 个并发提交节点、293 个合并节点，执行 seed 覆盖 62 个生成节点。14 份前端脚本、本次 8 份工作流 JSON、差异格式和敏感信息审计通过，真实测试媒体已清理。

## 2026-08-24 Wan 3.0 四合一视频节点

Status: implemented_verified_with_global_result_storage_issue

- 按最新版 `llms.txt` 与参考项目 `skill.md` 新增 `Comfly_wan_3_0_video_lowprice`，精确覆盖 `wan-3.0-i2v`、`wan-3.0-r2v`、`wan-3.0-global-i2v`、`wan-3.0-global-r2v`，未修改原 Wan 2.7 节点 key 或行为。
- I2V 要求 `image1` 首帧并允许 `image2` 尾帧；R2V 要求提示词，支持最多 10 张图片、5 个视频、5 段音频，并按插槽顺序上传。`file_url` 与 `link_url` 严格互斥。
- 四模型支持 `seconds=auto/2..30`、`480P/720P/1080P`、`adaptive/16:9/4:3/1:1/3:4/9:16`、生成音频及 `0..2147483647` 原生 seed。Global 模型支持 `enable_thinking`，Global R2V 使用文件或网页参考时自动开启。
- 前端按 I2V/R2V、国内/Global 模型动态显隐有效控件和递增素材插槽，并兼容自动生成的 10 路视频并发提交节点；节点接入国内 ApiKey 获取按钮。
- 新增 4 份逐模型空密钥工作流：两份首尾帧 I2V、两份图/视频/音频 R2V。工作流不包含测试 Key、任务号、上传地址、签名 URL 或生成结果。
- 真实验证：`wan-3.0-i2v` 完成并解码为 842×474、30 fps、60 帧；`wan-3.0-r2v` 使用本地图像、H.264 MP4 和 WAV 完成并解码为 832×480、30 fps、60 帧。
- 两个 Global 模型也均完成素材上传、提交和轮询，并返回 `completed + metadata.url`。两条结果都位于同一香港 COS 域名，该域名在当前机器从普通 requests、`trust_env=False` Session、Windows curl 及已运行的本地代理访问时均于 TLS 握手阶段断开；腾讯云新域名替换测试返回 404，因此未加入不可靠的域名改写。该问题发生在任务成功后的结果存储下载阶段，不是模型 payload 或节点轮询错误。
- 公共视频下载器已补强：流式正文读取期间发生连接/TLS 错误后，后续尝试切到无环境代理 Session；最终失败只报告错误类型，不再回显完整签名 URL。新增两项回归覆盖流式 SSL 路由切换与地址脱敏。
- 验证：WAN 3.0 专项 `11/11`、完整离线回归 `215/215` 通过；插件探针为 164 个普通节点、129 个并发提交节点、295 个合并节点，31 个自定义校验器代理一致。
- 测试 API Key、任务号、完整结果 URL、上传地址和生成媒体均未写入仓库；本地真实测试媒体由临时目录自动清理。

## 2026-08-25 Wan 3.0 Prime 高速模型扩展

Status: implemented_verified

- 按当天最新版 `llms.txt`、参考项目 `skill.md` 及其已验证实现，在原 `Comfly_wan_3_0_video_lowprice` 内新增 `wan-3.0-prime-i2v`、`wan-3.0-prime-r2v`、`wan-3.0-global-prime-i2v`、`wan-3.0-global-prime-r2v`，节点由四合一升级为八合一。
- 原四模型列表顺序、默认模型、节点 key、必选控件和可选输入插槽顺序均保持不变。Prime 复用文档规定的 2～30 秒或 auto、480P/720P/1080P、6 种画幅、生成音频及原生 seed 契约，因此旧工作流和自动生成的 10 路视频并发提交节点继续兼容。
- 只有 `wan-3.0-global-i2v/r2v` 两个标准版 Global 模型提交 `metadata.enable_thinking`。两个 Global Prime 模型即使旧工作流保存值为 true 也会忽略该字段，前端同步隐藏无效控件。
- 新增 4 份空密钥 Prime 工作流：国内/Global I2V 均连接首尾帧，国内/Global Prime R2V 使用真实验证稳定的单参考图组合；节点仍保留文档支持的最多 10 图、5 视频、5 音频插槽。
- 真实验证：四个 Prime 模型均以 2 秒、480P 通过节点上传、提交、轮询、结果下载和 MP4 解码。两项 I2V 输出为 842×474、30fps、60 帧，两项 R2V 输出为 832×480、30fps、60 帧。
- Global Prime 首次生成完成后，结果下载复现 Tencent COS 旧 `myqcloud.com` 域名 TLS EOF。共享媒体下载层新增严格限定的官方 `tencentcos.cn` 等价域名回退，保留原签名 path/query、保持 TLS 校验；重新实测两个 Global Prime 均成功下载并解码。该恢复也覆盖其他共享图片和媒体下载调用。
- 验证：WAN 3.0 专项 `13/13`、媒体下载专项 `9/9`、完整离线回归 `219/219` 通过；插件探针仍为 164 个普通节点、129 个并发提交节点、295 个合并节点和 31 个自定义校验器。15 份前端脚本、8 份 WAN 3.0 工作流 JSON 与敏感信息审计通过。
- 测试 API Key、任务号、完整结果 URL、上传地址和生成媒体均未写入仓库；真实测试媒体由临时目录自动清理。

## 2026-08-30 Zhenzhen Video G Omni 1.1 Flash Lowprice

Status: implemented_verified

- 按最新版 `llms.txt`、参考项目 `skill.md` 及其已验证实现，新增独立 `Comfly_zhenzhen_video_g_omni_1_1_flash_lowprice`，精确调用 `zhenzhen-video-g-omni-1.1-flash-lowprice`；没有修改原 Omni Lowprice 与旧版兼容节点的 key、输入输出顺序或模型 ID。
- 1.1 节点复用文档确认的四模式契约：text 不传素材；frame 发送 `generation_type=frame` 和一张首帧；reference_images 发送 `generation_type=reference` 和 1/3 张连续参考图；reference_video 发送 `metadata.video_url` 并省略 `seconds`。
- 支持 4/6/8/10 秒、720p/1080p/4k、16:9/9:16 与 NSFW 检查；共享上传、轮询、最低 120 秒媒体下载和结果解码链路。
- 前端按模式动态显示有效图片、视频和时长控件；新增国内版 ApiKey 按钮识别，并由现有框架自动生成 10 路视频并发提交节点和 fixed/random seed 缓存控件。
- 新增 4 份空 API Key 工作流：文生视频、首帧生视频、三图参考生视频、参考视频生成；所有节点类型、模式值、连线、JSON 和敏感信息扫描通过。
- 真实验证四种模式均完成素材上传、提交、轮询、结果下载和首帧解码；四条结果均为 1280×720、24 fps、96 帧，测试生成媒体已从临时目录清理。
- 完整离线回归 `220/220` 通过；插件探针为 165 个普通节点、130 个并发提交节点、297 个合并节点和 32 个并发校验代理。
- 测试 API Key、任务号、完整结果 URL、上传地址和生成媒体均未写入源码、测试、README、roadmap、工作流或配置。

## 2026-08-30 API Settings 注册隔离与旧工作流兼容

Status: implemented_verified

- 新增最终主注册 ID `T8Zhenzhen_API_Settings`，显示名继续为 `Zhenzhen API Settings`，仅包含 `zhenzhen / seedance_low_price / ip` 三个贞贞渠道，并保持原来的两个输出和默认国内平价小屋渠道。
- `Zhenzhen_api_set` 与 `Comfly_api_set` 作为 deprecated 兼容类保留，输入、输出和执行结果继承主节点；兼容类不再加入 `comfly / hk / us` 等其他平台渠道。
- 当 `Comfyui_Comfly` 已占用共享旧 ID 时，本插件不导出自己的同名别名、不覆盖对方注册；当对方后加载时由 ComfyUI 原生加载顺序接管该旧 ID。两个插件的源文件和运行时配置均不被本插件修改。
- 前端在画布配置前把本插件旧工作流的 `Zhenzhen_api_set`，以及可由渠道、包元数据或双输出契约确认的旧 `Comfly_api_set`，迁移为最终主 ID；对方的 `comfly / hk / us` 和单输出 `ip` 节点保持不变，也不会挂载贞贞的注册链接 UI。
- 357 份工作流全部经 JSON 解析校验，其中 308 份、309 个 Settings 节点和 618 个节点类型/元数据值迁移到最终 ID；相关工作流生成器同步更新，旧注册值在示例工作流中清零。
- 使用真实 `Comfyui-zhenzhen` 与 `G:\Comfyui_Comfly` 完成两种加载顺序探针：最终主 ID 与中间兼容 ID 始终归本插件，共享旧 ID 始终归 `Comfyui_Comfly`；外部插件 Git 状态在验证前后完全一致。
- 验证通过前端迁移行为探针、Python/JavaScript 语法、真实节点映射探针和完整离线回归 `227/227`；没有写入 API Key，也没有创建或读取 `Comflyapi.json`。
