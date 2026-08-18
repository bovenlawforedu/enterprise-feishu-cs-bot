# -*- coding: utf-8 -*-
"""用真实 pipeline 输出生成静态展示页 docs/index.html（供 GitHub Pages）。
零后端依赖：架构图 SVG 内嵌 + 真实对话示例预渲染。"""
import os, re, html, json
import rag, understand, guard, generate

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
DOCS = os.path.join(ROOT, "docs")
os.makedirs(DOCS, exist_ok=True)

rag.load_or_build()

# 真实对话场景（与演示脚本一致）
SCENARIOS = [
    ("张三", "这款多少钱 有折扣吗", "销售"),
    ("李四", "坏了怎么保修", "客服"),
    ("王五", "能不能接我们内部系统", "研发"),
    ("赵六", "怎么开发票 走什么流程", "财务"),
    ("张三", "客户想批量采购 要来考察工厂 应该联系谁", "销售"),
    ("钱七", "你们老板叫什么名字", "其他"),
    ("孙八", "出问题了怎么办", "客服"),
]


def run_one(user, q, role_hint):
    role = understand.resolve_role(user) or role_hint
    it = understand.analyze(q, role, "")
    chunks = rag.search(it["rewritten"], k=3)
    best = chunks[0]["score"] if chunks else 0
    ok, reason = guard.verify_answerable(q, chunks)
    answered = (best >= rag.MIN_SCORE) and ok
    ans = generate.refuse() if not answered else generate.answer(q, chunks)
    cites = [{"source": c["source"], "section": c["section"]} for c in chunks[:2]] if answered else []
    return {
        "user": user, "role": role, "q": q,
        "rewritten": it["rewritten"], "expansions": it["expansions"],
        "best": round(best, 2), "answered": answered, "reason": reason,
        "answer": ans, "citations": cites,
    }


def esc(s):
    return html.escape(str(s))


def chat_card(d):
    role_badge = f'<span class="badge">{esc(d["role"])}</span>'
    if d["answered"]:
        ans_html = esc(d["answer"])
        cites_html = "".join(
            f'<span class="cite">📎 {esc(c["source"])} · {esc(c["section"])}</span>'
            for c in d["citations"]
        )
        bot = f'<div class="bubble bot"><div class="ans">{ans_html}</div><div class="cites">{cites_html}</div></div>'
    else:
        reason = (f'<div class="reason">⚠️ {esc(d["reason"])}</div>') if d["reason"] else ""
        bot = (f'<div class="bubble bot refuse">'
               f'<div class="ans">{esc(d["answer"])}</div>{reason}'
               f'<div class="up">🔔 已自动记录并上报知识库管理员</div></div>')
    return f'''
    <div class="chat">
      <div class="row me"><div class="bubble me">{esc(d["q"])}{role_badge}</div></div>
      {bot}
      <div class="meta">自动识别岗位：<b>{esc(d["role"])}</b> ｜ 检索改写：<code>{esc(d["rewritten"])}</code> ｜ 命中分 {d["best"]}</div>
    </div>'''


cards = "\n".join(chat_card(run_one(*s)) for s in SCENARIOS)

# 提取架构图 SVG
with open(os.path.join(BASE, "architecture.html"), encoding="utf-8") as f:
    arch = f.read()
m = re.search(r"<svg.*?</svg>", arch, re.S)
svg = m.group(0) if m else ""

PAGE = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>企业内飞书智能客服 · 展示页</title>
<style>
  *{{box-sizing:border-box;}}
  body{{margin:0;background:#f5f7fa;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:#263238;line-height:1.6;}}
  .wrap{{max-width:920px;margin:0 auto;padding:28px 16px 56px;}}
  h1{{font-size:24px;color:#1a237e;margin:0 0 6px;}}
  .sub{{font-size:13px;color:#607d8b;margin:0 0 18px;}}
  .card{{background:#fff;border:1px solid #e3e8ee;border-radius:14px;padding:14px;box-shadow:0 2px 10px rgba(38,50,56,.06);margin:16px 0;}}
  .arch{{text-align:center;}}
  .arch svg{{width:100%;height:auto;}}
  h2{{font-size:17px;color:#0d47a1;margin:26px 0 8px;border-left:4px solid #1976d2;padding-left:10px;}}
  .chat{{background:#fff;border:1px solid #e3e8ee;border-radius:12px;padding:14px;margin:12px 0;}}
  .row{{display:flex;}}
  .row.me{{justify-content:flex-end;}}
  .bubble{{max-width:78%;padding:10px 13px;border-radius:12px;font-size:14px;white-space:pre-wrap;word-break:break-word;}}
  .bubble.me{{background:#dcedc8;border-bottom-right-radius:4px;}}
  .bubble.bot{{background:#e3f2fd;border-bottom-left-radius:4px;margin-top:8px;}}
  .bubble.bot.refuse{{background:#fff3e0;border:1px solid #ffcc80;}}
  .badge{{display:inline-block;margin-left:8px;font-size:11px;background:#1b5e20;color:#fff;border-radius:10px;padding:1px 8px;vertical-align:middle;}}
  .ans{{font-size:13.5px;}}
  .cites{{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;}}
  .cite{{font-size:11.5px;background:#e8f5e9;color:#1b5e20;border-radius:8px;padding:2px 8px;}}
  .reason{{margin-top:6px;font-size:12.5px;color:#b71c1c;}}
  .up{{margin-top:6px;font-size:12px;color:#8e24aa;}}
  .meta{{margin-top:8px;font-size:11.5px;color:#78909c;}}
  .meta code{{background:#eceff1;padding:1px 5px;border-radius:5px;font-size:11px;}}
  .run{{background:#0d47a1;color:#fff;border-radius:12px;padding:16px;font-size:13.5px;}}
  .run code{{background:rgba(255,255,255,.18);padding:2px 7px;border-radius:6px;}}
  .links a{{color:#1565c0;}}
  .foot{{font-size:12px;color:#90a4ae;margin-top:24px;text-align:center;}}
</style>
</head>
<body>
<div class="wrap">
  <h1>企业内飞书智能客服机器人 · 展示页</h1>
  <p class="sub">基于公司私有资料（产品手册/售后政策/FAQ）的 RAG 问答 · 不幻觉 · 带引用 · 高频未答闭环下发</p>

  <div class="card arch">{svg}</div>

  <h2>① 自动识别提问者身份（无需手动选岗）</h2>
  <p class="sub">飞书通讯录提供岗位标签，机器人收到消息即从 <code>open_id</code> 解析部门/职位映射到岗位，再决定检索焦点。下方示例均由系统<b>自动识别</b>。</p>

  <h2>② 真实对话示例（由本仓库代码实时生成，非编造）</h2>
  {cards}

  <h2>③ 如何运行可交互完整版</h2>
  <div class="run">
    本页为静态展示。完整可交互机器人（飞书 @机器人 行为模拟器，含知识补全下发闭环）需本地运行：<br><br>
    <code>git clone &lt;本仓库地址&gt;</code><br>
    <code>cd enterprise-feishu-cs-bot/demo</code><br>
    <code>python app.py</code> &nbsp;→&nbsp; 浏览器打开 <code>http://localhost:8000</code><br><br>
    无需安装任何第三方库（已预构建索引 <code>demo/data/index.json</code>，零依赖可跑）。
  </div>

  <h2>④ 关键能力一览</h2>
  <p class="sub">
    • 多格式 ingestion：Word(.docx)/PDF(.pdf)/网页(.html) 统一解析分块<br>
    • 中文 bigram BM25 检索，抗单字误命中<br>
    • 双重护栏：阈值拒答（MIN_SCORE）+ 内容护栏（无信源/无联系人 → 拒答并上报）<br>
    • 强制引用：每条回答带 source / section<br>
    • 高频未答闭环：未答看板 → 管理员补资料 → 定向下发当初提问员工<br>
    • 黄金集评测：不幻觉准确率 <b>12/12 = 100%</b><br>
    • 真实飞书接入代码见 <code>demo/feishu_bot.py</code>（技术附件）
  </p>

  <p class="foot">企业内飞书智能客服 · 面试作品　|　完整源码与运行说明见仓库 README</p>
</div>
</body>
</html>'''

with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as f:
    f.write(PAGE)

print("showcase written:", os.path.join(DOCS, "index.html"), os.path.getsize(os.path.join(DOCS, "index.html")), "bytes")
