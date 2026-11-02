# -*- coding: utf-8 -*-
# ============================================================
# contract_check.py —— 第 5 类判据：**档位接口契约**
#
# 真机报错实录（2026-10-08｜整轮中止）：
#   `Error: stage_w1.set_active 不存在。  In: main`
#   ⇒ full_run 会对**每个档位**调用 cur.set_active(...) ✓，
#     而我以为"只有带副机的档位才需要" ✗ ⇒ 跨档位接口不一致 ⇒ 崩 ✗✗
#
# 判据：full_run.py 里所有 `cur.NAME(` / `st.NAME(` 调用的 NAME，
#      **每个档位文件都必须有 `def NAME(`** ✓（统一接口 ⇒ 可机械验证 ✓）
# 自测：故意造一个缺函数的档位源，必须被报出来 ✓
# ============================================================
import os, re, sys

SAVE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
STAGES = ["stage_w1.py", "stage_row.py", "stage_w3.py", "stage_w4.py", "stage_w6.py",
          "stage_w8.py", "stage_w12.py", "stage_w16.py", "stage_w22.py"]


def required():
    src = open(os.path.join(SAVE, "full_run.py"), encoding="utf-8").read()
    names = set()
    for m in re.finditer(r"\b(?:cur|st)\.([A-Za-z_][A-Za-z_0-9]*)\s*\(", src):
        names.add(m.group(1))
    return sorted(names)


def check(src, need):
    have = set(re.findall(r"^def ([A-Za-z_][A-Za-z_0-9]*)\(", src, re.M))
    return [n for n in need if n not in have]


def main():
    need = required()
    print("full_run 要求的档位接口:", need)
    bad = 0
    for st in STAGES:
        p = os.path.join(SAVE, st)
        if not os.path.exists(p):
            continue
        miss = check(open(p, encoding="utf-8").read(), need)
        if miss:
            print("  !!", st, "缺少:", miss)
            bad = bad + len(miss)
        else:
            print("  ok", st)
    # 自测：缺函数必须被报出来 ✓
    demo = "def enter():\n\treturn 1\n"
    hit = check(demo, ["enter", "set_active"])
    print("自测（档位缺接口）：", "抓到 ✓" if len(hit) == 1 else "没抓到 ✗（工具失效）")
    print("总计缺失:", bad)
    return 0 if (bad == 0 and len(hit) == 1) else 1


sys.exit(main())
