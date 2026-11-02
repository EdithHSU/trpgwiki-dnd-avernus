"""從團錄 CLAUDE.md 的「角色名單」與「常用專有名詞」表產生 jieba 自訂詞典。

只取第一欄的標準寫法（括號內的說明拿掉、以「／」分開的各自成詞），不收常見誤判。
用法：python tools/make_jieba_dict.py ../團錄/CLAUDE.md jieba_dict.txt
"""

import re
import sys
from pathlib import Path

SECTIONS = ("## 角色名單", "## 常用專有名詞")
FREQ = 50000  # 夠高，讓專有名詞優先於一般詞彙被切成一個詞
WORD_RE = re.compile(r"^[㐀-鿿・]{2,12}$")


def words_from(cell: str):
    cell = re.sub(r"（[^）]*）", "", cell)  # 去掉全形括號內的說明
    for w in cell.split("／"):
        w = w.strip()
        if WORD_RE.match(w):
            yield w
            if "・" in w:
                yield from (p for p in w.split("・") if len(p) >= 2)


def main(src: str, dst: str):
    words, active = [], False
    for line in Path(src).read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            active = line.startswith(SECTIONS)
            continue
        if not active or not line.startswith("|") or set(line) <= set("|- "):
            continue
        first = line.split("|")[1].strip()
        if first in ("角色", "標準寫法"):
            continue
        words.extend(words_from(first))
    extra = Path(__file__).with_name("jieba_extra.txt")
    if extra.exists():
        words.extend(l.strip() for l in extra.read_text(encoding="utf-8").splitlines()
                     if l.strip() and not l.startswith("#"))
    uniq = list(dict.fromkeys(words))
    Path(dst).write_text("".join(f"{w} {FREQ}\n" for w in uniq), encoding="utf-8", newline="\n")
    print(f"{len(uniq)} words -> {dst}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
