"""内容级护栏：即使 BM25 分数过了阈值，也要判断命中的资料是否真正回答了问题。

典型场景：员工问“该联系谁”，但知识库里只有价格/部署内容，没有任何联系方式/对接人信息。
此时必须拒答，避免给出看似相关、实则无关的堆砌答案。
"""
import re

# 询问“谁/联系谁/负责人”的提问模式
_WHO_PATTERNS = re.compile(r"联系谁|找谁|联系哪位|找哪位|对接人|负责人|归属谁|应该联系|联系哪个|找哪个|谁负责|对接谁|找哪位")
# 资料里必须出现「人/角色」才算真正回答了「联系谁」；单纯出现“邮箱/电话”不算
_PERSON_TERMS = re.compile(r"联系人|对接人|负责人|客户经理|销售|商务|BD|售前|售后|专属顾问|客户经理|业务代表")

# 询问“在哪/地点/位置”的提问模式
_WHERE_PATTERNS = re.compile(r"在哪|在哪里|地点|位置|地址|怎么去")
# 资料里出现以下词，才算真正包含地点信息
_PLACE_TERMS = re.compile(r"地址|地点|位置|楼层|会议室|酒店|大厦|园区|城市|区|路|号")


def verify_answerable(query, chunks):
    """返回 (is_answerable, reason)。

    is_answerable=False 时，reason 会透传给前端/用户，说明为何无法直接回答。
    """
    q = query or ""
    text = "\n".join(c.get("text", "") for c in chunks)

    if _WHO_PATTERNS.search(q):
        if not _PERSON_TERMS.search(text):
            return False, "知识库中暂无对接人或负责人信息，建议您先联系直属上级或公司商务负责人确认。"

    if _WHERE_PATTERNS.search(q):
        if not _PLACE_TERMS.search(text):
            return False, "知识库中暂无具体地点或地址信息，建议您向行政或相关组织部门确认。"

    return True, ""
