#!/usr/bin/env python3
"""自制 YouTube MCP：直接调用 YouTube Data API v3，不经过任何第三方平台。

只用 Python 标准库。两种用法：
  1. MCP（stdio）：python3 server.py
  2. 命令行：
     python3 server.py search "リップサービス 発言" [数量]
     python3 server.py comments <视频ID或URL> [关键词] [最多条数]
     python3 server.py grep "关键词" "视频搜索词" [视频数]   # 搜视频→在评论里找关键词

API key：环境变量 YOUTUBE_API_KEY，通过 X-Goog-Api-Key 请求头发送。
配额（每天 10,000 单位免费）：搜索 100 单位/次，评论 1 单位/页（最多 100 条）。
"""
import json, os, re, sys, urllib.parse, urllib.request

API = "https://www.googleapis.com/youtube/v3/"


def _get(path, **params):
    params = {k: v for k, v in params.items() if v not in (None, "")}
    req = urllib.request.Request(API + path + "?" + urllib.parse.urlencode(params))
    req.add_header("X-Goog-Api-Key", os.environ.get("YOUTUBE_API_KEY", "placeholder"))
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"YouTube API {e.code}: {e.read().decode(errors='replace')[:500]}")


def _video_id(s):
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", s)
    return m.group(1) if m else s.strip()


def search_videos(query, max_results=10, order="relevance", region="JP"):
    d = _get("search", part="snippet", q=query, type="video", maxResults=min(int(max_results), 50),
             order=order, regionCode=region, relevanceLanguage="ja")
    return [{"videoId": i["id"]["videoId"], "title": i["snippet"]["title"],
             "channel": i["snippet"]["channelTitle"], "publishedAt": i["snippet"]["publishedAt"][:10],
             "url": "https://www.youtube.com/watch?v=" + i["id"]["videoId"]} for i in d.get("items", [])]


def video_comments(video, keyword="", max_comments=100, order="relevance"):
    """取评论（含回复）。给了 keyword 就用 API 的 searchTerms 过滤，并在本地再确认一次。"""
    vid, out, token = _video_id(video), [], None
    while len(out) < int(max_comments):
        d = _get("commentThreads", part="snippet,replies", videoId=vid, maxResults=100,
                 order=order, searchTerms=keyword, pageToken=token, textFormat="plainText")
        for t in d.get("items", []):
            top = t["snippet"]["topLevelComment"]["snippet"]
            cs = [("comment", top)] + [("reply", r["snippet"]) for r in t.get("replies", {}).get("comments", [])]
            for kind, c in cs:
                text = c.get("textOriginal") or c.get("textDisplay", "")
                if keyword and keyword not in text:
                    continue
                out.append({"type": kind, "text": text, "likes": c.get("likeCount", 0),
                            "date": c.get("publishedAt", "")[:10], "videoId": vid})
        token = d.get("nextPageToken")
        if not token:
            break
    return out[: int(max_comments)]


def grep_comments(keyword, video_query, videos=5):
    """搜视频，再在每个视频的评论里找含 keyword 的评论。"""
    hits = []
    for v in search_videos(video_query, videos):
        try:
            for c in video_comments(v["videoId"], keyword, 100):
                hits.append({**c, "videoTitle": v["title"], "url": v["url"]})
        except RuntimeError as e:  # 评论关闭等
            if "commentsDisabled" not in str(e):
                raise
    return sorted(hits, key=lambda c: -c["likes"])


TOOLS = {
    "youtube_search": (search_videos, "搜索 YouTube 视频（100 配额单位/次）", {
        "query": {"type": "string"}, "max_results": {"type": "integer", "default": 10},
        "order": {"type": "string", "enum": ["relevance", "date", "viewCount"], "default": "relevance"},
        "region": {"type": "string", "default": "JP"}}, ["query"]),
    "youtube_comments": (video_comments, "读取某视频的评论和回复；keyword 只返回含该词的评论（1 单位/页）", {
        "video": {"type": "string", "description": "视频 ID 或 URL"}, "keyword": {"type": "string"},
        "max_comments": {"type": "integer", "default": 100},
        "order": {"type": "string", "enum": ["relevance", "time"], "default": "relevance"}}, ["video"]),
    "youtube_grep_comments": (grep_comments, "按搜索词找视频，在评论区里挑出含 keyword 的真实评论", {
        "keyword": {"type": "string"}, "video_query": {"type": "string"},
        "videos": {"type": "integer", "default": 5}}, ["keyword", "video_query"]),
}


def serve():
    def send(msg):
        sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n"); sys.stdout.flush()
    for line in sys.stdin:
        if not line.strip():
            continue
        m = json.loads(line); mid, method = m.get("id"), m.get("method")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": m.get("params", {}).get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}}, "serverInfo": {"name": "youtube", "version": "0.1"}}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [
                {"name": n, "description": d, "inputSchema": {"type": "object", "properties": p, "required": r}}
                for n, (_, d, p, r) in TOOLS.items()]}})
        elif method == "tools/call":
            name, args = m["params"]["name"], m["params"].get("arguments", {})
            try:
                res = TOOLS[name][0](**args)
                send({"jsonrpc": "2.0", "id": mid, "result": {"content": [
                    {"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=1)}]}})
            except Exception as e:
                send({"jsonrpc": "2.0", "id": mid, "result": {"isError": True, "content": [{"type": "text", "text": str(e)}]}})
        elif mid is not None:
            send({"jsonrpc": "2.0", "id": mid, "result": {}} if method == "ping" else
                 {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}})


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        serve()
    else:
        cmd = {"search": search_videos, "comments": video_comments, "grep": grep_comments}[a[0]]
        print(json.dumps(cmd(*a[1:]), ensure_ascii=False, indent=1))
