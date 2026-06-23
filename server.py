#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GMV 日报生成器 - 后端服务
部署到云端后，API Key 存在环境变量里，用户无需填写
"""

import os
import base64
import json
import re
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import urllib.request

# 从环境变量读取 API Key（部署时在平台上设置）
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
PORT = int(os.environ.get("PORT", 8080))
STATIC_DIR = Path(__file__).parent

def call_vision_api(prompt, image_data_url_list):
    """调用 DashScope 视觉模型"""
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    content_parts = []
    for data_url in image_data_url_list:
        content_parts.append({"type": "image_url", "image_url": {"url": data_url}})
    content_parts.append({"type": "text", "text": prompt})
    payload_dict = {
        "model": "qwen-vl-max",
        "messages": [{"role": "user", "content": content_parts}],
        "max_tokens": 2000,
        "temperature": 0.1,
    }
    body_bytes = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body_bytes,
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

def extract_json_obj(text):
    """从 AI 返回文本中提取 JSON"""
    try:
        obj = json.loads(text)
        if isinstance(obj, (dict, list)): return obj
    except Exception: pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(1).strip())
            if isinstance(obj, (dict, list)): return obj
        except Exception: pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try: return json.loads(m.group(0))
        except Exception: pass
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        try: return json.loads(m.group(0))
        except Exception: pass
    return None

def build_report(data):
    """生成标准格式报告"""
    out = []
    date_str = (data.get("date") or "").strip()
    out.append(date_str if date_str else "待确认日期")
    out.append("")
    rooms_list = data.get("rooms") or []
    total_val = 0.0
    for r in rooms_list:
        try: total_val += float(r.get("gmv", 0))
        except Exception: pass
    out.append("总gmv：" + (str(round(total_val, 2)) if total_val > 0 else "待确认"))
    out.append("")
    out.append("会员开卡/续卡人数：" + str(data.get("member_new") or "待确认") + "/" + str(data.get("member_renew") or "待确认"))
    out.append("")
    out.append("各直播间gmv")
    out.append("")
    vip_gmv = ""
    other_rooms = []
    for r in rooms_list:
        nm = (r.get("name") or "").strip()
        gm = (r.get("gmv") or "").strip()
        if not nm: continue
        if "会员" in nm: vip_gmv = gm
        else: other_rooms.append((nm, gm))
    out.append("会员店：" + (vip_gmv if vip_gmv else "待填入"))
    for nm, gm in other_rooms:
        out.append(nm + "：" + gm)
    out.append("")
    out.append("今日top10商品：")
    out.append("")
    top10_items = data.get("top10") or []
    if top10_items:
        for idx, item in enumerate(top10_items[:10], 1):
            out.append(str(idx) + ". " + item)
    else:
        for i in range(1, 11):
            out.append(str(i) + ". 待填入")
    return "\n".join(out)

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
            if mime_type is None: mime_type = "application/octet-stream"
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

        if not DASHSCOPE_API_KEY:
            self._json_resp(500, {"success": False, "error": "服务器未配置 API Key"})
            return

        gmv_b64 = payload.get("gmv_image", "")
        top10_b64 = payload.get("top10_image", "")

        # 分析 GMV 截图
        gmv_result = {"date": "", "rooms": [], "member_new": "", "member_renew": ""}
        if gmv_b64:
            ai_text = call_vision_api(
                "请识别这张GMV数据截图，提取信息，严格只返回JSON。字段：date(如6.24), rooms([{name,gmv}]), member_new, member_renew",
                [gmv_b64]
            )
            parsed = extract_json_obj(ai_text)
            if isinstance(parsed, dict):
                gmv_result.update(parsed)

        # 分析 Top10 截图
        top10_list = []
        if top10_b64:
            ai_text = call_vision_api(
                "请识别Top10商品截图，按顺序返回JSON数组，每个元素是商品完整名称。严格只返回JSON数组。",
                [top10_b64]
            )
            parsed = extract_json_obj(ai_text)
            if isinstance(parsed, list):
                top10_list = parsed
            elif isinstance(parsed, dict) and "top10" in parsed:
                top10_list = parsed["top10"]

        final_data = {
            "date": gmv_result.get("date", ""),
            "member_new": str(gmv_result.get("member_new") or "") or "待确认",
            "member_renew": str(gmv_result.get("member_renew") or "") or "待确认",
            "rooms": gmv_result.get("rooms") or [],
            "top10": top10_list,
        }

        self._json_resp(200, {
            "success": True,
            "report": build_report(final_data),
            "data": final_data,
        })

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    print("=" * 50)
    if not DASHSCOPE_API_KEY:
        print("警告：DASHSCOPE_API_KEY 未设置，API 调用将失败")
    print(f"服务启动：http://0.0.0.0:{PORT}")
    print("=" * 50)
    srv = HTTPServer(("0.0.0.0", PORT), Handler)
    srv.serve_forever()
