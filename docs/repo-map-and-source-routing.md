# 短剧生产仓库定位与 source routing

更新时间：2026-07-02
状态：current routing draft，等待伟冬按实际导出习惯校准

## 1. 适用仓库

本文件只覆盖当前实际会用到的短剧生产协作仓。Vincent 个人 fork 不计入日常 operating map。

| 仓库 | 定位 | Owner / 可见性 | 主要放什么 | 不放什么 |
|---|---|---|---|---|
| `Little-viva1/shortdrama-current-state` | 当前事实与共享生产台账 | Vincent owner；伟冬可见 | 处理后的生产事实、阶段门、缺口、owner action、成本/效率口径、可共享来源索引 | 原始媒体、大 JSON、账号凭据、后台截图原图、未处理长逐字稿 |
| `58164542/StoryWeaver-AI_v1.3.1` | StoryWeaver 生产工具仓 | 伟冬 owner | 分镜到图片/视频的自动化 run、worklog、metrics、错误、reroll、工具能力变更 | current-state 结论、跨项目经营判断 |
| `58164542/PJ_noveal` | PJ Novel 文本/小说/分集生产工具仓 | 伟冬 owner | 选本、小说改编、分集文本、EP 进度、文本生产 run trace | current-state 结论、媒体资产 |
| `58164542/storyweaver-images` | StoryWeaver 图片资产仓 | 伟冬 owner | 可版本化的图片资产、图片 prompt / id / 产物索引 | 大视频、经营结论、敏感账号信息 |
| `Little-viva1/shortdrama-current-skills` | 生产工具 skill 与路由仓 | Vincent owner；公开可读 | agent skill、导出/上传规则、仓库定位、重复工作 SOP | daily truth、作品生产事实、原始材料 |

## 2. Agent 默认读法

伟冬的 agent 每次接短剧生产协作任务时，按下面顺序读：

1. 本文件：确认仓库定位、导出字段和上传落点。
2. 生产工具仓自己的当前入口：
   - StoryWeaver：优先读 `agent/worklogs/daily/`、`agent/worklogs/metrics/`、最近提交和工具 README。
   - PJ Novel：优先读 `dashboard.md`、`portfolio.md`、`novels/*`、最近提交；若后续新增 `agent/worklogs/daily/`，以 daily worklog 为准。
3. `shortdrama-current-state`：
   - `facts/production/current-production-flow-2026-07.md`
   - `ops/source-governance/storyweaver-pj-daily-sync-routing-2026-07.md`
   - `NEXT_ACTIONS.md`

## 3. 导出与上传路由

| 来源 | 系统可直接导出的内容 | 上传到 current-state 的位置 | 共享标准 |
|---|---|---|---|
| StoryWeaver run | 日期、作品/剧目、episode、shot id、阶段、生成次数、失败类型、reroll 次数、机器耗时、模型/供应商、现金成本、可用镜头数 | `sources/storyweaver-processed/YYYY-MM-DD-*.md/json`，汇总后进 `facts/production/` | 可共享处理后 trace；不上传原图/原视频/密钥/本机绝对路径 |
| PJ Novel run | 日期、项目、文本阶段、EP 编号、输入来源、输出文件、改写轮次、人工介入点、阻塞、下一步 | `sources/pj-novel-processed/YYYY-MM-DD-*.md/json`，汇总后进 `facts/production/` | 可共享阶段和进度；原始版权文本、长篇未脱敏材料留在工具仓或 source-bound layer |
| storyweaver-images | 图片 asset id、版本、对应 shot、是否通过审核、reroll 原因 | current-state 只存索引和状态；大图留图片仓或 NAS | GitHub current-state 不镜像图片本体 |
| 播放/收益/结算后台 | 播放、有效播放、收益、扣减、可提现、平台、统计时间 | `sources/copyright-metrics-processed/`，汇总后进 `facts/commercial/` | 只存脱敏结构化数据和口径；后台截图原图、账号信息不进 GitHub |
| 会议/语音/日记反馈 | 审核结论、返工原因、owner 决策、下一步 | `sources/meetings-processed/` 或 `sources/human-feedback-processed/` | 只写处理后结论；不要求人额外填重表 |

## 4. 人工与机器要分开记

生产效率判断必须拆成两类：

- 机器时间：模型生成、排队、上传、转码、批处理等待。它主要影响排产周期，可以通过并发、队列、批量调度和模型路由优化解决。
- 人的时间：选本判断、审美审核、失败镜头判定、重 roll 决策、字幕/封面/包装判断、平台上传和异常处理。它才是人的精力成本和组织瓶颈。

因此 daily trace 不要只写“总共花了多久”，至少拆成：

| 字段 | 解释 |
|---|---|
| `machine_elapsed_minutes` | 机器从开始到结束的自然时间 |
| `machine_active_minutes` | 可估算的模型/脚本实际执行时间 |
| `human_touch_minutes` | 人实际看、判断、修改、沟通的时间 |
| `reroll_count` | 因人工审核不达标而重新生成的次数 |
| `blocked_owner` | 当前真正卡住的人或系统 |
| `cash_cost_rmb` | 可追踪的模型/API/云端费用 |
| `evidence_ref` | 指向工具仓 worklog、commit、飞书表、会议结论或后台导出 |

## 5. 反馈保持轻量

能从系统直接导出的，优先用稳定字段和脚本导出，不要让人手填。

需要人工反馈的，只要求给出最低可用证据：

- 飞书会议逐字稿或会议纪要。
- 飞书表格的一行审核结果。
- 日记 / 周报里的线索。
- 语音聊完后的 agent 清洗结论。
- 对具体 shot / episode 的“通过 / 重 roll / 放弃 + 原因”。

不要为了追求完整系统，让伟冬、思泽每天填一套重型反馈表。agent 的责任是把轻量反馈整理成 current-state 可消费的事实。

## 6. 不要 claim

除非 current-state 已经收到播放、收益、成本和可复核生产 trace，否则不要 claim：

- 某部剧已经商业验证成功。
- 两周 trial 已经完成。
- StoryWeaver / PJ Novel 已经稳定自动化闭环。
- 成本已经可准确核算。
- 机器时间等于人的时间成本。

当前更稳妥的口径是：StoryWeaver / PJ Novel 已经从普通参考源升级为生产 trace source；是否能把“短剧两周 trial / 证据缺口”升级成具体剧目、播放、收益、成本状态，取决于日同步能否补齐真实产出、返工、发布时间、播放和结算证据。

