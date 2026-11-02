# ============================================================
# gamelang.py —— 扫「Python 有、但这个游戏语言**没有**」的表达式式语法
#
# 为什么需要它：实测踩过一次 —— `hay_farm.py` 里写了
#     print("...", "够" if comp >= 32236 else "不够")
# 这一行让脚本**在校验阶段就报 Error、一行输出都没有**，而：
#   * `python -m py_compile` 校验的是 **Python** 语法 ⇒ 通过；
#   * `audit_save0.py` 查的是重复声明/下标/未定义名字 ⇒ 也通过。
# ⇒ 需要一个专门盯"这门语言不支持哪些 Python 写法"的检查。
#
# 依据：`docs/game/scripting/*.md`。文档里 `if` 只有**语句**形式（没有条件表达式），
# 也从未出现过 f-string / 推导式 / lambda。
#
# 用法：python gamelang.py [文件名...]（默认扫存档根目录下所有 .py，跳过 __builtins__.py）
# ============================================================
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAVE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

# (名字, 正则, 说明)
CHECKS = [
    # 本语言 if 只有**语句**形式（换行 + 缩进块）⇒ 同一行里同时出现 if 和 else 就是三元。
    # 旧正则写作 `\S\s+if\s+[^:=]+?\s+else\s+\S`，中间那段把 `=` 排除在外，
    # 于是**条件里带 >= / <= / == / != 的三元全部溜过**（2026-10-05 实测踩到）✗
    ("三元表达式", re.compile(r"\bif\b.*\belse\b"),
     "`A if C else B` —— 文档里 if 只有语句形式，**不支持条件表达式**"),
    ("f-string", re.compile(r"""(^|[^\w])f["']"""),
     "f\"...\" 格式化字符串"),
    ("列表/字典推导式", re.compile(r"\[[^\]\n]*\bfor\b[^\]\n]*\bin\b[^\]\n]*\]|\{[^}\n]*\bfor\b[^}\n]*\bin\b[^}\n]*\}"),
     "[x for x in ...] / {k: v for ...}"),
    ("lambda", re.compile(r"\blambda\b"), "匿名函数"),
    ("链式比较", re.compile(r"[\w\)\]]\s*[<>]=?\s*[\w\(\[\"']+\s*[<>]=?\s*[\w\(\[\"']"),
     "`a < b < c` —— 每个比较都拆成两条"),
    ("not (A and B) 混写", re.compile(r"\bnot\s*\("),
     "优先级无先例 ⇒ 一律拆成嵌套 if"),
    ("装饰器", re.compile(r"^\s*@\w+"), "@decorator"),
    ("try/except/finally", re.compile(r"\b(try|except|finally|raise)\b"), "异常语法"),
    ("class", re.compile(r"^\s*class\s+\w+"), "类定义"),
    ("with", re.compile(r"^\s*with\s+"), "with 语句"),
    ("yield", re.compile(r"\byield\b"), "生成器"),
    ("多目标链式赋值", re.compile(r"^\s*\w+\s*=\s*\w+\s*=\s*"), "`a = b = 0` 未验证"),
    ("切片", re.compile(r"\w\[[^\]\n]*:[^\]\n]*\]"), "list[1:3] —— 未验证"),
]


def code_of(line):
    # 去掉字符串字面量与注释，避免把文档/提示文字里的词当成代码
    s = re.sub(r'"[^"]*"', '""', line)
    s = re.sub(r"'[^']*'", "''", s)
    return s.split("#")[0]


def main():
    names = sys.argv[1:]
    if not names:
        names = [os.path.basename(p) for p in sorted(glob.glob(os.path.join(SAVE, "*.py")))]
    total = 0
    for name in names:
        if name == "__builtins__.py":
            continue
        path = name if os.path.isabs(name) else os.path.join(SAVE, name)
        if not os.path.exists(path):
            print("[skip]", name, "不存在")
            continue
        hits = 0
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f.read().split("\n"), 1):
                code = code_of(line)
                if not code.strip():
                    continue
                for label, rx, tip in CHECKS:
                    if rx.search(code):
                        hits += 1
                        total += 1
                        print(f"{name}:{n}  [{label}] {tip}")
                        print(f"    {line.strip()[:90]}")
        if hits == 0:
            print(f"== {name}: 干净")
    print("总计可疑点:", total)
    return 0


sys.exit(main())
