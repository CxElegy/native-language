# YouTube MCP（自制）

直接调用 YouTube 官方的 Data API v3，不经过 vidIQ 这类第三方平台。只用 Python 标准库，不需要安装依赖。

- 在 `.mcp.json` 里注册，Claude Code 打开本仓库时自动加载。
- 需要环境变量 `YOUTUBE_API_KEY`（免费申请：Google Cloud → 启用 YouTube Data API v3 → 创建 API 密钥）。
  在云端会话里，也可以把它存成 `www.googleapis.com` 的 network secret，放在 `X-Goog-Api-Key` 请求头。
- 提供三个工具：
  - `youtube_search`：搜索视频，每次消耗 100 配额单位。
  - `youtube_comments`：读取某个视频的评论；传 `keyword` 时只返回含这个词的评论。每页消耗 1 单位。
  - `youtube_grep_comments`：先搜视频，再在这些视频的评论区里找含 keyword 的评论。
- 每天免费额度是 10,000 单位。

命令行用法：

```bash
python3 tools/youtube-mcp/server.py comments <视频ID> リップサービス 50
```
