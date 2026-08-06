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
