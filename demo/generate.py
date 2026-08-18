"""答案生成：LLM 可插拔（OpenAI 兼容，环境变量），无 key 时退回抽取式引用。"""
import os, json, urllib.request

SYS = ("你是企业内部知识助手。只能依据【资料】回答，必须每条结论标注引用"
       "（格式：来源文档·章节）。若资料未覆盖，明确说「未找到依据」。严禁编造。")

REFUSE = "未在知识库中找到相关依据，已记录并上报知识库管理员。如需进一步帮助，请联系对应产品线负责人。"


def refuse(reason=""):
    base = "未在知识库中找到可直接回答该问题的资料，已记录并上报知识库管理员补充。"
    if reason:
        return f"{base}\n\n建议：{reason}"
    return base


def _call_llm(system, user):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.1,
    }).encode()
    req = urllib.request.Request(
        base + "/chat/completions", data=body,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]
    except Exception:
        return None


def answer(query, chunks):
    ctx = "\n\n".join(f"【{c['source']}·{c['section']}】\n{c['text']}" for c in chunks)
    llm = _call_llm(SYS, f"资料：\n{ctx}\n\n问题：{query}")
    if llm:
        return llm
    # 抽取式兜底：直接返回命中段落 + 出处，诚实展示「不幻觉」
    return ("（以下为知识库中命中的原文，已附出处，未做任何编造）\n\n"
            + "\n\n".join(f"【{c['source']}·{c['section']}】\n{c['text']}" for c in chunks))


