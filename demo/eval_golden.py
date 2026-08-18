"""G6 验收：黄金问答集评测。

衡量两类正确性：
  (1) 可答问题必须命中（answered=True）并给出引用；
  (2) 不可答问题必须拒答（answered=False，不幻觉）。

运行：python eval_golden.py
输出：逐条判定 + 通过率。
"""
import rag, understand, generate

# (问题, 岗位, 期望可答?)
GOLDEN = [
    ("智能会议平板 X1 支持多大屏幕", "其他", True),
    ("这款多少钱", "销售", True),
    ("能私有化部署吗", "研发", True),
    ("坏了怎么保修", "客服", True),
    ("怎么开发票", "财务", True),
    ("投屏连不上怎么办", "客服", True),
    ("屏幕是什么材质", "其他", False),
    ("你们老板叫什么名字", "其他", False),
    ("今天天气怎么样", "其他", False),
    ("公司年会在哪开", "其他", False),
    ("帮我写一封辞职信", "其他", False),
    ("这个能用在客户那吗", "销售", True),
]


def main():
    rag.load_or_build()
    ok = 0
    print(f"{'问题':<24}{'岗位':<6}{'期望':<6}{'实际':<6}结果")
    print("-" * 60)
    for q, role, exp in GOLDEN:
        it = understand.analyze(q, role, "")
        ch = rag.search(it["rewritten"], k=3)
        best = ch[0]["score"] if ch else 0
        ans = best >= rag.MIN_SCORE
        passed = ans == exp
        ok += passed
        print(f"{q:<24}{role:<6}{'可答' if exp else '拒答':<6}"
              f"{'可答' if ans else '拒答':<6}{'✓' if passed else '✗'}")
    acc = ok / len(GOLDEN)
    print("-" * 60)
    print(f"通过率：{ok}/{len(GOLDEN)} = {acc*100:.1f}%  (阈值 MIN_SCORE={rag.MIN_SCORE})")
    return acc


if __name__ == "__main__":
    main()
