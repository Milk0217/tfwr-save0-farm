# ============================================================
# tidy.py —— 脚本卫生：删掉遗留的分区标记、把 3 个以上连续空行压成 2 个、
#            去掉行尾空白、保证文件以单个 \n 结尾。
#
# 为什么单独做成一步：大批量删代码（deadcode.py + patch_lines.py）之后会留下
# 「孤立的区块标题注释 + 一串空行」，读起来像是还有东西没删干净。
# 这些都不影响语法，所以放在**验证通过之后**单独跑，不与逻辑改动混在一起。
#
# 用法：python tidy.py main.py [--drop '# <<<PUMPKIN_SMART_END>>>' ...]
# 纪律：显式 utf-8 + newline="\n"（绝不用 PowerShell 往返改脚本）。
# ============================================================
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAVE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))


def main():
    args = sys.argv[1:]
    if not args:
        print("usage: python tidy.py file.py [--drop 'marker line' ...]")
        return 2
    fname = args[0]
    drops = []
    i = 1
    while i < len(args):
        if args[i] == "--drop":
            drops.append(args[i + 1])
            i = i + 2
        else:
            i = i + 1
    path = fname if os.path.isabs(fname) else os.path.join(SAVE, fname)
    with open(path, encoding="utf-8", newline="") as f:
        raw = f.read()
    if "\r" in raw:
        print("ABORT: 源文件里出现 CR（本项目脚本一律 LF）")
        return 1
    lines = raw.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    before = len(lines)

    kept = []
    for ln in lines:
        if ln.strip() in drops:
            continue
        kept.append(ln.rstrip())

    out = []
    blanks = 0
    for ln in kept:
        if ln == "":
            blanks = blanks + 1
            if blanks > 2:
                continue
        else:
            blanks = 0
        out.append(ln)
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    print(f"OK: {os.path.basename(path)} {before} -> {len(out)} 行（dropped {len(drops)} 个标记）")
    return 0


sys.exit(main())
