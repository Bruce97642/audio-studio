"""把白話中文剪輯指令解析成動作（給網頁精靈的第 3 步用）。"""

from __future__ import annotations

import re

# 時間範圍：2:10-2:30、130-150、1:02:03.5 到 1:05:00
_RANGE = re.compile(r"([\d:.]+)\s*(?:[-~]|到|至)\s*([\d:.]+)")
# 引號中的字句：『』「」“”"" ''
_QUOTED = re.compile(r"[『「“\"'‘]([^』」”\"'’]+)[』」”\"'’]")

_REMOVE_WORDS = ("剪掉", "刪掉", "刪除", "剪除", "去掉", "移除")
_KEEP_WORDS = ("只保留", "保留", "只留")
_FIND_WORDS = ("找", "搜尋", "尋找")

HELP_TEXT = """看不懂這個指令，你可以這樣說：
- 「剪掉 2:10-2:30」（也可以一次多段：剪掉 0:00-0:05 和 3:00-3:10）
- 「只保留 1:00-2:00」
- 「刪掉『下星期三』」← 會自動找到那句話的位置剪掉
- 「找『市集活動』」← 只告訴你時間點，不剪
- 「去空白」（去掉頭尾的安靜段）
- 「縮短停頓」（連中間的長停頓一起縮短）
- 「還原」（回到上一步）"""


def parse_command(text: str) -> tuple[str, object]:
    """回傳 (動作, 參數)。

    動作：remove / keep / remove_text / find_text / trim / gaps /
          undo / help
    """
    text = text.strip()
    if not text:
        return ("help", None)

    if re.search(r"還原|復原|回上一步|undo", text, re.IGNORECASE):
        return ("undo", None)
    if re.search(r"縮短?停頓|去停頓", text):
        return ("gaps", None)
    if re.search(r"空白|靜音|安靜", text) and not _RANGE.search(text):
        return ("trim", None)

    ranges = [f"{a}-{b}" for a, b in _RANGE.findall(text)]
    quoted = _QUOTED.findall(text)

    if any(w in text for w in _KEEP_WORDS) and ranges:
        return ("keep", ranges)
    if any(w in text for w in _REMOVE_WORDS):
        if ranges:
            return ("remove", ranges)
        if quoted:
            return ("remove_text", quoted[0])
        # 「刪掉 下星期三」沒加引號也試著理解
        m = re.search(r"(?:剪掉|刪掉|刪除|剪除|去掉|移除)\s*(.+)", text)
        if m and m.group(1).strip():
            return ("remove_text", m.group(1).strip())
    if any(w in text for w in _FIND_WORDS):
        if quoted:
            return ("find_text", quoted[0])
        m = re.search(r"(?:找|搜尋|尋找)\s*(.+)", text)
        if m and m.group(1).strip():
            return ("find_text", m.group(1).strip())

    return ("help", None)
