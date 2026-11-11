# Seedream 5.5与Seedance 2.5草稿转高清

开发日期：2026-11-11。渠道为贞贞的平价小屋。依据[当前API文档](https://api.seedance.nz/docs/llms.txt)与本地ComfyUI_Seedance已实现的方法核对；仅修改本插件，没有修改参考插件。开发验证基于2.5.7，本组功能纳入2.5.8发布。

## 节点

| 搜索名称 | 独立注册名 | 模型 |
| --- | --- | --- |
| Seedream / Dola 5.5 生成/编辑 | `T8Zhenzhen_Seedream_55_Image_LowPrice` | seedream-v5.5-t2i、seedream-v5.5-i2i、dola-seedream-5.5-t2i、dola-seedream-5.5-i2i |
| Seedream / Dola 5.5 图像分层 | `T8Zhenzhen_Seedream_55_Layers_LowPrice` | seedream-v5.5-layer-decomposition、dola-seedream-5.5-layer-decomposition |
| Seedance 2.5 草稿转高清 | `T8Zhenzhen_Seedance_25_Draft_To_Video_LowPrice` | seedance-2.5-standard-draft-to-video、seedance-2.5-global-standard-draft-to-video |

三个节点使用工作流中当前API Settings连接值；空密钥不会读取环境或配置文件补齐。API Settings使用本插件独立注册名 `T8Zhenzhen_API_Settings`。底部按钮为“贞贞的平价小屋APIKEY获取”，连接至本渠道注册地址。

生成/编辑与草稿转换有配套并发提交节点，接入原有30路图片/10路视频接收器。分层是多图列表输出，不套用会只取首张图片的接收器。

## 草稿转换

原 `Comfly_seedance25_standard_low_price` 六模型目录、四个输出、旧插口索引、原有控件前缀和原生seed行为不变。只在原skip_error后追加默认false的draft；关闭或省略时，请求与原实现相同。开启时提交metadata.draft=true并强制480p。

在原节点生成草稿后，将task_id输出（索引2，不是video_url）接入新节点的draft_task_id。已有任务号也可直接填写。使用同账号、同区域、已完成且七天内的草稿；国内/海外分别选对应模型。新请求仅含model及metadata.draft_task_id、output_format、return_last_frame，不重传提示词、素材、时长或分辨率。

支持MP4/MOV原始文件下载和原生SaveVideo。共享下载器仅追加可选文件扩展名参数，旧调用仍默认MP4，既有恢复与超时逻辑保持不变。

兼容新版ComfyUI自动插入原生seed控制项的行为：识别旧导出的布尔控件前缀，按名称恢复skip_error和draft，避免把旧skip_error误当作草稿开关。新链路示例显式保存fixed控制项，不改写原有六份Seedance 2.5工作流。

用户补充的国内草稿只做了只读查询，确认completed、国内t2v且draft=true；未为该任务另行提交高清生成。真实任务号不写入示例或此文档。

## 图像与分层

普通生成提示词5-5000字符，图生图1-10张单图输入，单张PNG编码不超过30MiB；文生图拒绝仍连接的参考图片。支持1k/1.5k/2k及自定义宽高，自定义时仅传宽高、不传resolution。透明背景须用PNG。全部参考图先校验并编码，再上传。

分层使用一个image输入，提示词可空，resolution为auto/1k/1.5k/2k；max_images为2-100，包含底图，默认30。支持text_recognition、watermark和safety_identifier。不会发送普通生成专属的background或宽高。

完整遍历 `data.data.content.image_urls`；不截取首图、不按max_images自行截断。images/masks以ComfyUI列表输出，每项维持独立尺寸。image_count、image_urls、local_paths和layers_json同步保留；元数据缺省时返回空数组，不猜测包围框或图层名称。异常空URL或错位元数据明确报错。

原始下载文件保持字节和Alpha；图像输出可保留RGBA，mask为ComfyUI反向Alpha。分层示例使用JoinImageWithAlpha接SaveImage，逐项保存透明PNG。所有新节点seed只用于ComfyUI缓存，不发送给API；fixed且输入不变时复用缓存。

## 工作流

新增11份示例，位于[workflow目录](../workflow)，全部使用空密钥，无真实任务号或结果地址：

- `zhenzhen-seedream-v5.5-{t2i,i2i,layer-decomposition}-lowprice.json`
- `zhenzhen-dola-seedream-5.5-{t2i,i2i,layer-decomposition}-lowprice.json`
- `zhenzhen-seedream55-transparent-lowprice.json`
- `zhenzhen-seedance-2.5-standard-draft-to-video-lowprice.json`
- `zhenzhen-seedance-2.5-global-standard-draft-to-video-lowprice.json`
- `zhenzhen-seedance-2.5-standard-draft-to-video-chain-lowprice.json`
- `zhenzhen-seedance-2.5-global-standard-draft-to-video-chain-lowprice.json`

独立转换示例的draft_task_id故意留空，需填写自己的有效任务号；完整链路示例已连接源节点task_id。

## 验证范围

本次恰好创建三个代表性任务，均完成提交、轮询、下载与解码；不把结果回放算成新API实测：

| 真实任务 | 结果 |
| --- | --- |
| seedream-v5.5-i2i，RGBA参考图、JPEG不透明输出 | 17.67秒，1024x1024 RGB，79159字节 |
| dola-seedream-5.5-layer-decomposition，max_images=2、文字识别开启 | 25.69秒，底图1024x1024 RGB与图层1063x986 RGBA，106236/626312字节；图层元数据存在 |
| 国内草稿转换，复用已完成国内草稿 | 77.62秒，1920x1080、97帧，MP4 1732143字节，完整解码 |

八个模型全部通过参考项目已完成响应回放，执行本插件实际结果解析、完整下载和解码；包括国内/海外透明文生图、编辑、双图分层和MP4/MOV高清转换。回放不验证一次新的上游生成。

19项专项测试通过，包括100项图层完整遍历、Alpha、异尺寸列表、严格运行时校验、空密钥拒绝、创建请求不盲重试、MOV容器、旧控件前缀与新工作流连线。

另有12组普通/并发旧控件布尔值迁移与保存重载检查通过：skip_error真假均覆盖，draft缺省/关闭/开启均覆盖。30个运行时JavaScript文件、画布脚本及相关Python编译检查通过；549份全仓工作流JSON、连线和密钥审计通过，旧工作流文件未改写。

真实ComfyUI画布覆盖11份新示例与6份旧Seedance 2.5示例：模型切换、尺寸调整、保存重载、插口/连接/控件值稳定、单个正确渠道按钮及后端排队校验。七份图像示例执行实际下载/解码与原生保存，并验证fixed重跑不重新提交；并发RGBA保存及单路skip_error不影响成功兄弟任务通过。真实保存的两组分层结果分别保留1254x836/1397x750及1188x883/1344x781尺寸，第二项均保留非全不透明Alpha。国内/海外两条完整草稿链均完成原生SaveVideo，四个保存文件全部解码成功：草稿854x480、成片1920x1080，均97帧。隔离画布阶段禁用了上游创建任务，只复用已完成结果，不重复生成。

全仓离线测试280项，262项通过，另有18项既有问题（9失败、9错误），与修改前基线一致；不能称全仓测试全部通过。未修复无关的环境导入、旧Hailuo/Suno及其他遗留断言。运行数据和测试结果文件均保存在仓库之外，不添加依赖、不生成Comflyapi.json。
