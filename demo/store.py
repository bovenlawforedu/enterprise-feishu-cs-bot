"""提问日志与高频未答聚合（零依赖，JSON 持久化）。"""
import os, json, time
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "logs.json")

# 业务真实阈值：24h 内同问题 ≥5 或 单周累计 ≥10
WINDOW_H = 24
WEEK_H = 24 * 7
SAME_REAL = 5
WEEK_REAL = 10
# Demo 可视化阈值（降低以便演示观察）：同问题 ≥2 即标「高频」
DEMO_SAME = 2


def _load():
    if os.path.exists(LOG):
        with open(LOG, encoding="utf-8") as f:
            return json.load(f)
    return []


def _save(d):
    with open(LOG, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def log(question, user, answered, top_source):
    d = _load()
    d.append({"ts": time.time(), "user": user, "question": question,
              "answered": answered, "top": top_source})
    _save(d)


def aggregate():
    d = _load()
    now = time.time()
    groups = defaultdict(list)
    for r in d:
        if not r["answered"]:
            groups[r["question"].strip()].append(r)
    out = []
    for q, rs in groups.items():
        total = len(rs)
        last24h = sum(1 for r in rs if now - r["ts"] <= WINDOW_H * 3600)
        last7d = sum(1 for r in rs if now - r["ts"] <= WEEK_H * 3600)
        out.append({
            "question": q, "total": total, "count": total,
            "last24h": last24h, "last7d": last7d,
            "askers": sorted(set(r["user"] for r in rs)),
            "high_freq": total >= DEMO_SAME,
        })
    out.sort(key=lambda x: -x["total"])
    return out


def resolve(question, title):
    """模拟「新资料下发原提问者」：统计曾问该未答问题的人数。"""
    d = _load()
    n = sum(1 for r in d if (not r["answered"]) and question and question in r["question"])
    return n
