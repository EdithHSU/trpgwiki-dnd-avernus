"""仿 Notion 版面的 hook。

- 每頁一個 emoji 圖示：front matter 的 `emoji`，沒有就依資料夾給預設值。
  圖示會出現在頁首（標題上方）、左側導覽、反向連結清單，以及瀏覽器分頁的 favicon。
- 標題下方的「屬性」列（像 Notion 資料庫頁面）：集數頁顯示日期、章節；
  其他頁顯示類型。出場集數由 backlinks hook 寫進 page.meta["backlink_episodes"]。
  沒有確切日期的集數用 front matter 的 `date_label` 顯示說明；`position` 顯示劇情位置
  （例如「位置未定」）。不要用 `status`，那是 Material 的導覽狀態欄位。
  玩家角色頁另有 `full_name`、`role`、`race`、`alignment`（目前陣營）。
- front matter 設 `cover: true` 的頁面在頂端加一張封面（樣式見 extra.css）。

必須排在 hooks/backlinks.py 之後載入。
"""

from __future__ import annotations

import html
import posixpath
import re
from urllib.parse import quote, unquote, urljoin

from mkdocs.utils.meta import get_data

DEFAULT_EMOJI = {
    "episodes/": "📜",
    "characters/": "🗡️",
    "npcs/": "👤",
    "places/": "🏰",
    "items/": "💎",
}
TYPE_LABEL = {
    "episodes/": "集數",
    "characters/": "玩家角色",
    "npcs/": "NPC",
    "places/": "地點",
    "items/": "物品",
}
CHAPTERS = "一二三四五六七八九十"

_emoji: dict[str, str] = {}       # src_uri → emoji
_url_to_src: dict[str, str] = {}  # 未編碼的頁面 URL → src_uri


def _folder(src: str) -> str:
    return src.split("/", 1)[0] + "/" if "/" in src else ""


def on_files(files, config):
    _emoji.clear()
    _url_to_src.clear()
    for f in files.documentation_pages():
        _, meta = get_data(f.content_string)
        _emoji[f.src_uri] = str(meta.get("emoji") or DEFAULT_EMOJI.get(_folder(f.src_uri), "📄"))
        _url_to_src[unquote(f.url).removeprefix("./")] = f.src_uri  # 首頁的 url 是 "./"
    return files


def _icon(src: str, cls: str) -> str:
    return f'<span class="{cls}" aria-hidden="true">{_emoji.get(src, "📄")}</span>'


def _properties(page) -> str:
    src, meta = page.file.src_uri, page.meta
    rows = []
    folder = _folder(src)
    if folder in TYPE_LABEL:
        rows.append(("🏷️", "類型", f'<span class="notion-tag">{TYPE_LABEL[folder]}</span>'))
    # 玩家角色頁：全名、職業、種族、目前陣營
    for key, icon, label in (("full_name", "🪪", "全名"), ("role", "⚔️", "職業"), ("race", "🧬", "種族")):
        if meta.get(key):
            rows.append((icon, label, html.escape(str(meta[key]))))
    if meta.get("alignment"):
        align = str(meta["alignment"])
        tone = "evil" if "邪惡" in align else "good" if "善良" in align else "neutral"
        rows.append(("⚖️", "目前陣營", f'<span class="notion-tag notion-tag--{tone}">{html.escape(align)}</span>'))
    # 沒有確切日期的集數用 date_label 說明（例如「2025-12（確切日期不詳）」）
    if meta.get("date") or meta.get("date_label"):
        rows.append(("📅", "日期", html.escape(str(meta.get("date") or meta["date_label"]))))
    if meta.get("position"):
        rows.append(("📍", "劇情位置", f'<span class="notion-tag notion-tag--pending">{html.escape(str(meta["position"]))}</span>'))
    chapter = meta.get("chapter")
    if isinstance(chapter, int) and 1 <= chapter <= len(CHAPTERS):
        rows.append(("📖", "章節", f'<span class="notion-tag notion-tag--ch{chapter}">第{CHAPTERS[chapter - 1]}章</span>'))
    episodes = meta.get("backlink_episodes")
    if episodes:
        rows.append(("🔗", "出場集數", f'<a href="#出場與提及">{episodes} 集</a>'))
    if not rows:
        return ""
    body = "".join(
        f'<div class="notion-prop"><div class="notion-prop__key"><span>{i}</span>{k}</div>'
        f'<div class="notion-prop__value">{v}</div></div>'
        for i, k, v in rows
    )
    return f'<div class="notion-props">{body}</div>'


def _pager(page) -> str:
    """頁尾的上一頁／下一頁卡片，放在內文欄裡，跟內文對齊（取代 Material 的頁尾）。"""
    cards = []
    for other, cls, label in ((page.previous_page, "prev", "← 上一頁"), (page.next_page, "next", "下一頁 →")):
        if other is None:
            cards.append(f'<span class="notion-pager__spacer"></span>')
            continue
        url = html.escape(other.file.url_relative_to(page.file))
        cards.append(
            f'<a class="notion-pager__link notion-pager__link--{cls}" href="{url}">'
            f'<span class="notion-pager__dir">{label}</span>'
            f'<span class="notion-pager__title">{_icon(other.file.src_uri, "notion-inline-icon")}'
            f'<span class="notion-pager__text">{html.escape(other.title or "")}</span></span></a>'
        )
    return f'<nav class="notion-pager" aria-label="上一頁與下一頁" data-search-exclude>{"".join(cards)}</nav>'


def on_page_content(html_out, page, config, files):
    src = page.file.src_uri
    html_out += _pager(page)
    head = ""
    if page.meta.get("cover"):
        head += '<div class="notion-cover" aria-hidden="true"></div>'
    head += _icon(src, "notion-page-icon")
    # 圖示放在 h1 前、屬性列放在 h1 後
    m = re.search(r"<h1[^>]*>.*?</h1>", html_out, re.S)
    if not m:
        return head + html_out
    # 反向連結清單裡的來源頁加上圖示
    rest = re.sub(
        r'<a class="backlink-page" data-src="([^"]+)"',
        lambda b: f'{_icon(html.unescape(b.group(1)), "notion-inline-icon")}<a class="backlink-page"',
        html_out[m.end():],
    )
    return html_out[:m.start()] + head + m.group(0) + _properties(page) + rest


def _favicon(emoji: str) -> str:
    svg = f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>{emoji}</text></svg>"
    return "data:image/svg+xml," + quote(svg)


def on_post_page(output, page, config):
    base = "http://site/" + unquote(page.url)

    def nav_icon(m):
        target = unquote(urljoin(base, m.group(2)).split("#")[0].removeprefix("http://site/"))
        src = _url_to_src.get(target)
        return m.group(0) + (_icon(src, "notion-nav-icon") if src else "")

    # 左側導覽的頁面連結（不含頁內目錄 #錨點）
    output = re.sub(r'(<a href="([^"#]*)" class="md-nav__link[^"]*">)', nav_icon, output)
    # 手機版目前頁面的 label
    output = output.replace(
        '<label class="md-nav__link md-nav__link--active" for="__toc">',
        '<label class="md-nav__link md-nav__link--active" for="__toc">'
        + _icon(page.file.src_uri, "notion-nav-icon"),
    )
    # 頁首右上角（搜尋前）放待確認名詞表單的入口；表單是 docs/confirm/index.html 靜態頁
    confirm = "../" * page.url.count("/") + "confirm/"
    output = output.replace(
        '<label class="md-header__button md-icon" for="__search">',
        f'<a class="md-header__button md-header__confirm" href="{confirm}" title="待確認名詞">'
        '<span aria-hidden="true">📝</span><span class="md-header__confirm-text">待確認名詞</span></a>'
        '<label class="md-header__button md-icon" for="__search">',
        1,
    )
    # 每頁用自己的 emoji 當 favicon
    output = re.sub(
        r'<link rel="icon" href="[^"]*">',
        f'<link rel="icon" href="{_favicon(_emoji.get(page.file.src_uri, "📄"))}">',
        output,
    )
    return output
