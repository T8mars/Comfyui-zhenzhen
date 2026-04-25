# 网站：[https://ai.t8star.cn](https://ai.t8star.cn/register?aff=cbff0534884)
# 在线工作流海外版：
https://www.runninghub.ai/?inviteCode=rh-v1121
# 在线工作流国内版：
https://www.runninghub.cn/?inviteCode=rh-v1121
# 👋🏻 Welcome to Zhenzhen

<img src="https://github.com/T8mars/Comfyui-zhenzhen/blob/main/pic/1.png" width="30%" alt="My favorite girl">
My favorite girl Go YounJung

# 企鹅版Nano Banana Pro,Sora2,Veo3.1无限并发整合包V5，感谢企鹅：
夸克网盘：https://pan.quark.cn/s/445806b40baa
谷歌盘：https://drive.google.com/file/d/1Ie384HYnA_nF5yOUqi57jm1WdeqpLiVW/view?usp=sharing

# 网站价格和宗旨：

本站开设初衷是提供平价的API给粉丝朋友玩最新的海外模型，并非盈利目的，秉承这一理念，我们的价格毛利不到10%，去掉正常缴税和人工开发维护，服务器成本后几乎没有利润，所以并非盈利性质网站，没有任何议价空间，也不支持用于商业目的的二次开发，仅服务于粉丝朋友，望理解，每个月发票数量有限，需要自己承担所有税费5-25%

# 网站使用及Api调用教程：

网站使用教程：https://ai.t8star.cn/about

API调用及开发教程：https://ai.t8star.cn/api-set

# 新版节点搭建，报错自查，API调用教程：

B站：https://www.bilibili.com/video/BV1TzspzpEFJ/

Youtube：https://www.youtube.com/watch?v=zwpjDCMCJOY

# 贞贞的AI工坊全模型使用教程（不断更新）：

https://space.bilibili.com/385085361/lists/6620957?type=season

https://www.youtube.com/playlist?list=PLNYA7C10cIXdrKL7TZnMSVjoyMtKADQlh


# 更新 Update：

<img src="https://github.com/T8mars/Comfyui-zhenzhen/blob/main/pic/6.jpg" width="70%" alt="new node">

如果报错了，请查看上面的代码，不一定都是你的问题，或者服务器问题，尤其SORA2，大部分情况是OPENAI的问题，当你发生500报错了，请在跑一次就可以了！

<img src="https://github.com/T8mars/Comfyui-zhenzhen/blob/main/pic/oss.png" width="70%" alt="new node">

由于NanoBanana Pro 4K的图像文件过大，在跨境下载时候容易导致失败，新增OSS设置(对象存储服务)

登录网站-令牌-你使用的APIKEY-编辑-拉到底部-选择CN或者US的OSS即可解决问题，如果报错也可以在comfyui终端检查最后报错代码，其中有下载地址，可以下载图片！

### 通知

我们是海外服务器，如果打不开贞贞的AI工坊或者连通不上，报443错误，请求API都需要开启魔法，望周知
部分人完全是因为用的Vpn软件问题，请用常规软件！开Tun模式
开源免费版仓库：https://github.com/2dust/v2rayN/releases
下载Windows版本！
另外360防火墙这些垃圾软件也可能导致这个问题！请关闭！包括有些人的路由器设置！

目前由于谷歌风控严重，nano-banana-pro和gemini-3.1-flash-image-preview模型需要用优质分组比较稳定
由于openai风控严重，暂时可用的分组是sora-vip分组

### 20260425-1

zhenzhen-gpt-image-2-official_ratio节点输入图从5张调整到16张


### 20260425

zhenzhen-gpt-image-2-official_ratio节点增加skip_error参数

### 20260424-2

新增节点zhenzhen-gpt-image-2-official_ratio，支持全比例分辨率，近似取值，包含特殊比例，如21:9等

新增工作流：zhenzhen-gpt-image-2官方全比例4K版（支持多参）.json


### 20260424-1

更新seedance2.0超时时间从10分钟调整为60分钟，防止部分时间长的返回不成功


### 20260423-2

新增快速判断错误类型并返回错误结果，感谢十字鱼提供代码！

修正zhenzhen-gpt-image-2-官方版多图编辑支持4K.json工作流

### 20260423

节点：zhenzhen-gpt-image-2-official更新，支持最多16图输入

新增工作流：

zhenzhen-gpt-image-2-官方版多图编辑支持4K.json


### 20260422

新增节点：zhenzhen-gpt-image-2-official，这是官方节点，需要修改分组openai优质，用default分组还是走的普通的，务必注意

新增工作流：

gpt-image-2-4K官方版（需要修改分组）.json

### 20260421

新增节点：Zhenzhen_gpt_image_2_S2A，注意一定要用这个新的，这个是异步任务，之前的是chat，只有异步任务失败才会退费，目前0.04积分/次，我们只保留10%的运营毛利

新增工作流：

gpt-image-2-全量版文生图.json

gpt-image-2-全量版图像编辑.json

### 20260420

新增节点：Zhenzhen_gpt_image_2，支持最新gpt-image-2模型，由于该模型并未全量，所以不保证每个图片都是gpt-image-2生成，仅供测试，不是非常推荐

新增工作流

zhenzhen-gpt-image-2图像编辑（非100%）.json

zhenzhen-gpt-image-2文生图(非100%).json

Suno+V5.5顶级纯音乐生成V1(基准0.5_两首歌-贞贞AI工坊).json

### 20260417

seedance2.0节点支持原生native1080p，效果炸裂
目前后端还没匹配，今晚更新，先把节点更新了！

### 20260416

更新支持suno v5.5模型，效果真的太棒了！

新增工作流：zhenzhen-suno-v5.5-excellent.json

另外高允贞新剧4.18上线，大家记得来看哦！


### 20260414

新增节点

Zhenzhen Google Veo3 Lite

支持veo3.1-lite模型及原本的模型，仅支持令牌分组：veo&grok-备用1

新增节点

Zhenzhen Grok3 Video 30S

令牌分组：

veo&grok-备用1

只支持720P 时长可以6-30秒

veo&grok-备用2

支持720和1080P

时长只能10秒和15秒

更新对应的工作流

目前后端可能有点问题，白天我在检查下


### 20260412

seedance2.0支持2k,4k,1080p，更新视频教程

Bilibili教程：https://www.bilibili.com/video/BV1YnDQBtEkP/

Youtube教程：https://www.youtube.com/watch?v=xR5zyNNYnNk

### 20260411

重写seedance2.0节点逻辑，修复BUG
更新seedance2.0的3个工作流

### 20260410

支持seedance2.0真人ID上传永久复用，修复后端的一些BUG
新增工作流Seedance2.0-asset-upload.json

### 20260409

支持seedance2.0
最新上架2个模型doubao-seedance-2-0-fast-260128，doubao-seedance-2-0-260128

不同的传入，最终价格不同，注意传入参考视频，参考视频的秒数也计入价格

便宜的可以考虑用480P FAST大概0.5算力左右，720P 满血版的大概1算力

支持直接上传真人，也支持传入素材库保存ID永久使用

调用教程（还没完全完善），网站左侧API文档，sdols

更新工作流Seedance2.0-multiref-video-generate.json

（目前节点有可能有点BUG，白天继续修复，目前上传资产有点问题，另外有可能生成成功了， COMFYUI还在跑，可以去网站异步任务的ID下载，白天修复）


### 20260331

Veo3.1模型恢复，提高一定稳定性

### 20260330

香蕉2&Pro默认分组修复，4K依然推荐用优质分组，默认分组可能还不算稳定，还在调整

Gork视频增加资源，提高稳定性

### 20260328

由于 Sora 官方App 下架，default分组下架、暂时仅Sora-vip可用

### 20260323

sora2 default 组恢复，价格恢复0.1 算力，sora pro 也恢复

工作流:

(新版0.1积分-支持真人)Sora2新图生视频V1(贞贞工坊-令牌分组选default) 

https://www.runninghub.cn/post/2036008151446724610/?inviteCode=rh-v1121

(新版0.1积分-支持真人)Sora2新文生视频V1(贞贞工坊-令牌分组选default) 

https://www.runninghub.cn/post/2036011299909410818/?inviteCode=rh-v1121

### 20260317

grok-video-3模型已恢复使用，支持多参，15S，中文配音，分镜头，多宫格等
sora-2模型默认分组已经暂时下架

### 20260317

新增工作流，zhenzhen-grok3-video-multi-imgs-r2v-15s-v2

### 20260316

grok-3-video模型支持类seedance2.0多参，工作流和节点均已更新！

最多支持 7张参考图，需要在 prompt 中描述 @img1 @img2... @img7 ，这是固定格式

例如： @img1 一只T8拿着刀追 @img2 温总

新增工作流，zhenzhen-grok3-video-r2v-Mul-Imgs-15s-v1.json

### 20260304

不好意思，昨天工作太晚刚起来，贞贞的AI工坊早上网站SSL证书过期了，导致API出问题，实在抱歉，已经修复

另外节点修正了一个传参错误，grok-video-3的duration应该传参string，已修正


### 20260303

更新grok video 15秒T2V及R2V工作流，更新新香蕉2工作流

### 20260228

更新Grok3VideoApi节点，目前支持15S视频！漫剧，真人短剧必备！

### 20260227

支持gemini-3.1-flash-image-preview模型，新增节点Zhenzhen Gemini 3.1 Flash Image Edit S2A

更新工作流zhenzhen-gemini-3.1-flash-image-preview_edit_s2a.json

更新工作流zhenzhen-gemini-3.1-flash-image-preview_t2i_s2a.json

### 20260213

已支持 glm-5模型，目前世界级sota存在，支持缓存计费，sora-2模型default 分组暂时恢复可用，sora-2 价格上升至 0.5 一次/15秒

### 20260210

新增sora-2-vip模型，单词1.25 只支持10S，分组选择default，生成成功率90%以上，生成时间150秒左右

新增工作流：zhenzhen-sora2-2-vip-ti2v-recommend.json

### 20260203

支持grok video新模型的10秒功能，增加分辨率选项，支持文生视频和图生视频，支持中文语言，删除老的工作流，新增2个新的工作流

zhenzhen-grok3-video-t2v-v2.json

zhenzhen-grok3-video-i2v-v2.json

### 20260202-2

更新sora2_new节点
进一步加强稳定性

### 20260202

目前sora2进展，
1、目前sora2-vip分组基本可用，但是成本上涨即将涨价
2、sora2的default分组已经开始降低失败率，即将稳定，成本上涨即将涨价
3、sora2_new模型，独立API仅提供漫剧即将违约的朋友，成本价1000条200元，网站公告有联系方式，需要预约，数量有限，纯帮忙

sora2平替：
gork视频模型已经升级，支持多镜头，效果比Sora2还要好，支持直接真人模式，无限并发，NSFW我们已经过滤，支持生成10s，有声音。是sora目前比较合适的平替。完美匹配中文语音，效果炸裂！！如果不会调用的可以看我的comfyui节点，扔给AI！模型名字grok-video-3
视频效果可以看贞贞工坊官网-左侧教程-最上方

### 20260131(晚上8点半通知)

Sora2基本搞定，测了一天了，很稳定，模型请用：sora-2， 分组切换成 sora-vip，消费积分0.33334/次，请自行尝试，，15S，请自行尝试

目前可以用的是Default分组的sora-2-pro模型，支持HD和25S，以及sora-vip分组的sora-2模型

### 20260201

sora2-new模型稳定版已支持自动去水印(非并发comfyui版，支持RH使用)
这几天洛杉矶办事处网络出现一些问题，由于亚太地区海底光缆别切断导致我们骨干网络服务供应商NTT网络性能下降，目前该服务商已暂时停止服务。所波及影响是无论打开我们贞贞的AI工坊或者联通API都需要开启魔法，望周知！

### 20260201

新增了sora2_new节点，需要单独的APIKEY，因为共同的最近风控太厉害了，如果有需要的B站联系我。。稳定
新增了veo3.1-fast模型的支持
新增sora2 new工作流，和原本的APIKEY不通用

### 20260116

暂时取消veo3.1-fast模型，有点问题，等处理后添加，重写veo3.1节点，务必更新！

新增veo3.1-4k工作流

sora2-character角色获取节点新增from_task参数，创建角色可以通过taskid创建

### 20260115

更新支持veo3.1-fast,4k,pro 4k等模型及节点支持，fast 基准0.2 4K 基准0.5 Pro 4K 基准2，工作流不变，只需要选择新模型

更新vidu q2多参工作流：zhenzhen-vidu-q2-multi-ref-i2v.json

Api Setting节点废弃2个不用的接口地址（US,HK）

### 20260112

更新支持minimax hailuo 2.3 I2V图生视频及工作流

更新支持Flux2 max图像编辑及工作流

更新支持Mj niji 7及工作流，注意这个目前不支持用apisetting节点，我下个版本更新，直接输入KEY即可

网站教程顶部增加基础报错教程以及企鹅无限并发整合包

### 20260109

Claude 4.5 opus Default渠道恢复
Veo3.1 恢复
Grok vieo 3 恢复
Sora2正在继续扩容，目前出现超时请重试，我们正在不断扩容！

### 20251219-3

目前由于openai官方问题，sora2的API大批出现问题，等待官方修复，并非我们问题

### 20251219-2

升级gpt-image-1-edit节点，支持最多10图输入和10 mask（Mask我没测试）
新增2个gpt-image-1-edit工作流

### 20251219

新增gemini-3-flash-preview模型
昨天谷歌大香蕉2 Default分组基本一点问题没有，大家可以继续用便宜的分组，优质分组做紧急备用

### 20251218-3

更新gpt-image-1和gpt-image-1-edit节点，支持gpt-image-1.5模型
推荐优质分组基准0.12，Default分组超级慢，不推荐，非异步，目前测试优质分组大概200秒左右出图

### 20251218-2

香蕉2模型的优质分组价格阶梯：1k，2k都是0.42算力额度, 4k单独做了价格：0.555算力额度。默认分组价格保持不变。

### 20251218

重要通知， 谷歌Nano Banana 2(pro) 大香蕉官方低价渠道并发削减导致卡顿，后台排队阻塞严重，现提升 Gemini 优质分组价格，使用高等级 Vetrex 账号，以维持稳定可用；default组得等谷歌调整恢复并发，可用性较差，急的建议尝试调整令牌分组，网站左侧令牌，找到对应的APIKEY编辑，添加gemini优质分组

### 20251217

新增节点wan2_6_API，支持官方百炼的APIKEY，暂时贞贞网站还没上，我测试用的，支持文生和图生视频，工作流已更新到workflow目录下
llm_api节点重写视频识别部分，目前已正常支持视频反推，工作流已更新到workflow目录下

### 20251216-2

修复代码冗余导致的节点加载异常

### 20251216

sora2_character新增from_task参数输入框：可以直接把sora2生成的真人视频的task id直接输入进去创建角色。

### 20251213-2

今天openai服务器问题导致sora2一直失败（应该是GPT5.2太火爆），导致的负载不够，并非我们问题，SORA2只能多抽卡或者等官方恢复后使用，并非我们问题

### 20251213

新增节点zhenzhen_llm_api，支持图像反推，文本扩写，支持Openai兼容格式，可用网站的模型，如需反推的话需要标签带识图的模型
模型选择位置-登录网站-右上角模型价格-搜索或者查找你要的模型，注意标签哦！

### 20251211-2

Sora2 Pro 15S HD版和25S已经恢复使用，节点不变，基准2.5元

### 20251211

Nano-banana-2(Pro) 由于官方并发大幅缩减，目前正在大量增加并发，成本上涨，故NanoBanana Pro价格从0.15上调至0.2基准，gemini 3 pro image preview暂时不变，价格已经生效，望周知

### 20251209

新增Grok3-video节点，支持最新GORK文生视频和图生视频，支持音画同步，支持中文配音，已过滤nsfw内容，合规使用！新增对应的2个工作流
今天下午谷歌砍了并发，导致目前一直分组上限，目前在逐步处理，推荐先用优质分组

### 20251206-2

新增工作流zhenzhen-Nano-Banana-2-Edit-S2A.json，同步转异步，支持异步任务，可在网站后台异步任务查询(nano banana pro)

<img src="https://github.com/T8mars/Comfyui-zhenzhen/blob/main/pic/s2a.png" width="100%" alt="new node">

### 20251206

新增nano_banana2_edit_S2A节点，支持同步转异步模式，任务可在异步任务中查询了！同时可以通过任务ID回溯下载失败的图片URL地址！另外做了一些异常处理

### 20251205-2

修复veo3.1 component模型问题
新增节点：Zhenzhen_Z_Image_Turbo
工作流晚上回去发

### 20251205

新增Zhenzhen Doubao Seedream4.5节点，可使用豆包4.5，出图速度比大香蕉2快多了，人物一致性好过大香蕉，基准0.15，支持2K和4K
新增zhenzhen-doubao-seedream4_5_image_edit.json工作流

### 20251203

nano_banana2-edit节点新增模型nano-banana-2-2k，nano-banana-2-4k，如果用API调用时候，image_size参数不生效，主要用于由于谷歌问题导致的2K,4K出图变1K问题的备用方案，作为备用模型

上架可灵视频O1模型，Z-image-tubro以及阿里的各种视频模型

### 20251130

以下2个新模型扣费方式不太一样，使用前请注意下，因为都是官方渠道

更新vidu以及Flux2 pro和Flux2 Flex新工作流

Vidu的扣费方式是按照0.04*官方的Cost

flux-2-pro模型，此模型按量付费，不同分辨率不同价格

官方文档：

https://docs.bfl.ai/api-reference/tasks/generate-or-edit-an-image-with-flux2-[pro]

价格计算器：

https://bfl.ai/pricing

### 20251128

上线 Claude 最新模型 claude-opus-4-5-20251101，目前最强的推理模型之一，上架MinMax系列音频模型，上架Flux2 Pro和Flux2 Flex模型，上架Vidu多参，文生，图生，首尾帧模型

SORA2 15S和10S调用变慢的问题，目前OPENAI又改了，所以速度变慢了，在优化，但是速度应该回不到之前速度，每天晚上NANO BANANA PRO速度变慢时候，建议把BASEURL改成US，白天正常的情况下用主站

### 20251127

新增Flux2相关节点，Flux_2_Flex，Flux_2_Pro
新增Vidu相关节点，vidu_img2video，vidu_text2video，vidu_ref2video，vidu_start-end2video

工作流晚上更新

### 20251124-2

Nano Banana 2模型后端进行了调整，基本修复了出白图的问题，调整了格式，可以尝试使用Default或者和优质分组一起用

Nano Banana 2 Edit节点新增AUTO模式，自动跟随图片尺寸比例，已默认

### 20251124

注意，目前令牌分组default负载过大，4K容易出白图，推荐2K
如需4K，在贞贞AI工坊网站左侧令牌-找到自己的令牌编辑，删除Default分组，添加优质分组，成功率大大提高
报错429和报错500都是谷歌负载上限，并不扣费，如果遇到的是提示无法处理图片并扣费，这时候请去网站的日志里，找到对应任务点进去，实际已经生成完毕，目前在排查这个问题

### 20251122

Nano Banana 2模型4K价格下调到基准0.15元(rmb)
Veo3.1及component模型价格从2.025下调到0.3元(rmb)
Veo3.1 Pro模型价格从3元下调到1元(rmb)

### 20251121-2

新增节点：nano_banana2_edit

支持Nano Banana 2多图编辑以及2K，4K高清版

增加工作流：Nano-Banana-2-Edit-T2I-4K.json

增加工作流：Nano-Banana-2-Edit-Multi-I2I-4K.json

可选分辨率以及1K,2K,4K，暂时都是0.2积分

### 20251121

新增Nano-Banana-2模型

目前支持2个模型Gemini-3-Pro-Image-Preview 和 Nano-Banana-2

区别：

Gemini-3-Pro-Image-Preview，适配官方格式级openai chat格式
nano-banan-2：支持chat，支持Openai兼容格式，传送支持2K,4K，API调用参数：mage_size="4K",支持绘图接口同步模式以及异步模式

节点也更新了，但是似乎4K没生效，白天看下在修复

### 20251120

支持nanobanana 2，直接用原本的nanobnana工作流即可，更换下模型！
模型名字gemini-3-pro-image-preview
增加工作流：zhenzhen-nano-banana-V2(Gemini-3-pro-image-preview).json
目前是0.2积分/图

<img src="https://github.com/T8mars/Comfyui-zhenzhen/blob/main/pic/6.png" width="100%" alt="new node">

### 20251117

增加2个新工作流，分别是Sora2角色创建节点，以及多角色@调用加图片参考混合工作流

zhenzhen-sora2-character-create.json --角色创建，创建将花费0.01积分，只需创建一次，可以无线调用

zhenzhen-sora2-multi-character.json --多角色@调用加图片参考混合

创建我们可以通过图床的URL获取，但是很多图床不支持VIDEO，另外有些哪怕可以上传SORA2也不支持，所以推荐用下面方式：

首先先用Sora2跑一次视频，跑出来的角色的response的MP4地址复制到新节点的URL

常规操作：

URL部分需要用图床，但是不是每个图床都支持，最好的办法， 先用我们的API生成一个SORA2视频，他会有个MP4地址

生成的usename保存下来，后续就可以直接@使用了，支持多角色

比如：https://midjourney-plus.oss-us-west-1.aliyuncs.com/sora/39cf59c1-354f-4ba3-88d6-5abebc14c0b8.mp4

让后复制下即可，就能获得新的USERNAME

timestamps代表获取URL视频的其中几秒中的角色，1,3意思就是1-3秒，以此类推

参考工作流是2角色@加一个参考背景，可支持多角色客串艾特以及多图参考，当然太多肯定也会影响一致性，请适量！

### 20251112

增加3个新工作流，分别是Suno V5歌曲翻唱，Suno V5歌曲续写，Suno V5歌词读取，3个文件已更新到workflow文件夹下，一次出两首歌，如果发现两首歌一样的话，只需要去贞贞AI工坊网页版-左侧的异步任务，点开任务ID，里面下载MP3即可

### 20251111-2

新增Comfly Sora2 Character节点，使用方式是把生成后的username用于放在提示词中 @username 直接调用。可同时使用多个角色客串调用。需要先在sora2中认证创建角色，或者用别人已认证创建过的角色，支持真人！

统一所有的节点分组

### 20251111:

sora2新增创建角色 API，创建角色，后续可在prompt 里 @ 调用，可以同时调用多个角色，调用方式：https://gpt-best.apifox.cn/api-374618722

新增VIDU接口

节点后续更新

### 20251110:

新增sora2-pro优质分组，网站显示有问题，不是次数，是按秒收费，务必注意！还是比较贵的，只有4秒8秒12秒，原本的也能用，但是奥特曼改了每个账号的次数，所以每天次数有限

插件更新suno_cover，suno_upload_extend，suno_upload:节点`:

suno_upload：上传自己的音频文件，获取clip_ip,用于suno_cover和suno_upload_extend节点。上传音频时长必须在6s-60s内。

suno_cover：音乐翻版\修改风格，输入clip_ip(可以是自己上传的，或者在平台生成的音乐的。PS：自己上传的有可能因为跨账号问题不生效。)

suno_upload_extend：音频续写，输入clip_ip(可以是自己上传的，或者在平台生成的音乐的)

示例工作流后续更新

### 20251106:

增加新节点sora2_openai
是官方格式的节点，暂时只支持图生视频，不支持文生视频

所有Sora2节点新增参数，防止生成视频泄露，已经内置，不需要手动设置

### 20251030:

修正最新comfyui内核节点加载报错的问题

### 20251024-2:

RunningHub上所有API相关工作流均已更新，如果发现有漏网之鱼请B站或者youtube留言发链接，我会及时处理

### 20251024:

更新sora2-chat节点，速度更快，目前只支持横版，竖版15S非HD视频！不支持HD和25S，更稳定

所有工作流全部做了更新，请下载新工作流，搭建方式有所区别

新增sora2-chat对应工作流

另外Sora2-chat节点，生成后可以下载GIF以及视频，在Comfyui节点会生成如下链接，请从控制台中查找

<img src="https://github.com/T8mars/Comfyui-zhenzhen/blob/main/pic/4.png" width="100%" alt="new node">

然后链接复制到浏览器打开，如下也可以下载和分享

<img src="https://github.com/T8mars/Comfyui-zhenzhen/blob/main/pic/5.png" width="60%" alt="new node">

### 20251023:

<img src="https://github.com/T8mars/Comfyui-zhenzhen/blob/main/pic/3.png" width="100%" alt="new node">

新增节点api setting
由于昨天网站被攻击，昨天半夜已经修复，防止再出现类似问题，增加多个可选接口，目前有1个主站，一个美国站，一个香港站，还有个自定义IP接口，RH的工作流需要晚上更新，本地直接改下节点即可

### 20251020-2:

修复上个版本NananaBanana图像编辑比例不生效问题
新增12个包括nanobanana以及veo3,veo3.1的工作流

veo3特价模型基准1.5RMB/8S，模型名字：
veo3 文生视频
veo3-fast 文生视频
veo3-fast-frames 图生视频

Veo3 Pro模型3RMB/8S，模型名字：
veo3-pro 文生视频
veo3-pro-frames 图生视频
高质量模式，价格也高一点

Veo3.1 特价模型基准1.5RMB/8S，模型名字：
veo3.1 文生视频，图生视频
veo3.1-components 文生视频，图生视频，多参1-2张
注意veo3.1-components，支持多图参考，Veo3.1支持首尾帧

Veo3.1 Pro模型基准3RMB/8S，模型名字：
veo3.1-pro  文生视频，图生视频，首尾帧
高质量模式，价格也高一点

注意模型价格可能根据情况调整，实际价格以https://ai.t8star.cn/register?aff=dP7j 为准

### 20251020:

Nano-banana 由于长期风控原因，将于 10.20 日 中午12点涨价至 0.08/次；
官方模型(gemini-2.5-flash-image)价格不变
gemini-2.5-flash-image和gemini-2.5-flash-image-preview模型有概率不出图，只支持chat格式

nano-banana节点已更新，只有edit节点才支持尺寸选择。

Veo3.1节点更新，支持新模型veo3.1，价格不变

工作流一会更新

### 20251018:

目前模型分为sora-2和sora-2-pro版

sora-2 偶发性出水印，价格基准0.1RMB，不支持HD，可选10S和15S，支持横版竖版，画面会有闪烁
sora-2 Pro，无水印，基准价格1.7RMB，10S和15S支持HD，25S不支持HD，支持横版竖版，无闪烁画面，HD非常清晰，非HD一般清晰

务必注意25S不要和HD同时开！

25S 大概需要30分钟
15S HD大概需要20分钟
10S 非HD大概5分钟左右
15S 非HD大概10分钟左右

由于并发压力不同，以上时间仅供参考

更新了6个最终版工作流，可以直接使用

B站教程：https://www.bilibili.com/video/BV1m3WszsEn7/
Youtube教程：https://www.youtube.com/watch?v=bc8b5ZxPvJE

### 20251017-2:

修复了sora-2-pro模型，其中10S和15S支持HD同时开启，25S不支持HD，务必注意！基准都是1.7RMB，无论是不是HD或者是不是25S，25S目前测试下来需要1400秒左右，非常久，务必注意
sora-2模型，是普通版模型，可以输出15S，支持横版竖版，时间预计5-10分钟，基准价格0.1RMB
修改了后台的超时等待时间，从1200秒提高到了3000秒，节点也对应修复

再说一遍，务必注意，HD不支持25S！！！

### 20251017:

更新了工作流，删除老的工作流
目前15S没问题，时间有所延长
25S和HD有点问题，暂时先不要用，白天排查

### 20251016-3:

注意，Sora2更新节点后15S不要开HD，否则会报错！25S才能开HD！

### 20251016-2:

修改Sora2的最大重试次数

### 20251016:

支持Sora2 HD 25S 以及 普通版 15S，无水印，节点已更新，工作流重新拉一下节点即可
Veo3.1已支持，节点明天更新
NanoBanan自定义分辨率已更新，节点明天更新

### 20251014-2:

由于sora2 HD 15S非常需要时间（官方也很慢），将重试时间从120S-调整到180S，目前测试下来大部分在150S-160S时候成功，偶尔也有180S没成功情况
节点超时不代表一定失败，请从贞贞AI工坊-左侧异步任务，点进去可以看看到，点对应任务的蓝色数字链接，从里面下载MP4即可，如果超时会提示超时，超时失败会退费
Sora普通版0.1积分，SORA HD 15S 1.7积分

### 20251014:

删除2个老的SORA2工作流，老版本HD和15S模型下架
sora_video2-portrait-15s 模型下架
sora_video2-landscape-15s 模型下架
sora_video2-portrait-hd-15s 模型下架
sora_video2-landscape-hd-15s 模型下架

新的模型请用：sora-2-pro
工作流：sora2-plus-new-15shd.json

这个版本质量非常高，但是跑起来非常慢，15S差不多10分钟，HD还要单独8分钟，也就是跑一次至少20分钟左右，且有失败概率，如果Comfyui超时了，请去网站查看下异步任务，看看原因，正常失败会退积分。

## 演示视频

[观看项目演示视频](https://github.com/T8mars/Comfyui-zhenzhen/blob/main/pic/ma.mp4)

### 20251010:

Comfly_sora2:节点,新增sora-2-pro模型，目前基准1.7，目前出视频速度较慢，无水印，支持15秒以及HD，工作流同步更新，workflow目录下sora2-plus-new-15shd.json

### 20251009:

Comfly_sora2:节点: 新增sora2视频模型节点，新节点支持直接video combine了，不用再复制链接了！目前无水印，生成最多10s普通画质视频，hd和15s暂时无法使用请知晓。

### 20251005:

更新新节点:OpenAi sora api plus：支持4个新模型，支持15秒时长

上面2个1080P，下面2个是HD，国庆期间依然粉丝价格0.01人民币一个视频

sora_video2-portrait-15s

sora_video2-landscape-15s

sora_video2-portrait-hd-15s

sora_video2-landscape-hd-15s


目前国庆期间依然15S依然是0.01元RMB，给大家玩，祝大家中秋快乐！

更新新工作流：Sora2-Plus-15s-HD.json，15秒专属工作流，支持HD，支持横版及竖版

### 20251002-3：

新版节点可以用以下5个模型，支持横版，复制到节点的model上即可，国庆期间PRO模型也是0.01元RMB，国庆礼物，祝大家国庆玩得开心

竖版高清模型：sora_video2-portrait-hd
横版高清模型：sora_video2-landscape-hd
新版竖版模型：sora_video2-portrait
新版横版模型：sora_video2-landscape
老板竖版模型：sora_video2
更新节点以及示例工作流--Sora2-hd.json

### 20251002-2：

Sora2 Api目前并发较高，如反复出现500代码且报错代码为401，通常是这个APIKEY首先，重新新建一个令牌一般即可解决

20251002：

新增Sora2节点，国庆期间每个10秒视频仅0.01元，目前保存视频节点有点问题，保存video_url，然后复制到浏览器保存视频即可

20250924：

`Comfly_suno:节点`: 新增v5模型


### 20250918：

`Comfly_suno:节点`: 新增Comfly_suno_description，Comfly_suno_lyrics，Comfly_suno_custom三个节点
简单描述生成歌曲，生成歌词，自定义生成歌曲三个节点。

`Comfly_Doubao_Seedream_4节点`: 节点新增自定义尺寸。在aspect_ratio选择Custom，然后可以在width和height自定义。


### 20250911：

`Comfly_Googel_Veo3:节点`: Veo 模型大幅降价，文生视频支持设置横、竖屏


### 20250909：

`Comfly_Doubao_Seedream_4节点`: 新增节点："Comfly Doubao Seedream4.0


### 20250903：

`Comfly_gpt_image_1_edit节点`: 参数新增input fidelity，partial_images参数

### 20250902：

`Comfly_nano_banana_edit节点`: 新增节点Comfly_nano_banana_edit，这个可以选择生成图片的尺寸，模型只能是：nano-banana
文生图下尺寸才能生效，图生图不生效。

### 20250829：

`Comfly_MiniMax_video节点`: 新增节点Comfly_MiniMax_video，支持海螺ai全部视频模型，支持最新首尾帧。
具体模型能力和参数选择请查看官方文档，避免使用错误：
https://platform.minimaxi.com/document/video_generation?key=66d1439376e52fcee2853049


### 20250828：

目前官方返无图的可能性比较高，所以需要你开魔法，并且节点在美国（我测试这样的情况基本没有问题，有问题加群）

`Comfly_nano_banana_fal节点`: 新增节点Comfly_nano_banana_fal，这个可以生成1到4张图片，nano-banana为文生图模型。
nano-banana/edit为图生图模型（图生图模型会产生额外的图片上传费用，具体可以看网站日志，在网站异步任务也可查看任务信息）

`Comfly_nano_banana节点`: 新增模型nano-banana选项，这个模型不容易被识别成对话模型，

### 20250827：

`Comfly_nano_banana节点`: 新增节点：Comfly_nano_banana（文生图，图生图，支持多图参考编辑），
谷歌最强编辑模型：gemini-2.5-flash-image-preview，
有默认和gemini优质两个分组。价格比官方便宜很多。可以在cherrystudio里面的newapi供应商填写我的api中转站调用模型使用。


### 20250819：

`qwen image_edit节点`: 新增千问图片编辑节点：Comfly_qwen_image_edit，价格0.1.
可以自定义尺寸（size选择Custom后，在Custom_size输入分辨率即可，例如1280x720）。
num_images生成图片数量是1到4张，注意api计算是按照图片张数来的，生成越多，api消费就多。

### 20250814：

`doubao节点`: 新增节点：Comfly_Doubao_Seedream和Comfly_Doubao_Seededit都是3.0模型


### 20250807：

`qwen image节点`: 新增千问绘图节点：Comfly_qwen_image，价格全网最低~
可以自定义尺寸（size选择Custom后，在Custom_size输入分辨率即可，例如1280x720）。
num_images生成图片数量是1到4张，注意api计算是按照图片张数来的，生成越多，api消费就多。

### 20250731：

`mj 换脸节点`: 新增mj换脸节点：Comfly_Mj_swap_face，修复mju，mjv节点bug。


### 20250729：

`kling 可灵节点`: 新增可灵多图参考视频节点：Comfly_kling_multi_image2video，最多支持4个参考图，只支持1.6模型。
新增2.1模型选择。 

### 20250722：

`mj video延长节点`: 新增mj视频延长节点：Comfly_mj_video_extend，一次生成4个视频，按次收费。

task id是接入上一次生成视频的task id 输出内容。
index 是选择延长上一次生成的4个视频里面的哪一个做为延迟，范围是0,1,2,3，对应的是第一，二，三，四视频
视频最多延长4次，一次延长4s。

### 20250722：

`mj video节点`: 新增mj视频节点：Comfly_mj_video，一次生成4个视频，按次收费。 


20250716：删除了Comfly_kling_videoPreview节点，视频节点的video输出接口可以直接连接comfyui本体的save video节点。

20250714：

`Googel veo3节点`: veo3谷歌视频，新增veo3-fast-frames模型，图生视频


### 20250630：

`Googel veo3节点`: 

新增Comfly_Googel_Veo3节点，文生视频模型：veo3，veo3-fast，veo3-pro。图生视频模型：veo3-pro-frames。 
enhance_prompt开关：
是否优化提示词，一般是false；由于 veo 只支持英文提示词，所以如果需要中文自动转成英文提示词，可以开启此开关。
目前4个模型都是自动生成带音效的。无法手动关闭，并且不支持选择生成视频尺寸，默认都是生成横幅视频。


### 20250627：

`Flux节点`: Comfly_Flux_Kontext，Comfly_Flux_Kontext_Edit两个节点新增flux-kontext-dev模型


### 20250613：

`Flux节点`: 新增bfl官方节点：Comfly_Flux_Kontext_bfl节点，价格不变

### 20250611：

`Flux节点`: Comfly_Flux_Kontext_Edit节点支持设置出图数量（1-4张范围），这个节点不会消耗上传图片费用，直接传入图片即可，
           跟Comfly_Flux_Kontext一样，就是上传图片不会扣费，图片输入支持base64图片编码格式，可以做为稳定性的备用节点。

### 20250601：

`Flux节点`: Comfly_Flux_Kontext节点支持设置出图数量（1-4张范围），支持多图输入。
已经支持对上一次生成的图片再次提示词编辑（但只有当出土数量选择1时才可以使用这个。


### 20250526：

`Jimeng即梦视频节点`: 新增ComflyJimengVideoApi节点。即梦视频，按次收费，5s是0.6元，10s是1.2元。
<details>
<summary>查看更新/Update </summary>  
 
![75ae4f4c3b061c0a7f7d1b1eb1b0264](https://github.com/user-attachments/assets/a8533eef-8233-4c35-ab1b-c9a26d5ddf72)

</details> 

### 20250518：

`Flux节点`: 新增Comfly_Flux_Kontext节点，支持：flux-kontext-pro和flux-kontext-max模型，按次收费：pro模型大约0.096元，max大约0.192元，比官方便宜很多。


20250518：

`Kling节点`: 可灵节点新增kling-v2-master的可灵2.0模型。价格很贵，按需使用。

20250429：

`Chatgpt节点`: Comfly_gpt_image_1_edit新增chats输出口，输出多轮对话。
新增clear_chats,当为Ture的时候，只能image输入什么图片修改什么图片，不支持显示上下文对话。
当为Flase的时候，支持对上一次生成的图片进行二次修改。支持显示上下文对话。并且支持多图模式下新增图片参考。

<details>
<summary>查看更新/Update </summary>  
 
![2eaf76b077612170647f6861e43e2af](https://github.com/user-attachments/assets/1c4c484f-c3c6-48c6-96c5-58c4ef4e59d5)

![6a43cb051fece84815ac6036bee3a4c](https://github.com/user-attachments/assets/f0fbf71e-8cfb-448e-87cd-1e147bb2f552)

</details> 

20250425：


`Chatgpt节点`: 
新增Comfly_gpt_image_1和Comfly_gpt_image_1_edit官方gpt_image_1模型api接口节点。

模型名都是gpt_image_1，区别只是分组不同：

一共四个分组：default默认分组为官方逆向，价格便宜，缺点就是不稳定，速度慢。按次收费。不支持额外参数选择。这个分组的apikey只能用于ComflyChatGPTApi节点。

其他三个组都是官方api组，最优惠的目前是ssvip组。分组需要再令牌里面去修改选择。这3个官方分组优点就是速度快，稳定性高。支持官方参数调整。
缺点就是贵，但是也比官方便宜。大家可以按照自己的情况选择。这3个分组的令牌的apikey只能用在下面2个新节点上面！！！

1. Comfly_gpt_image_1 节点：文生图，有耕读参数调整，支持调整生图限制为low。

2. Comfly_gpt_image_1_edit 节点：图生图，支持mask遮罩，支持多图参考。

<details>
<summary>查看更新/Update </summary>  
 
![3bc790641c44e373aca97ea4a1de47e](https://github.com/user-attachments/assets/1a7a0615-46e5-46b3-af04-32246a23d6f4)

![5efe58fcf7055d675962f40c1ad1cbb](https://github.com/user-attachments/assets/8a90eab5-4242-43bb-ae01-74493b90b6ce)

</details> 

20250424：
`Chatgpt节点`: ComflyChatGPTApi节点新增官方gpt-image-1，按次计费 0.06，
旧版的gpt4o-image，gpt4o-image-vip，sora_image, sora_image-vip可以做为备选。首选gpt-image-1。

`jimeng即梦节点`: 即梦的ComflyJimengApi节点新增参考图生成图片，image url图片链接参考生成图片。
注意：参考图生成图片会额外消耗上传图片的token费用（具体根据你图片大小来，大部分都是0.000几到0.00几元不等。图片链接有时效性，不做长期储存），
这个只适用于你没有image url图片链接的前提下使用。
如果你有image url图片链接，就直接填写在image url里面既可以。

<details>
<summary>查看更新/Update </summary>  
 
![e1abc11e855680b70985ec9f339a967](https://github.com/user-attachments/assets/6d77c103-d35a-4c6b-804a-4b5add172bcf)

![307e5ea0d789b785fd0a60f01f2b8cf](https://github.com/user-attachments/assets/5c8a7984-ae5e-4cbf-aa47-b09bc7e6f8d6)

</details> 

### 20250422：
`Chatgpt节点`: ComflyChatGPTApi节点新增chats输出口，输出多轮对话。
新增clear_chats,当为Ture的时候，只能image输入什么图片修改什么图片，不支持显示上下文对话。
当为Flase的时候，支持对上一次生成的图片进行二次修改。支持显示上下文对话。

<details>
<summary>查看更新/Update </summary>  

![cad243f2bf4a3aa11163f1a007db469](https://github.com/user-attachments/assets/ef0f6a34-3de7-42a2-8543-c1930575e1bb)

![bd6493050affdf156143c8dc5286988](https://github.com/user-attachments/assets/0906caf3-35ec-4061-bfc9-5f611a19abf2)

![e5b3d375b700dcbf921b12a8aa527c4](https://github.com/user-attachments/assets/75537100-e5d2-403c-b2e0-1f662680092f)


</details> 
