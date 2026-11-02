# -*- coding: utf-8 -*-
# ============================================================
# api_check.py —— 上线前检查：游戏代码里用到的「集合方法」是否真被内置支持
#
# 为什么需要它（2026-10-07 真机事故）：
#   `Error: get 从未被定义。在使用变量之前必须先给它赋值。  In: main <- run <- busy_ok <- handed`
#   我在 handed() 里写了 `H_BIT.get(name, 0)` —— 而游戏内置里**只有**
#   append / insert / pop / remove / len / range（见 __builtins__.py L579~L677），
#   **字典没有 get** ✗。而这类错误是**整轮中止**（不是返回 False）⇒ 一次都不能赌 ✓
#
# 白名单来源：项目的 __builtins__.py（游戏自带的 API 参考）
#   * 所有 `def NAME(` 里定义的函数名 ✓
#   * 它 docstring 里出现的 `x.NAME(` 形式（= 官方示例里的方法调用）✓
# 用法：python tools/api_check.py <游戏代码文件...>
# ============================================================
import os
import re
import sys

SAVE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
BUILTINS = os.environ.get("TFWR_BUILTINS", os.path.join(SAVE, "__builtins__.py"))
if not os.path.exists(BUILTINS):
    print("api_check: 缺少 __builtins__.py（游戏/社区维护的类型存根，本仓库因版权原因未收录）。")
    print("           请用环境变量 TFWR_BUILTINS=<path/to/__builtins__.py> 指定后再运行。")
    sys.exit(2)

# 我们自己的档位/任务文件（旧单体那一堆 .py 不查：它们不再上真机）
GAME_FILES = ["full_run.py", "util.py", "budget.py", "jobs.py", "block_farm.py",
              "stage_w1.py", "stage_row.py", "stage_w3.py", "stage_w4.py", "stage_w6.py",
              "stage_w8.py", "stage_w12.py", "stage_w16.py", "stage_w22.py"]


def whitelist():
    src = open(BUILTINS, encoding="utf-8").read()
    names = set()
    for m in re.finditer(r"^def ([A-Za-z_][A-Za-z_0-9]*)\(", src, re.M):
        names.add(m.group(1))
    for m in re.finditer(r"\.([A-Za-z_][A-Za-z_0-9]*)\(", src):
        names.add(m.group(1))
    names.add("append")     # 官方示例里的方法式调用（例：my_list.append(4)）
    return names


def count_args(src, open_paren):
    # 从 '(' 开始数顶层逗号（跳过嵌套括号与字符串）
    depth = 0
    n = 0
    i = open_paren
    seen = 0
    while i < len(src):
        c = src[i]
        if c == "(" or c == "[" or c == "{":
            depth = depth + 1
        elif c == ")" or c == "]" or c == "}":
            depth = depth - 1
            if depth == 0:
                return 0 if seen == 0 else n + 1, i
        elif c == "," and depth == 1:
            n = n + 1
        elif depth == 1 and c not in " \t\n":
            seen = 1
        i = i + 1
    return -1, i


def arity_check(name, src):
    # 本文件里 def 的形参数 vs 调用处实参数（只查**本文件内**的函数，够用了 ✓）
    defs = {}
    for m in re.finditer(r"^def ([A-Za-z_][A-Za-z_0-9]*)\(", src, re.M):
        args, _ = count_args(src, m.end() - 1)
        defs[m.group(1)] = args
    bad = []
    for fn, want in defs.items():
        for m in re.finditer(r"(?<![.\w])" + fn + r"\(", src):
            line_start = src.rfind("\n", 0, m.start()) + 1
            line = src[line_start:src.find("\n", m.start())]
            if line.strip().startswith("def "):
                continue
            # 切掉**行尾注释**（否则注释里提到 need_soon() 也会被当成调用 ✗ 实测误报过）
            if "#" in line:
                line = line.split("#")[0]
                if line.find(fn) < 0:
                    continue
            got, _ = count_args(src, m.end() - 1)
            if got >= 0 and got != want:
                bad.append((src.count("\n", 0, m.start()) + 1, fn, want, got, line.strip()[:70]))
    return bad


def none_guard_check(name, src):
    # measure() 可能返回 None（真机两次整轮中止都是它 ✗）：
    #   `运算符 > 不能用于操作数 None 和 14`（sun_shift）
    #   `运算符 <= 不能用于操作数 None 和 5`（cactus_sort_line）
    # 判据：一行里 measure( 参与了比较/算术、但**没有** None 判断 ⇒ 可疑 ✓
    bad = []
    for i, line in enumerate(src.split("\n"), 1):
        s2 = line.strip()
        if s2.startswith("#") or "measure(" not in s2:
            continue
        if "None" in s2:
            continue                      # 已经判过 None ✓
        if re.search(r"measure\s*\([^)]*\)\s*(<=|>=|<|>|==|!=|\+|-|\*|//)", s2) or \
           re.search(r"(<=|>=|<|>|==|!=|\+|-|\*|//)\s*measure\s*\(", s2):
            bad.append((i, s2[:80]))
    return bad


def main(argv):
    if len(argv) == 0:
        argv = GAME_FILES
    ok_names = whitelist()
    print("白名单方法数：", len(ok_names))
    bad = 0
    for name in argv:
        p = os.path.join(SAVE, name)
        if not os.path.exists(p):
            print("  [skip]", name, "不存在")
            continue
        src = open(p, encoding="utf-8").read()
        hits = []
        for i, line in enumerate(src.split("\n"), 1):
            s = line.strip()
            if s.startswith("#"):
                continue                       # 注释不算
            # 排除我们自己模块的调用（util.xxx / jobs.xxx / budget.xxx ...）——
            # 它们不是「集合方法」，查了就全是假警报 ✗
            if re.search(r"\b(util|budget|jobs|block_farm|dino_fast|stage_w\d+|stage_row|st|cur|df|mod)\.",
                         line):
                continue
            for m in re.finditer(r"\.([A-Za-z_][A-Za-z_0-9]*)\(", line):
                fn = m.group(1)
                if fn not in ok_names:
                    hits.append((i, fn, s[:90]))
        if hits:
            bad = bad + len(hits)
            print("  !!", name, "用了", len(hits), "处未支持的集合方法：")
            for i, fn, s in hits:
                print("     L%d  .%s()  ->  %s" % (i, fn, s))
        else:
            print("  ok", name)
        for i2, ln in none_guard_check(name, src):
            print("     !! L%d measure() 的值未判 None 就拿去比较/运算 -> %s" % (i2, ln))
            bad = bad + 1
        for i2, fn, want, got, ln in arity_check(name, src):
            print("     !! L%d %s() 形参 %d 个，这里传了 %d 个 -> %s" % (i2, fn, want, got, ln))
            bad = bad + 1
    print("总计可疑点（含参数个数）:", bad)
    return 0 if bad == 0 else 1


sys.exit(main(sys.argv[1:]))
