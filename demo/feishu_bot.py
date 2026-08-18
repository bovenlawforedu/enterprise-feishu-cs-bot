"""飞书机器人 · 生产集成附件（技术交付物，对应交付方案 C）。

这是把 Web Demo 里验证过的同一套 RAG 核心（rag / understand / generate）
接到真实飞书开放平台的代码。Web Demo 给非技术面试官看「行为」，
这份代码给技术面试官看「如何真正落地」。

职责链（与 Demo 完全一致）：
  飞书群消息事件 → 提取 @机器人 文本 + 发消息人岗位(从消息体/通讯录取)
  → understand 改写 → rag 检索 → generate 生成(强制引用/拒答) → 飞书回消息

零三方依赖（仅用 urllib）；真实部署只需设置环境变量并暴露 HTTPS 端点。

环境变量：
  FEISHU_APP_ID     飞书自建应用 App ID
  FEISHU_APP_SECRET 飞书自建应用 App Secret
  PORT              本地监听端口（默认 8000）
"""
import os, json, urllib.request, hashlib, hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
import rag, understand, generate, guard

APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
PORT = int(os.environ.get("PORT", "8000"))
_TOKEN = os.environ.get("FEISHU_VERIFY_TOKEN", "")  # 事件订阅的 verify token（可选）
_ENCRYPT_KEY = os.environ.get("FEISHU_ENCRYPT_KEY", "")

# 演示用：仅在通讯录接口不可用时兜底。真实环境优先以飞书通讯录返回的部门/职位为准。
ROLE_BY_USER = {
    # "ou_xxxx": "销售",
}


def fetch_user_info(token, open_id):
    """调飞书通讯录 v3 接口，获取用户部门与职位。需申请权限：
    contact:user.department:readonly / contact:user.base:readonly
    """
    url = f"https://open.feishu.cn/open-apis/contact/v3/users/{open_id}?user_id_type=open_id"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("code") == 0:
            d = data.get("data", {})
            dept_names = [dep.get("name", "") for dep in d.get("department_ids", [])]
            return {"dept": ", ".join(dept_names), "title": d.get("job_title", "")}
    except Exception:
        pass
    return {}


def _post(url, payload, token=None, as_json=True):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def get_tenant_token():
    """获取 tenant_access_token（飞书开放平台鉴权）。"""
    r = _post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
              {"app_id": APP_ID, "app_secret": APP_SECRET})
    return r.get("tenant_access_token", "")


def reply_text(token, chat_id, text, msg_type="text"):
    """通过「回复消息」接口把答案发回群/会话。"""
    _post("https://open.feishu.cn/open-apis/im/v1/messages",
          {"receive_id": chat_id, "msg_type": msg_type, "content": json.dumps({"text": text})},
          token=token,
          as_json=True)


def handle_message(event, token):
    """event: 飞书 message 事件体。返回给调用方的日志字符串。"""
    msg = event.get("message", {})
    text = msg.get("text", "").replace("@_user", "").strip()
    chat_id = msg.get("chat_id") or msg.get("open_chat_id") or msg.get("open_id")
    user_open_id = msg.get("sender", {}).get("sender_id", {}).get("open_id", "")
    # 1) 优先从飞书通讯录读取部门/职位，动态推断角色
    info = fetch_user_info(token, user_open_id)
    role = understand.resolve_role(user_open_id, info.get("dept", ""), info.get("title", ""))
    if role == "其他":
        role = ROLE_BY_USER.get(user_open_id, "其他")
    if not text:
        return "empty text, skip"
    # 2) Query Understanding + 检索 + 内容护栏
    intent = understand.analyze(text, role, "", user=user_open_id)
    chunks = rag.search(intent["rewritten"], k=3)
    best = chunks[0]["score"] if chunks else 0
    answered = best >= rag.MIN_SCORE
    reason = ""
    if answered:
        ok, reason = guard.verify_answerable(text, chunks)
        if not ok:
            answered = False
    if not answered:
        answer = generate.refuse(reason)
    else:
        answer = generate.answer(text, chunks)
        cites = "\n".join(f"· 来源：{c['source']} · {c['section']}" for c in chunks)
        answer = answer + "\n\n【引用来源】\n" + cites
    reply_text(token, chat_id, answer)
    return f"answered={answered} role={role} q={text!r}"


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        # 1) URL 验证（飞书事件订阅首次握手）
        if body.get("type") == "url_verification":
            self._send(200, {"challenge": body.get("challenge", "")})
            return
        # 2) 事件回调
        token = get_tenant_token()
        event = body.get("event", {})
        log = handle_message(event, token)
        self._send(200, {"msg": "ok", "detail": log})

    def log_message(self, *a):
        pass


def main():
    rag.load_or_build()
    print(f"飞书机器人已就绪（需配置 FEISHU_APP_ID/SECRET 并配置事件订阅回调到 /）。")
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
