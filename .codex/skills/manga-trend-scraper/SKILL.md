---
name: manga-trend-scraper
description: >
  Use when the user needs to login to WeChat Official Account backend, scrape or backfill manga ranking
  articles, refresh the manga trend database, or judge which mangas and topics are rising or falling based
  on existing trend data. Triggers on login, daily refresh, backfill, trend reading, and database-refresh
  requests. Prefer reading existing snapshots before scraping again unless the user explicitly asks for new data.
---

# Manga Trend Scraper

## Overview

你负责把“漫剧有数”的日榜数据稳定抓进项目内趋势数据库，并让 agent 能基于结构化历史数据做趋势判断。

你的核心任务是：
1. 判断当前是需要登录、抓最新、回填历史，还是只读数据库做分析
2. 优先复用项目内已有数据，不要每次都重跑抓取
3. 抓取完成后把结果沉淀到 `data/manga-trends/`
4. 输出时直接回答“这跟赚钱和方向判断的关系是什么”

## 模式判断

- 用户说“登录公众号后台” → `Login Mode`
- 用户说“抓漫剧日榜”/“更新漫剧趋势库” → `Daily Scrape Mode`
- 用户说“回填漫剧榜单”/“补历史” → `Backfill Mode`
- 用户说“哪些剧在上涨/下滑”/“分析最近漫剧趋势” → `Analysis Mode`

## 工作流程

### 1. 先检查数据状态

优先检查：
- `data/manga-trends/config/session/` 是否存在并可用
- `data/manga-trends/daily/` 是否已有快照
- `data/manga-trends/index/latest.json` 是否存在

### 2. Login Mode

当首次运行或 session 失效时：
- 指导运行 `python -m scripts.manga_trends login`
- 登录必须走有头模式
- 成功后复用 session，后续默认无头

### 3. Daily Scrape Mode

当用户要更新最新数据时：
- 若 session 缺失或失效，先走 Login Mode
- 否则运行 `python -m scripts.manga_trends scrape-day`
- 完成后读取最新 `daily/*.json` 与 `reports/*.md`
- 汇报：新增日期、是否成功落榜单、当前最值得关注的趋势变化

**失败分流：**
- session 失效 → 明确要求先重新登录，不假设无头还能继续
- 抓取失败但本地已有历史快照 → 先说明最新刷新失败，再降级基于现有数据库继续做趋势判断
- 抓取失败且本地没有可用快照 → 直接标记为阻塞，说明卡点、影响和下一步处理
- 连续失败或异常类型不明确 → 升级为需要用户拍板的问题，不在 skill 内硬猜

### 4. Backfill Mode

当用户要补历史数据时：
- 先确认日期范围
- 运行 `python -m scripts.manga_trends backfill --start YYYY-MM-DD --end YYYY-MM-DD`
- 只汇报：新增日期数、失败日期数、主要异常

### 5. Analysis Mode

当用户只问趋势判断时：
- 优先读取 `data/manga-trends/daily/` 和 `data/manga-trends/index/`
- 不重跑抓取，除非用户明确要求更新最新数据
- 输出必须覆盖：
  - 哪些剧在上涨 / 下滑
  - 哪些是新入榜
  - 哪类题材或形式在变强/变弱
  - 这和赚钱机会的关系是什么

**收口规则：**
- 不只报榜单变化，要明确这些变化更像“短期波动”还是“值得继续跟的方向信号”
- 如果证据不足，不要硬下方向结论，要明确说还缺哪几期数据或哪类对照
- 如果已经足够支持方向判断，直接给出“继续跟 / 观察 / 暂不跟”三级结论

## 回传与复盘

每次执行完抓取或分析后，优先回收这几项：
- 是否完成本轮更新 / 分析
- 卡在哪一环
- 哪个环节最耗时或最不稳定
- 是否生成了可复用的 `daily/*.json` / `reports/*.md`
- 这次结果是否足以支持方向判断

如果是抓取任务，输出至少要有：
- 新增日期数 / 成功日期
- 失败日期数 / 失败类型
- 当前数据库是否可继续用于趋势判断

如果是分析任务，输出至少要有：
- 上涨 / 下滑 / 新入榜
- 值得继续跟的题材或形式
- 当前判断还缺什么证据

## 输出规则

- 简洁，直接说结论
- 不把抓取日志原样倒给用户
- 如果失败，要说清：卡在哪、不解决会怎样、下一步怎么处理
- 做趋势分析时，优先基于结构化快照，不靠自由文本硬猜
- 每次都回答：这次结果和赚钱判断、选题判断的关系是什么

## 绝对禁止

- 不在已有数据足够时重复抓取
- 不把旧项目 `app.py` 当作运行时依赖
- 不跳过登录态检查直接假设无头可用
- 不只输出自由文本报告而不看结构化榜单数据
- 不在证据不足时硬给方向性结论
