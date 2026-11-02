"""反向連結 hook。

建站時掃描所有頁面原始碼中的標準 Markdown 連結（`[文字](路徑.md#錨點)`），
建立「目標頁 → 來源頁」的反向索引，並在每個被連結的頁面底部加上「出場與提及」區塊。

- 每個來源頁列一項：來源頁標題（可點擊）＋提到本頁的句子（最多 MAX_SENTENCES 句）。
- 句中的其他連結只保留文字；連到本頁的文字以粗體標示。
- 集數頁（episodes/）依 front matter 的 order（沒有就用 date）排序，排在其他頁面之前。
- front matter 設 `backlinks: false` 的頁面：不顯示反向連結，它連出去的連結也不計入
  （首頁、時間線、名詞表這類索引頁用，避免每頁都出現同樣的來源）。
- 區塊帶 data-search-exclude 屬性，不會被搜尋索引收錄。
"""

from __future__ import annotations

import html
import logging
import posixpath
import re
from collections import defaultdict
from urllib.parse import unquote, urlsplit

from mkdocs.utils.meta import get_data

log = logging.getLogger("mkdocs.hooks.backlinks")

SECTION_TITLE = "出場與提及"
MAX_SENTENCES = 3
EPISODE_DIR = "episodes/"

# [文字](目標 "可選標題")；排除圖片 ![...]；目標可用 <...> 包住
LINK_RE = re.compile(
    r'(?<!!)\[((?:[^\[\]]|\[[^\]]*\])*)\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+"[^"]*")?\s*\)'
)
FENCE_RE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$", re.M | re.S)
LIST_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+")
TERMINATORS = "。！？!?"
CLOSERS = "」』）)\"'"

_meta: dict[str, dict] = {}
_titles: dict[str, str] = {}
# 目標頁 → {來源頁: [句子 HTML, ...]}（dict 保留插入順序）
_index: dict[str, dict[str, list[str]]] = defaultdict(dict)


def _resolve(src: str, raw: str) -> str | None:
    """把連結目標解析成相對於 docs 的 .md 路徑；外部連結或非頁面回傳 None。"""
    raw = raw.strip("<>")
    parts = urlsplit(raw)
    if parts.scheme or parts.netloc or not parts.path:
        return None
    path = unquote(parts.path)
    if not path.endswith(".md"):
        return None
    if path.startswith("/"):
        return posixpath.normpath(path.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(src), path))


def _units(markdown: str):
    """把 Markdown 切成段落／清單項目，回傳每個單位的純文字（行已合併）。"""
    markdown = FENCE_RE.sub("", markdown)
    unit: list[str] = []
    for line in markdown.splitlines():
        s = line.strip()
        while s.startswith(">"):
            s = s[1:].strip()
        if not s or s.startswith(("#", "!!!", "???", "|", "<", "---")):
            if unit:
                yield "".join(unit)
                unit = []
            # 表格列也當成一個單位，讓表格裡的連結一樣能被收集
            if s.startswith("|"):
                yield s
            continue
        if LIST_RE.match(s) and unit:
            yield "".join(unit)
            unit = []
        unit.append(LIST_RE.sub("", s))
    if unit:
        yield "".join(unit)


def _sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    """回傳包含 text[start:end] 的那一句的範圍。"""
    s = start
    while s > 0 and text[s - 1] not in TERMINATORS:
        s -= 1
    e = end
    while e < len(text) and text[e] not in TERMINATORS:
        e += 1
    while e < len(text) and (text[e] in TERMINATORS or text[e] in CLOSERS):
        e += 1
    return s, e


def _plain(fragment: str) -> str:
    return html.escape(re.sub(r"\*\*|__|`|\{[^}]*\}", "", fragment))


def _render_sentence(src: str, sentence: str, target: str) -> str:
    """句中連結轉成純文字；連到 target 的文字加粗。"""
    out, pos = [], 0
    for m in LINK_RE.finditer(sentence):
        out.append(_plain(sentence[pos:m.start()]))
        text = html.escape(re.sub(r"\*\*|__|`", "", m.group(1)))
        out.append(f"<strong>{text}</strong>" if _resolve(src, m.group(2)) == target else text)
        pos = m.end()
    out.append(_plain(sentence[pos:]))
    rendered = re.sub(r"\s*\|\s*", "｜", "".join(out)).strip("｜ ")
    # 「經歷」清單常寫成「[集數](...)：內容」，開頭的目標頁名稱和來源標題重複，拿掉
    return re.sub(r"^<strong>[^<]*</strong>[：:]\s*", "", rendered)


def on_files(files, config):
    _meta.clear()
    _titles.clear()
    _index.clear()

    pages = {f.src_uri: f for f in files.documentation_pages()}
    for src, f in pages.items():
        markdown, meta = get_data(f.content_string)
        _meta[src] = meta
        h1 = re.search(r"^#\s+(.+?)\s*$", markdown, re.M)
        _titles[src] = str(meta.get("title") or (h1.group(1) if h1 else posixpath.splitext(posixpath.basename(src))[0]))
        if meta.get("backlinks") is False:
            continue
        for unit in _units(markdown):
            for m in LINK_RE.finditer(unit):
                target = _resolve(src, m.group(2))
                if target is None or target == src:
                    continue
                if target not in pages:
                    log.debug("略過不存在的連結目標：%s → %s", src, target)
                    continue
                s, e = _sentence_span(unit, m.start(), m.end())
                rendered = _render_sentence(src, unit[s:e], target)
                sentences = _index[target].setdefault(src, [])
                if rendered and rendered not in sentences:
                    sentences.append(rendered)
    return files


def _label(src: str) -> str:
    title = _titles.get(src, src)
    meta = _meta.get(src, {})
    date = meta.get("date") or meta.get("date_short")
    return f"{date}　{title}" if src.startswith(EPISODE_DIR) and date else title


def _sort_key(src: str):
    if src.startswith(EPISODE_DIR):
        # 劇情順序與錄音日期不同時，用 front matter 的 order 覆寫排序（例如 0524 的劇情在 0517 之前）
        meta = _meta.get(src, {})
        return (0, str(meta.get("order") or meta.get("date", "")), src)
    return (1, _titles.get(src, src), src)


def on_page_content(html_out, page, config, files):
    src = page.file.src_uri
    if _meta.get(src, {}).get("backlinks") is False or not _index.get(src):
        return html_out

    sources = sorted(_index[src], key=_sort_key)
    # 給 hooks/notion.py 的屬性列用
    page.meta["backlink_episodes"] = sum(s.startswith(EPISODE_DIR) for s in sources)

    items = []
    for source in sources:
        url = files.get_file_from_path(source).url_relative_to(page.file)
        sentences = _index[src][source]
        quotes = "".join(f"<li>{s}</li>" for s in sentences[:MAX_SENTENCES])
        more = len(sentences) - MAX_SENTENCES
        if more > 0:
            quotes += f'<li class="backlinks-more">另有 {more} 處提及</li>'
        items.append(
            f'<li><div class="backlinks-source"><a class="backlink-page" data-src="{html.escape(source)}" '
            f'href="{html.escape(url)}">{html.escape(_label(source))}</a></div>'
            f'<ul class="backlinks-quotes">{quotes}</ul></li>'
        )

    return (
        html_out
        + '\n<section class="backlinks" data-search-exclude>'
        + f'<h2 id="{SECTION_TITLE}">{SECTION_TITLE}<span class="backlinks-count">{len(sources)}</span></h2>'
        + f'<ul class="backlinks-list">{"".join(items)}</ul></section>'
    )
