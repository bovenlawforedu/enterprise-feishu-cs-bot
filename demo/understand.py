"""Query Understanding 层：把员工模糊的提问，结合其岗位与对话上下文，
改写为更易命中的检索式。无 LLM key 时用基于岗位的规则扩展；有 key 时优先 LLM 改写。

设计目标（来自客户确认）：飞书里员工 @机器人 的提问往往很口语/模糊，
必须根据「发问者岗位」与「上下文」提炼关键信息，才能匹配到正确知识。
"""
import os
import re
import json

BASE = os.path.dirname(os.path.abspath(__file__))

# 演示用：员工身份 → 岗位映射（真实环境应调飞书通讯录接口动态获取）
_USER_MAP = {"by_name": {}, "by_dept": {}, "by_title": {}}
try:
    with open(os.path.join(BASE, "users.json"), encoding="utf-8") as _f:
        _USER_MAP = json.load(_f)
except Exception:
    pass
# 也支持环境变量一次性注入（JSON 字符串）
_env_roles = os.environ.get("USER_ROLES")
if _env_roles:
    try:
        _USER_MAP = json.loads(_env_roles)
    except Exception:
        pass


def resolve_role(user="", dept="", title=""):
    """根据飞书身份标签（姓名/部门/职位）自动推断岗位。"""
    u = (user or "").strip()
    d = (dept or "").strip()
    t = (title or "").strip()
    by_name = _USER_MAP.get("by_name", {})
    by_dept = _USER_MAP.get("by_dept", {})
    by_title = _USER_MAP.get("by_title", {})
    # 1) 精确姓名/open_id 匹配
    if u and u in by_name:
        return by_name[u]
    # 2) 部门匹配
    if d:
        for dept_key, role in by_dept.items():
            if dept_key in d or d in dept_key:
                return role
    # 3) 职位关键词匹配
    if t:
        for title_key, role in by_title.items():
            if title_key in t:
                return role
    return "其他"


# 各岗位关注的检索焦点词。命中模糊提问时，把这些词补进检索式做加权。
ROLE_PROFILE = {
    "销售": {
        "focus": ["价格", "报价", "折扣", "配置", "卖点", "方案", "适用场景", "客户"],
        "hint": "面向客户的商务信息（价格 / 配置 / 卖点 / 适用场景）",
    },
    "研发": {
        "focus": ["接口", "SDK", "API", "对接", "集成", "协议", "开发", "技术参数", "私有化"],
        "hint": "技术对接与开发信息（接口 / SDK / 协议 / 技术参数）",
    },
    "财务": {
        "focus": ["发票", "开票", "付款", "账期", "报销", "含税", "价格", "费用"],
        "hint": "商务财务信息（发票 / 付款 / 账期 / 含税价）",
    },
    "客服": {
        "focus": ["售后", "保修", "维修", "退换", "故障", "报修", "响应"],
        "hint": "售后与故障处理（保修 / 维修 / 退换 / 报修流程）",
    },
    "行政/采购": {
        "focus": ["采购", "下单", "交付", "物流", "流程", "部署"],
        "hint": "采购与交付流程（下单 / 部署 / 物流）",
    },
}

# 模糊表达 → 补权关键词（与岗位无关，纯语义澄清）
VAGUE_EXPANSIONS = [
    (r"出问题|坏了|不行|不能用|故障|异常", ["故障", "售后", "报修", "处理"]),
    (r"花多少钱|多少钱|贵不贵|预算|费用", ["价格", "报价", "费用", "含税"]),
    (r"怎么买|在哪买|下单|采购|要货", ["采购", "下单", "交付", "流程"]),
    (r"能接|能不能用|兼容|对接|集成|打通", ["接口", "SDK", "对接", "集成", "协议"]),
    (r"开票|报销|付款|发票|账期", ["发票", "付款", "账期", "含税"]),
    (r"保修|质保|保多久|售后", ["保修", "维修", "退换", "响应"]),
    (r"客户|甲方|对外|卖给", ["方案", "适用场景", "卖点", "配置"]),
]

_OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
_OPENAI_BASE = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
_OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def _rule_rewrite(question, role, context):
    """规则改写：岗位焦点 + 模糊澄清，拼接成检索式。"""
    focus = ROLE_PROFILE.get(role, {}).get("focus", [])
    extra = list(focus)
    for pat, words in VAGUE_EXPANSIONS:
        if re.search(pat, question):
            extra.extend(words)
    # 上下文：若本轮是追问（短问句）且上一轮有内容，带上上一轮关键词
    ctx_terms = []
    if context and len(question) <= 12:
        ctx_terms = [w for w in re.findall(r"[一-鿿]{2,}", context) if w not in ("这个", "那个", "怎么", "什么")][:6]
    # 去重保序
    seen, merged = set(), []
    for w in extra + ctx_terms:
        if w not in seen:
            seen.add(w); merged.append(w)
    rewritten = question + " " + " ".join(merged)
    return rewritten, merged


def _llm_rewrite(question, role, context):
    """有 LLM key 时，让模型把模糊提问改写为精准检索式（中文，≤40字）。"""
    try:
        import urllib.request
        role_hint = ROLE_PROFILE.get(role, {}).get("hint", "通用员工")
        ctx_block = f"\n历史上下文：{context}" if context else ""
        sys_p = ("你是企业知识库检索式改写器。把员工在飞书里对@机器人说的模糊/口语化提问，"
                 "结合其岗位和历史上下文，改写成一条精准、利于检索的中文查询（≤40字，只输出查询本身）。")
        user_p = f"岗位：{role}（关注：{role_hint}）\n当前提问：{question}{ctx_block}"
        body = {
            "model": _OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": user_p},
            ],
            "temperature": 0,
            "max_tokens": 80,
        }
        req = urllib.request.Request(
            _OPENAI_BASE.rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {_OPENAI_KEY}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        rewritten = data["choices"][0]["message"]["content"].strip().strip('"')
        if rewritten:
            return rewritten, []
    except Exception:
        pass
    return None, []


def analyze(question, role="其他", context="", user="", dept="", title=""):
    """对外接口。返回 dict：rewritten / role / role_hint / expansions / method。

    若调用方没传 role，则根据 user/dept/title（飞书身份标签）自动推断。
    """
    if not role or role == "其他":
        role = resolve_role(user, dept, title)
    role = role if role in ROLE_PROFILE else "其他"
    hint = ROLE_PROFILE.get(role, {}).get("hint", "通用员工，无特定焦点")
    rewritten, expansions = _rule_rewrite(question, role, context)
    method = "rule"
    if _OPENAI_KEY:
        llm_q, _ = _llm_rewrite(question, role, context)
        if llm_q:
            rewritten, method = llm_q, "llm"
    return {
        "rewritten": rewritten,
        "role": role,
        "role_hint": hint,
        "expansions": expansions,
        "method": method,
    }
