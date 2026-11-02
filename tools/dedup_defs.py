# -*- coding: utf-8 -*-
# ============================================================
# dedup_defs.py —— 去掉**重复的顶层 def**（真机根因：patch 追加而不是替换 ✗）
#
# 真机证据（2026-10-08）：
#   stage_w8.py 里有 3 个 def assign()、2 个 def allocation() ✗
#   而 Python 取**最后一个**定义 ⇒ 运行的是**旧配版**（8 项表）✗
#   ⇒ 日志 `[s8] 配比 ['hay','hay','hay','wood','wood','wood','carrot','carrot']` ✓✓
#   `矩形里 胡萝卜 0 草 12 木 4` 正是 ['hay','hay','hay','wood'] 的形态 ✓
#
# 策略：同一名字出现多次时，**保留最后一个**（= 文件里最终生效的那个），
#   删掉它前面的同名定义块 —— 这样「运行什么」与「读到的最后一段」永远一致 ✓
# 用法：python tools/dedup_defs.py <文件...>   （不给参数就扫全部档位）
# ============================================================
import os
import re
import sys

SAVE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
FILES = ["full_run.py", "util.py", "budget.py", "jobs.py", "block_farm.py",
         "stage_w1.py", "stage_row.py", "stage_w3.py", "stage_w4.py", "stage_w6.py",
         "stage_w8.py", "stage_w12.py", "stage_w16.py", "stage_w22.py"]


def blocks(src):
    # 顶层 def 的 (name, start, end)
    out = []
    lines = src.split("\n")
    for i, ln in enumerate(lines):
        m = re.match(r"^def ([A-Za-z_][A-Za-z_0-9]*)\(", ln)
        if m:
            out.append([m.group(1), i, len(lines)])
    for k in range(len(out) - 1):
        out[k][2] = out[k + 1][1]
    return out, lines


def main(argv):
    files = argv if len(argv) > 0 else FILES
    total = 0
    for name in files:
        p = os.path.join(SAVE, name)
        if not os.path.exists(p):
            continue
        src = open(p, encoding="utf-8").read()
        bs, lines = blocks(src)
        seen = {}
        for k, b in enumerate(bs):
            seen.setdefault(b[0], []).append(k)
        dup = {n: ks for n, ks in seen.items() if len(ks) > 1}
        if not dup:
            print("  ok", name)
            continue
        drop = []
        for n, ks in dup.items():
            for k in ks[:-1]:                      # 保留最后一个 ✓
                drop.append(bs[k])
        drop.sort(key=lambda b: b[1], reverse=True)   # 从后往前删，避免位移
        for b in drop:
            del lines[b[1]:b[2]]
        open(p, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
        total = total + len(drop)
        print("  !!", name, "删掉", len(drop), "个重复定义：",
              ", ".join("%s@" % n for n, _ in [(b[0], b[1]) for b in drop]))
    print("总计删除重复定义:", total)
    return 0


sys.exit(main(sys.argv[1:]))
