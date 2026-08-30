# 最近 3 个 Commit 深度审查报告

- 审查时间：2026-07-06
- 审查范围：`7a1016c`（衍生资产生图流程实现，07-01）、`e8092c7`（分镜制作工作台-分镜脚本生成，07-05）、`b68c010`（分镜制作工作台-媒体视频服务集成，07-05，当前 HEAD）
- 审查方式：3 个并行深度审查代理逐 commit 通读 diff 与工作区实现 + 主线程独立交叉验证（实际运行 pytest、vue-tsc、模块导入实测、git 对象统计）
- 变更体量：约 9,000 行代码新增 + 约 470MB 二进制文件入库

## 综合结论

**综合评分：63/100，建议：退回修复。**

| 维度 | 7a1016c | e8092c7 | b68c010 | 综合 |
|---|---|---|---|---|
| 业务实现 | 68 | 78 | 70 | **72** |
| 代码质量 | 74 | 62 | 42 | **58** |
| 逻辑缜密 | 65 | 70 | 62 | **66** |

三条主业务链路（衍生资产生图、分镜脚本生成、媒体视频生成）在架构方向与复用纪律上是健康的，但 b68c010 引入了三个"一票否决"级问题：真实云凭据入库、测试套件被弄断、巨量二进制入库。按 CLAUDE.md 决策规则（<80 分退回），必须退回修复后重新审查。

## P0 — 必须立即处理（均已本地实证）

### P0-1【严重·安全事故】阿里云 AccessKey 明文硬编码进 git（b68c010 引入）

`backend/app/core/config.py:158-159`：

```python
media_s3_access_key_id: ... os.getenv("MEDIA_S3_ACCESS_KEY_ID", "LTAI5t8UdeQmMuLrbjZd5tdP")
media_s3_secret_access_key: ... os.getenv("MEDIA_S3_SECRET_ACCESS_KEY", "PQhqD5kBVuQnCp1rewtvi08IDZXiGR")
```

连同真实 bucket `nonaforage`（:155）、北京 endpoint、CDN 域名一并作为代码默认值提交。任何拿到仓库的人可全权读写删该 OSS 桶并产生费用。密钥已进入版本历史，仅改文件无效。
**处置**：立即在阿里云控制台吊销该密钥对 → 换新密钥仅经环境变量注入 → `git filter-repo` 清除历史。

### P0-2【严重】测试套件被 b68c010 弄断，收集阶段即中断（本地实测复现）

b68c010 删除了 `AssetMedia`/`AssetGeneration` 模型，但 1206 行旧服务 `backend/app/services/asset_media.py` 与其测试 `test_asset_media_service.py` 原样保留：

```
app\services\asset_media.py:24: ImportError: cannot import name 'ASSET_GENERATION_STATUS_FAILED' from 'app.models.asset'
!!!! Interrupted: 1 error during collection !!!!  (123 tests collected, 1 error)
```

整个 pytest 无法运行——证明该 commit 提交前未执行过测试，直接违反本仓库"每次改动必须本地验证、失败立即终止提交"的强制准则。asset_media.py 的约 30 个函数已被复制进 media.py，旧文件成为 ImportError 死代码，还与 media.py 构成大面积重复实现（`ASSET_IMAGE_PROMPT_TASK_TYPE`、`generate_asset_image`、`_build_derivative_edit_prompt` 等同名双份）。
**处置**：删除 asset_media.py；将 test_asset_media_service.py 的两个纯函数测试迁移指向 `services/media.py` 的对应实现。
**附**：排除坏文件后其余测试 106 通过 / 17 失败；17 个失败全部是 user 模块 `[trio]` 参数化用例的事件循环问题（`RuntimeError: There is no current event loop`），与本次 3 个 commit 变更文件零交集，属历史遗留基线问题——但也说明测试基线长期是红的。

### P0-3【严重】约 470MB 生成图片 PNG 提交进 git，且无 .gitignore 排除规则

- e8092c7：17 个 PNG（`data/asset_media/...`，约 216MB）
- b68c010：20 个 PNG（`data/media/...`，约 254MB）——**同一批图换目录二次入库**
- 全仓库截至 HEAD 共跟踪 205 个图片文件、约 799MB，`.git` 目录已达 851MB
- 根 `.gitignore` 仅排除 `data/skills`、`data/models/`、`data/chroma/`，无 `data/media/`、`data/asset_media/`

**处置**：`.gitignore` 增加两条规则 + `git filter-repo` 清历史（可与 P0-1 一次完成）。

## 逐 Commit 评估

### 7a1016c 衍生资产生图流程实现（业务 68 / 质量 74 / 缜密 65）

实现衍生资产生图闭环：`edit_image` 网关链路（OpenAI 兼容 `/images/edits` multipart）、参考图三级回退（显式参考图→父资产封面→父资产最新图）、提示词合成从 300 秒同步 HTTP 改为异步任务+轮询。

**亮点**：`edit_image` 与既有 `generate_image`/`generate_video` 严格同构复用；前后端双重边界校验（父未绑定/父无图，中文可操作报错）；`_MediaTiming` 阶段计时贯穿成功与失败路径；前端按资产 keyed 的轮询状态 + 资产切换双向 ID 比对，竞态防御在同类代码中相当细致。

**关键问题**：
- 【严重】多参考图 multipart 键名错误：所有图都用 `image` 字段名，OpenAI 多图编辑要求 `image[]`，多图场景静默退化为单图——而前端默认全选父资产所有图，多图是常态路径。铁证是后续 commit 自己修复了（当前 provider_runtime.py:733-734 `field_name = "image[]" if len(file_parts) > 1 else "image"`）并补了测试。核心卖点"父级参考图强约束"在该 commit 时点实际失效。
- 【中等】失败的 `AssetGeneration` 记录被任务处理器 rollback 吞掉，FAILED 生成记录永不落库，且 `TaskHandlerFailure.result` 携带的 `generation_public_id` 指向已回滚的幽灵行，诊断信息误导。
- 【中等】`count>1` 时封面 check-then-act 跨 worker 竞态（worker 并发 4），可产生双 `final` 封面，无 (asset, media_role) 唯一约束兜底。
- 【中等】批量资产 + 参考图交叉污染：`build_image_generation_task_items` 把同一份参考图复制进每个资产子项，多资产提交时全部使用第一个资产父级的参考图；当前仅靠前端只传单资产侥幸规避。
- 【中等】上传参考图功能三层实现齐全（路由/服务/前端 API）但前端零调用点，且 UI 过滤掉 `reference` 角色媒体——上传后无处展示无法选用，半成品功能。
- 【中等】`main_asset` 推断脆弱："非主即衍生"，抽取 LLM 漏输出 `main_asset` 字段时普通资产被误判为衍生资产，生图直接被阻断；未用既有的 child_of 关系交叉校验。
- 【中等】提示词轮询无次数上限（对比媒体轮询有 120 次上限），worker 宕机时生成按钮永久 loading。
- 【中等】`response_format: "b64_json"` 硬编码与目标模型 gpt-image-1 的 edits 接口矛盾（官方不接受该参数），依赖第三方网关宽容度。
- 【轻微】`model_id` 入参为摆设（无条件被 `project.image_model` 覆盖）；durationMs 前端两处口径不一；队列名复用 `ASSET_EXTRACT_QUEUE_NAME` 语义错位；5 个文件缺行尾换行；750 行后端变更仅 1 个测试用例且没测到最高风险的 `_build_image_edit_files`（S1 缺陷恰在此处）。

### e8092c7 分镜制作工作台-分镜脚本生成（业务 78 / 质量 62 / 缜密 70）

后端新增 `StoryboardShot` 模型/迁移（含 episode+shot_index 唯一约束）、902 行 storyboard 服务（LLM 流式生成→多级解析容错→幂等落库）、REST 路由与任务 handler；前端新增 1394 行 Production.vue 工作台及 ModelGroupSelect/useProviderModels 复用组件。

**亮点**：幂等 upsert 设计周全（锁定行跳过覆盖、未命中旧行软删、软删行复用复活）；LLM 输出解析四级容错（fenced 代码块→JSON 数组正则→dict 包装键探测→中英文字段别名，最后回退剧本正文规则解析并以 `parse_status` 标记来源）；风格手册加载有路径遍历双重防护；全面复用既有基建（gateway/task engine/PromptRegistry/BaseView）；`_StoryboardTiming` + prompt_trace 可观测性完整。

**关键问题**：
- 【严重】902 行核心 service 零测试：commit 标题是"分镜脚本生成"，但附带的两个测试文件全部服务于顺带修改的图片编辑功能；`parse_storyboard_table`/`normalize_storyboard_row`/`persist_storyboard_rows` 均为最适合单测的纯函数，无回归保障。
- 【中等】LLM 输出重复 sequence 时 rows 内部不去重、循环内 `by_index` 不随新建行更新，直撞唯一约束 → IntegrityError 不属于 `StoryboardServiceError`，落入 worker 裸兜底，用户看到原始 SQL 报错且 prompt_trace 丢失。
- 【中等】同一分集并发生成无任何防护：前端按钮不含运行中判断、服务端无互斥检查，worker 并发 4 下竞态 IntegrityError 或互相覆盖。
- 【中等】前端轮询飞行请求竞态：`tick` 内 await 期间组件卸载，await 返回后重新 `setTimeout` 注册，轮询链复活无人清理；catch 分支无限重试无退避。
- 【中等】后台任务完成触发 `loadShots()` 整体替换 shots → `selectedShot` 新引用触发 watch → `syncEditForm` 静默覆盖用户正在编辑的抽屉表单，未保存输入丢失。
- 【中等】资产关联两处歧义：asset_lookup 数字键空间中 index 与 asset.id 互相覆盖（LLM 回传数字无法区分归属，可绑定到错误资产）；fallback 路径"键名包含于动作文本"匹配，`"1" in "拿起1把剑"` 为真导致必然误匹配。
- 【中等】前端编辑 assetNames 不同步 assetPublicIds，两字段脱钩后续按 ID 取参考图引用错误资产。
- 【中等】核心 prompt 契约文件 `data/skills/storyboard_table_generation.md` 被 .gitignore 排除未入库：字段名契约（sequence/lines/associateAssetsIds）与代码解析强耦合，新环境静默降级为 5 行极简 fallback prompt，部署不可复现。
- 【轻微】prompt 要求 LLM 输出 emotion/sound 字段但落库全部丢弃；无新增镜头/重排 API（编辑闭环缺口）；Production.vue 侧边栏与暗色样式跨页第三次复制（达到"重复三次应抽象"阈值）；剧本正文硬截断 9000 字符用户无感知；`load_style_context` 同步 IO 阻塞事件循环。

### b68c010 分镜制作工作台-媒体视频服务集成（业务 70 / 质量 42 / 缜密 62）

建立统一媒体中枢：`MediaAsset` 单表取代 `AssetMedia`+`AssetGeneration` 双表，1828 行 media 服务、391 行存储抽象（local/S3/OSS）、622 行数据迁移（迁行+搬文件+删旧表）、火山方舟视频 Provider（提交+轮询）。

**亮点**：迁移脚本实现完整可逆 downgrade（重建旧表、`params._legacy` 逆向还原、文件缺失告警跳过不中断）；存储抽象干净（策略模式三实现、boto3/oss2 惰性导入、`normalize_storage_key` + resolve 双重防路径逃逸、同步 IO 全部 `asyncio.to_thread` 包装）；视频轮询健壮（deadline 超时、连续错误容忍 3 次、区分 failed/cancelled 终态）；`cover_urls_for` 批量查询避免 N+1。

**关键问题**（P0-1/2/3 之外）：
- 【中等】`app/models/__init__.py` 未注册 `app.models.media`：alembic autogenerate 依赖 `from app.models import *` 收集元数据，下次自动生成迁移会误产出 drop `af_media_asset` 的迁移。
- 【中等】迁移中 `shutil.move` 文件搬运游离在数据库事务之外：后续步骤失败则 DB 回滚为旧结构而文件已离开旧布局，旧表 storage_key 全部指向空路径，无补偿逻辑。
- 【中等】迁移静默丢数据面：`started_at`/`completed_at` 查了不迁、downgrade 时 `negative_prompt` 恒写空串、INNER JOIN 使孤儿媒体行静默随 drop_table 湮灭且无计数告警。
- 【中等】`params: dict` 无键白名单：用户可传 `model`/`content` 覆盖 provider 请求体（`{"model": ..., **body_extra}` 展开在后），传 `model_id`/`prompt` 则触发 `TypeError: multiple values`，该异常不在 `except (ProviderModelGatewayError, MediaServiceError)` 范围内，裸冒泡到任务引擎。
- 【中等】OSS 后端凭据链路断裂：`OSS2MediaStorage` 构造收下的密钥参数从未使用，只认 `OSS_ACCESS_KEY_ID` 环境变量，选 oss 后端必然运行时报错；`backend_name = "s3"` 使 OSS 媒体行在库中伪装成 s3。
- 【中等】远端视频任务无取消：轮询超时/失败两条路径都不调用方舟取消接口，远端继续跑完并计费，结果丢弃。
- 【中等】大文件三处全量驻内存：上传先整读再校验（视频上限 512MB → 单请求 512MB 峰值）、生成结果全量下载无流式落盘、帧图最多 6 张×20MB base64 进 JSON body（bytes→b64→json 三次复制，请求体可达 160MB+）。
- 【中等】failed 状态机名存实亡：代码承诺 `pending→processing→ready/failed` 且失败时置 FAILED 并 flush，但任务处理器随即 rollback（注释自认"不留半行"）——新链路失败历史永不落库，而迁移却专门归档旧失败记录，同表新旧行为自相矛盾。
- 【中等】media.py 1828 行上帝模块：承担存储键/上传/分发/缩略图/删除/视频生成/资产提示词合成/资产生图/封面/3 套任务提交等 8 类职责；跨模块调用 asset_service 的 4 个私有函数（`_parse_object_field` 等），asset.py 反向局部导入规避循环依赖——双向私有耦合。
- 【中等】commit 名为"分镜制作工作台-媒体视频服务集成"，但 storyboard 服务/路由与前端对 media_service 零引用，`MEDIA_SCOPE_SHOT` 只是占位——分镜侧集成实际未发生，提交名与内容不符。
- 【轻微】本地写非原子（直写目标路径，中断留半文件且 exists 判真）；新生成媒体 `provider_key` 恒为空（建了索引的字段不写值）；`MediaAssetRead.params` 把含旧存储路径的 `_legacy` 内部 JSON 原样暴露给前端；content/thumbnail 端点忽略 URL 中的 project 参数、与同文件其余端点鉴权口径不一致（"uuid 即凭据"是文档化的有意设计，但媒体 URL 会进浏览器历史/代理日志，建议团队显式确认）；混入 70+ 行无关的主/衍生资产重构；`ASYNC_TASK_MODULES` 需手工配置新任务模块但无任何部署文档；`_payload_str_list` 与 `_dedupe_text_list` 重复实现。

## 三维度横向分析

**业务实现（72/100）**：三条主链路均真实闭环——衍生生图（父子绑定→三级参考回退→edit 派发→落盘→封面）、分镜生成（分集→LLM→四级解析→幂等落库→工作台编辑/锁定）、视频生成（API→任务→方舟提交轮询→下载→回写 ready），前后端贯通且边界报错中文可操作。失分集中在"最后一公里"：多图参考在 7a1016c 时点实际失效、上传参考图断链、分镜-媒体集成名不副实、分镜资产关联存在两处必然误绑定的歧义、emotion/sound 要而不存。模式是"主干真实可用，支线存在静默失效"，而静默失效比报错更危险。

**代码质量（58/100）**：结构层面值得肯定——router→service→gateway→provider→task 分层稳定，新能力一律同构挂接既有基建而非另起炉灶，中文注释描述意图与约束（如"事务回滚不留半行媒体"），前端 vue-tsc 零错误（本地实测）。但工程纪律在 b68c010 崩坏：测试套件被弄断且 3900 行零新增测试（前一个 commit 还带测试，最后反而清零）、1206 行 ImportError 死代码与 media.py 大面积同名双份实现并存、真实云凭据与 470MB 二进制入库、commit 粒度混入无关重构。三个 commit 的测试投入依次为 1 个用例 / 94 行（测错重点）/ 0，与 CLAUDE.md"每次实现必须提供可自动运行的测试"的强制要求持续背离。

**逻辑缜密（66/100）**：局部防御的细致程度超过多数同类代码——存储键双重防逃逸、风格路径白名单+relative_to 校验、LLM 解析四级容错+规则 fallback、轮询 deadline/终态区分、前端资产切换双向 ID 比对。但系统性缝隙呈现同一模式：**单线程视角缜密，并发与事务边界视角缺位**。三处 check-then-act 竞态（封面×2、同分集并发生成）均无数据库约束兜底；失败状态机在两条链路上都被 rollback 语义架空（FAILED 行永不落库、result 引用幽灵行）；文件系统操作（迁移搬文件、媒体落盘）游离在数据库事务之外无补偿；params 直通打穿 provider 请求体。这些不是极端 case——worker 默认并发 4、前端默认全选多图、LLM 输出重复序号，都是常态输入。

## 演进轨迹观察

4 天内同一领域三次重写：07-01 在 asset_media.py 上构建生图闭环（+490 行）→ 07-05 上午顺带增强它并补测试 → 07-05 下午整体平移进 media.py 并删除其依赖的模型，但不删旧文件。架构方向（统一媒体中枢）是对的，但"平移不清尾"直接制造了 P0-2。同一批测试图片也因目录方案变更（data/asset_media → data/media）被二次提交，二进制债务翻倍。建议后续大重构以"迁移+删除+测试绿"为同一 commit 的完成定义。

## 修复优先级清单

1. **今天**：吊销并轮换阿里云密钥（P0-1）；删除 asset_media.py、迁移其测试、恢复 pytest 可收集（P0-2）；.gitignore 增加 `data/media/`、`data/asset_media/`（P0-3 止血）。
2. **本周**：`models/__init__.py` 注册 media 模型（防 autogenerate 事故）；params 白名单化（Pydantic 模型枚举合法键）；封面/分镜并发加唯一约束或行锁；分镜 sequence 去重；前端轮询加 stopped 标志与次数上限；修复编辑表单被后台刷新覆盖。
3. **规划内**：`git filter-repo` 清理 799MB 历史与密钥（需协调所有协作者）；media.py 按"通用媒体能力 / 资产生图业务"拆分并消除双向私有耦合；失败状态机重设计（FAILED 行独立事务落库或废弃该状态）；为 media.py/storyboard.py/迁移补测试；prompt 契约文件纳入版本控制；大文件流式化。

## 审查留痕

- 主线程独立验证项：config.py 凭据（读取确认）、asset_media ImportError（`python -c` 复现）、pytest 收集中断与 106/17 通过面（实际运行）、git 二进制统计（`git ls-tree -r -l`）、vue-tsc 通过（实际运行）、media.py 函数清单、LocalDisk 非原子写、params 透传链路、storyboard 解析函数、tasks 层事务语义。
- 三个审查代理合计执行 114 次工具调用，全部发现要求 file:line + 代码摘录证据；与主线程交叉验证无矛盾结论。
- 说明：CLAUDE.md 指定的 sequential-thinking / shrimp-task-manager / desktop-commander 等 MCP 工具在本会话环境不可用，以内置深度推理、并行审查代理与本地命令验证等价替代，验证均可重复。
