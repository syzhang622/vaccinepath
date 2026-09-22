"""官方指引检索（RAG 的 R）：从 docs/sources/ 的原文摘录里取出可直接引用的原句。

确定性关键词检索，不经过 LLM、不联网。每次检索都会在审计日志里留下 retrieved: <文件名>。
语料是人工从官方页面抄录的原句（见各文件头部的 URL 与抓取日期），agent 只能引用，不能改写成医学结论。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

SOURCES_DIR = Path(__file__).parent.parent / "docs" / "sources"

# 每条语料的检索关键词（中英并列：agent 的 query 可能是任一种）
# 语料只覆盖"接种后反应 / 儿童发热"。排程、补种、记录核实不在这两份来源里 → 检索不到就不引用（原则 §0）
OUT_OF_SCOPE = ("catch_up", "schedule")

KEYWORDS: dict[str, list[str]] = {
    "fever": ["fever", "发热", "发烧", "体温", "temperature"],
    "emergency": ["emergency", "急诊", "urgent", "紧急", "立即"],
    "doctor": ["doctor", "医生", "就医", "consult", "看医生"],
    "reaction": ["reaction", "反应", "副作用", "接种后", "post vaccination", "post-vaccination"],
    "crying": ["cry", "哭", "哭闹", "settle", "安抚"],
    "breathing": ["breathing", "呼吸"],
    "seizure": ["seizure", "fit", "抽搐", "惊厥", "convulsion"],
    "lethargy": ["lethargic", "awaken", "嗜睡", "叫不醒", "精神"],
    "feeding": ["feed", "urine", "drink", "喝", "尿", "进食"],
    "skin": ["skin", "pale", "grey", "bruising", "肤色", "瘀"],
    "activity": ["active", "活跃", "精神"],
    "medication": ["medication", "退烧药", "antipyretic", "药"],
    "duration": ["persistent", "持续", "2 days", "两天", "duration"],
    "catch_up": ["catch-up", "catch up", "补种", "overdue", "逾期", "missed", "漏"],
    "schedule": ["schedule", "日程", "排程", "ncis", "推荐月龄", "dose", "剂次"],
}


@dataclass(frozen=True)
class Excerpt:
    source_file: str
    source_title: str
    source_url: str
    section: str
    quote: str

    def cite(self) -> str:
        return f"「{self.quote}」（{self.source_title} — {self.section}）"


def _topics(text: str) -> set[str]:
    low = text.lower()
    return {t for t, kws in KEYWORDS.items() if any(k in low for k in kws)}


@lru_cache(maxsize=1)
def corpus() -> list[Excerpt]:
    """把 docs/sources/*.md 解析成一条条可引用的原句（只取 markdown 引用块里的句子）。"""
    out: list[Excerpt] = []
    for path in sorted(SOURCES_DIR.glob("*.md")):
        lines = path.read_text().splitlines()
        title = lines[0].lstrip("# ").split("（")[0].strip()
        url = next((l.split("URL: ", 1)[1].strip() for l in lines if "URL: " in l), "")
        section = ""
        for line in lines:
            if line.startswith("## "):
                section = line[3:].strip()
            elif line.startswith(">"):
                q = re.sub(r"^>\s*-?\s*", "", line).strip()
                if q:
                    out.append(Excerpt(path.name, title, url, section, q))
    return out


def search(query: str, limit: int = 3) -> list[Excerpt]:
    """按关键词重合度排序返回原句。query 可以是中文症状词、规则名或自由描述。

    只问排程/补种/记录核实（本语料未覆盖）时返回空列表，让调用方明确"无可引用的官方原句"。
    """
    wanted = _topics(query)
    if wanted and wanted <= set(OUT_OF_SCOPE):
        return []
    wanted -= set(OUT_OF_SCOPE)
    scored: list[tuple[int, int, Excerpt]] = []
    for i, e in enumerate(corpus()):
        score = len(wanted & _topics(f"{e.section} {e.quote}"))
        if any(w.lower() in e.quote.lower() for w in re.findall(r"[A-Za-z]{4,}", query)):
            score += 1
        if score:
            scored.append((-score, i, e))
    return [e for _, _, e in sorted(scored)[:limit]]


def source_files(excerpts: list[Excerpt]) -> str:
    return ", ".join(dict.fromkeys(e.source_file for e in excerpts)) or "（无匹配）"
