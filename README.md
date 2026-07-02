# Short Drama Current Skills

本仓库是短剧项目的生产工具与 agent skill 路由仓。

它不替代 `shortdrama-current-state` 的当前事实，也不保存 StoryWeaver / PJ Novel 的原始生产产物。它负责告诉 agent：

- 短剧相关仓库各自是什么定位。
- StoryWeaver / PJ Novel / 图片资产 / 播放收益数据应该从哪里导出。
- 导出的处理后事实应该上传到哪个 current-state 目录。
- 哪些信息可以共享，哪些必须留在生产工具仓、NAS 或 source-bound layer。

## Agent 先读顺序

1. `docs/repo-map-and-source-routing.md`
2. `.codex/CLAUDE.md`
3. 需要具体任务时再读 `.codex/skills/*`

如果伟冬或他的 agent 只需要知道“怎么导出、上传到哪里”，先读第 1 个文件即可。

