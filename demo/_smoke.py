import rag, store, generate

n = rag.build()
print("[G2] 语料分块数:", n)
print("[G2] 文档清单:", [d["title"] for d in rag.list_docs()])

cases = [
    "X1 的保修期是多久？",
    "批量采购怎么开专票？",
    "你们公司叫什么名字？",   # 知识库无覆盖 → 应拒答
]
for q in cases:
    c = rag.search(q, 3)
    best = c[0]["score"] if c else 0
    print(f"\n[ASK] {q}")
    print("  best_score =", best, "| answered =", best >= rag.MIN_SCORE)
    if best > 0:
        print("  top:", c[0]["source"], "·", c[0]["section"])
    else:
        print("  ->", generate.refuse())

# 模拟「未答→写新资料→再问命中」闭环
print("\n[G5] 模拟闭环：管理员写入新资料")
rag.add_doc("公司介绍", "公司名称为「演示科技」，成立于 2018 年，专注于企业协作终端。")
c = rag.search("你们公司叫什么名字？", 3)
best = c[0]["score"] if c else 0
print("  写入后 best_score =", best, "| answered =", best > 0,
      "| hit:", c[0]["source"] if best > 0 else None)
print("\nALL OK" if best > 0 else "\nLOOP FAILED")
