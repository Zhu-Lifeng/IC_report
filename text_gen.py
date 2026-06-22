"""
text_gen.py — 条目文字生成接口（预留给「根据图片生成文字」的 AI 能力）

目前是占位实现：自动模式下返回占位文字，等将来接入图→文模型时，
只需替换 generate_item_text() 的实现即可，调用方（app.py）无需改动。

约定：
  generate_item_text(image_paths, item, kind) -> {"condition": str, "comments": str}
    image_paths : list[str]   该条目的本地图片绝对路径
    item        : dict        物业条目 {id, name, type, description}
    kind        : str         "check-in" | "check-out"
"""
from typing import List, Dict

# 占位文字：将来 AI 接入后会被真实生成的文字替换
PLACEHOLDER_CONDITION = "待 AI 生成"
PLACEHOLDER_COMMENTS = ""


def generate_item_text(image_paths: List[str], item: Dict, kind: str = "check-in") -> Dict[str, str]:
    """
    根据条目图片生成「状况 / 备注」文字。

    ⚠️ 当前为占位实现，未真正分析图片。接入图→文模型时在此处替换：
        例如调用视觉模型，传入 image_paths 与 item 上下文，返回结构化文字。
    """
    # === 将来在这里接入真实的图片理解模型 ===
    # e.g. result = vision_model.describe(image_paths, context=item)
    #      return {"condition": result.condition, "comments": result.comments}
    return {
        "condition": PLACEHOLDER_CONDITION,
        "comments": PLACEHOLDER_COMMENTS,
    }


# 标记：自动模式当前是否为占位（前端/接口可据此提示用户）
IS_PLACEHOLDER = True
