"""零依赖 Web 服务：静态首页 + JSON API。"""
import json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import rag, store, generate, understand, guard

BASE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(BASE, "static", "index.html")


def _body(handler):
    n = int(handler.headers.get("Content-Length", 0))
    return json.loads(handler.rfile.read(n) or b"{}")


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj=None, html=None):
        self.send_response(code)
        if html is not None:
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/index.html"):
            with open(INDEX, encoding="utf-8") as f:
                self._send(200, html=f.read())
        elif p == "/api/docs":
            self._send(200, rag.list_docs())
        elif p == "/api/unanswered":
            self._send(200, {"unanswered": store.aggregate()})
        elif p == "/api/whoami":
            q = parse_qs(urlparse(self.path).query)
            role = understand.resolve_role(
                (q.get("user") or [""])[0],
                (q.get("dept") or [""])[0],
                (q.get("title") or [""])[0],
            )
            self._send(200, {"role": role})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        p = urlparse(self.path).path
        try:
            d = _body(self)
        except Exception:
            d = {}
        if p == "/api/ask":
            q = (d.get("question") or "").strip()
            u = d.get("user") or "匿名员工"
            role = d.get("role") or ""
            context = d.get("context") or ""
            dept = d.get("dept") or ""
            title = d.get("title") or ""
            # 1) Query Understanding：依飞书身份标签 + 岗位 + 上下文改写模糊提问
            intent = understand.analyze(q, role, context, user=u, dept=dept, title=title)
            # 2) 检索改写后的查询（命中率更高）
            chunks = rag.search(intent["rewritten"], k=3)
            best = chunks[0]["score"] if chunks else 0
            answered = best >= rag.MIN_SCORE
            # 3) 内容级护栏：即使分高，也要确认资料真正回答了问题（如“联系谁”需有联系人信息）
            reason = ""
            if answered:
                ok, reason = guard.verify_answerable(q, chunks)
                if not ok:
                    answered = False
            if not answered:
                self._send(200, {"answer": generate.refuse(reason), "citations": [],
                                 "answered": False, "intent": intent})
            else:
                cites = [{"source": c["source"], "section": c["section"],
                          "snippet": c["text"][:200]} for c in chunks]
                self._send(200, {"answer": generate.answer(q, chunks),
                                 "citations": cites, "answered": True,
                                 "intent": intent})
            store.log(q, u, answered, chunks[0]["source"] if chunks else None)
        elif p == "/api/add_doc":
            title = (d.get("title") or "").strip()
            text = (d.get("text") or "").strip()
            question = (d.get("question") or "").strip()
            if title and text:
                rag.add_doc(title, text)
                n = store.resolve(question, title)
                self._send(200, {"ok": True, "dispatched": n,
                                 "message": f"新资料《{title}》已入库，已向 {n} 位曾提问的员工下发新答案。现在再问该问题将能命中。"})
            else:
                self._send(400, {"error": "title/text required"})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass


def main():
    n = rag.load_or_build()
    print(f"企业内智能客服 Demo 已启动（已索引 {n} 个知识片段）→ http://localhost:8000")
    HTTPServer(("0.0.0.0", 8000), H).serve_forever()


if __name__ == "__main__":
    main()
