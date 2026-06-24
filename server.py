#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GMV 日报生成器 - 本地后端服务
直接运行：python server.py
然后打开 http://localhost:8080
"""

import os
import base64
import json
import re
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import urllib.request

DASHSCOPE_API_KEY = "sk-ws-H.RYMLDHE.whau.MEYCIQDquxZlik8DU5m2K0mSSHGKcwkdJPYVXjgO98gGtq3H-QIhAIPwVswRmUE9XKvHpTOzM6LmgqD21SL69VlG5HPH8MLw"
PORT = 8080
STATIC_DIR = Path(__file__).parent


def call_vision_api(prompt, image_data_url):
    """调用 DashScope 视觉模型"""
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    payload = {
        "model": "qwen-vl-max",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_data_url}}
            ]
        }],
        "max_tokens": 2000,
        "temperature": 0.1,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": "Bearer " + DASHSCOPE_API_KEY,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
    except Exception as exc:
        return "API_ERROR: " + str(exc)


def build_report(gmv_text, top10_text):
    """合并 AI 返回的两部分内容"""
    report = gmv_text.strip()
    if top10_text and top10_text.strip():
        if "今日top10商品" in report:
            # 替换掉占位符
            report = re.sub(r"今日top10商品[：:].*", top10_text.strip(), report, flags=re.DOTALL)
        else:
            report += "\n\n" + top10_text.strip()
    return report


class Handler(BaseHTTPRequestHandler):
    def _json_resp(self, status_code, obj):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/" or path == "/index.html":
            self._serve_file(STATIC_DIR / "index.html")
        elif "/../" in path:
            self._json_resp(403, {"success": False, "error": "Forbidden"})
        else:
            self._serve_file(STATIC_DIR / path.lstrip("/"))

    def _serve_file(self, fpath):
        try:
            resolved = fpath.resolve()
            root_resolved = STATIC_DIR.resolve()
            if not str(resolved).startswith(str(root_resolved)) or not fpath.exists():
                self._json_resp(404, {"success": False, "error": "Not found"})
                return
            data = fpath.read_bytes()
            mime_type, _ = mimetypes.guess_type(str(fpath))
            if mime_type is None:
                mime_type = "application/octet-stream"
            self.send_response(200)
            ct = mime_type + "; charset=utf-8" if mime_type.startswith("text/") else mime_type
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            self._json_resp(500, {"success": False, "error": str(exc)})

    def do_POST(self):
        if self.path.split("?")[0] != "/api/analyze":
            self._json_resp(404, {"success": False, "error": "Not found"})
            return

        clen = int(self.headers.get("Content-Length") or 0)
        if clen <= 0:
            self._json_resp(400, {"success": False, "error": "Empty body"})
            return

        try:
            payload = json.loads(self.rfile.read(clen).decode("utf-8"))
        except Exception as exc:
            self._json_resp(400, {"success": False, "error": str(exc)})
            return

        gmv_b64 = payload.get("gmv_image", "")
        top10_b64 = payload.get("top10_image", "")

        gmv_result = ""
        top10_result = ""

        if gmv_b64:
            gmv_prompt = """你是一个电商直播数据分析助手。请从这张GMV数据截图中提取信息，严格按照格式输出：

【输出格式】
M月D日

总gmv：总GMV数字（保留两位小数，用逗号分隔千位）

会员开卡/续卡人数：开卡人数/续卡人数（如果截图没有则写"待确认"）

各直播间gmv

（每个直播间占一行，格式：账号名：GMV数字，保留两位小数，用逗号分隔千位）
（必须包含"会员店/会员号"，排在所有直播间第一个；截图中没有的账号不写）

今日top10商品：
1. 商品全名1
2. 商品全名2
...
10. 商品全名10

【重要规则】
- 日期：从截图中识别日期，格式 M.D（如 6.24）
- 总GMV：把所有直播间GMV相加自己计算，不要直接用截图中的"总GMV"
- 直播间列表：只输出截图中出现的直播间，不要预设固定列表，新增的账号也要写上，当天没有的账号不要写，每个直播间独立一行
- 会员店/会员号：如果截图中有这个账号，必须排在第一个；如果没有，则不写
- top10商品：如果截图中没有top10商品信息，则写"今日top10商品：待上传截图"
- 数字格式：保留两位小数，千位用逗号分隔（如 75,936.55）
- 每个字段之间用一个空行分隔"""
            gmv_result = call_vision_api(gmv_prompt, "data:image/png;base64," + gmv_b64)

        if top10_b64:
            top10_prompt = """请从这张top10商品截图提取商品名称列表，严格按照以下格式输出：

今日top10商品：
1. 完整的商品名称1（不要截断，尽量还原完整名称）
2. 完整的商品名称2
...
10. 完整的商品名称10

【重要】商品名称必须完整，不要截断。如果名称很长，也要完整输出。"""
            top10_result = call_vision_api(top10_prompt, "data:image/png;base64," + top10_b64)

        report = build_report(gmv_result, top10_result)

        self._json_resp(200, {
            "success": True,
            "report": report,
        })


if __name__ == "__main__":
    print("=" * 50)
    print(f"服务启动：http://0.0.0.0:{PORT}")
    print("=" * 50)
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
