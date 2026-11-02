# ============================================================
# deadcode.py —— 找出「从入口出发到不了的顶层函数」，并生成 patch_lines.py 的 spec
#
# 为什么需要它：main.py 里同时躺着 4 架时代、8 架时代、单机时代的三套历史路径，
# 它们不只是占行数 —— 旧 work_pumpkin() 只数第 0 号方阵，误用就会出现「南瓜只收一片」
# 的怪象；靠人眼找「谁还被谁调用」在这个规模上一定会漏。
#
# 做法（纯静态、机械）：
#   1. 扫出所有**顶格 def**（本项目的脚本没有嵌套 def），记录每段的行号区间；
#   2. 每段函数体里出现过的「已知函数名」记为一条调用边；
#   3. 入口 = 命令行给的名字（默认 main8），外加**顶层语句**里引用到的名字
#      （例如文件末尾的入口分派 `if drone_cap() >= 7: main8()`）；
#   4. 从入口做可达性搜索，不可达的顶层 def 就是死代码；
#   5. `模块名.函数名` 这种跨文件引用（w_pumpkin.loop_pumpkin_smart）也算一条边。
#
# 用法：
#   python deadcode.py main.py [入口名...]          # 只报告
#   python deadcode.py main.py --spec out.json      # 顺便生成删除用的 spec
#
# 注意：它只判断「顶层 def 是否可达」，不删除任何东西；真正落盘走 patch_lines.py，
#       而后者会再核一遍锚点/行号，所以误判也不会直接毁文件。
# ============================================================
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAVE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

DEF_RE = re.compile(r"^def\s+([A-Za-z_]\w*)\s*\(")
NAME_RE = re.compile(r"[A-Za-z_]\w*")
ATTR_RE = re.compile(r"([A-Za-z_]\w*)\.([A-Za-z_]\w*)")
STR_RE = re.compile(r'"[^"]*"')
DOTTED_RE = re.compile(r"[A-Za-z_]\w*\.[A-Za-z_]\w*")


def code_of(line):
    """剥掉字符串字面量、注释与点号表达式，只留「本文件自己的裸名字」。
    必须剥注释：本项目注释里到处写 `main.py`、`game_loop`、`work_pumpkin` 这些名字，
    不剥的话它们会把死代码「撑活」（第一版就因此漏报了 game_loop / main / 旧 work_pumpkin）。
    必须剥点号表达式：`spawn_drone(w_pumpkin.loop_pumpkin_smart, ...)` 里的属性名
    与本文件那个**已死的同名函数**撞名，会被误判成一条边（第二版就漏报了它）。"""
    s = STR_RE.sub('""', line).split("#")[0]
    return DOTTED_RE.sub("", s)


def scan(path):
    src = open(path, encoding="utf-8").read()
    lines = src.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    funcs = []          # (name, def_line_idx)
    for i, ln in enumerate(lines):
        m = DEF_RE.match(ln)
        if m:
            funcs.append((m.group(1), i))
    spans = {}
    for k, (name, start) in enumerate(funcs):
        # 段尾 = 下一个顶格 def 之前，去掉尾部空行
        end = funcs[k + 1][1] if k + 1 < len(funcs) else len(lines)
        # 顶层语句（非缩进、非空、非注释）会打断函数的归属
        j = start + 1
        while j < end:
            ln = lines[j]
            if ln.strip() == "" or ln.startswith("\t") or ln.startswith(" "):
                j += 1
                continue
            break
        end = j
        while end > start + 1 and lines[end - 1].strip() == "":
            end -= 1
        spans[name] = (start + 1, end)      # 1-based 闭区间
    return lines, funcs, spans


def main():
    args = [a for a in sys.argv[1:]]
    spec_out = None
    if "--spec" in args:
        k = args.index("--spec")
        spec_out = args[k + 1]
        del args[k:k + 2]
    # --no-top：不把顶层语句当入口。用来问「只从 main8 出发，还有哪些是死的」——
    # 文件末尾那句入口分派 `if drone_cap() >= 7: main8() else: main4()` 会把 main4/main
    # 自己撑成「活的」，而那正是要删的东西，所以必须能把它关掉。
    no_top = "--no-top" in args
    if no_top:
        args.remove("--no-top")
    # --keep a,b：明确「故意保留」的函数（例如 read_carrot_votes 是备而不用的回退路径），
    # 它们仍然算可达，免得每次跑都刷一堆已知的噪声。
    keep = set()
    if "--keep" in args:
        k = args.index("--keep")
        keep = set(x.strip() for x in args[k + 1].split(",") if x.strip())
        del args[k:k + 2]
    if not args:
        print("usage: python deadcode.py main.py [entry...] [--spec out.json]")
        return 2
    fname = args[0]
    entries = args[1:] or ["main8"]
    path = fname if os.path.isabs(fname) else os.path.join(SAVE, fname)

    lines, funcs, spans = scan(path)
    names = set(spans)

    # 每个函数体引用到哪些已知函数名
    #
    # **不要**把 `模块名.函数名` 当成本文件的调用边：本代码里点号后面的名字要么是枚举
    # （`Items.Cactus` / `Unlocks.Mazes`），要么是跨模块调用（`w_pumpkin.loop_pumpkin_smart`）——
    # 而后者恰好与本文件里那个**已经死掉的同名函数**重名，认下去就会把它撑活
    # （第一版就因此漏报了 main.py 里那份 loop_pumpkin_smart / work_pumpkin_smart）。
    edges = {}
    for name, start in funcs:
        s, e = spans[name]
        body = "\n".join(code_of(x) for x in lines[s:e])
        refs = set(w for w in NAME_RE.findall(body) if w in names and w != name)
        edges[name] = refs

    # 顶层语句（不属于任何函数体的行）作为额外的入口来源
    covered = set()
    for name in spans:
        s, e = spans[name]
        for i in range(s - 1, e):
            covered.add(i)
    top_refs = set()
    for i, ln in enumerate(lines):
        if i in covered:
            continue
        for w in NAME_RE.findall(code_of(ln)):
            if w in names:
                top_refs.add(w)

    entry = set(x for x in entries if x in names) | keep
    if not no_top:
        entry |= top_refs
    seen = set()
    stack = list(entry)
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for nxt in edges.get(cur, ()):
            if nxt not in seen:
                stack.append(nxt)

    dead = [n for n, _ in funcs if n not in seen]
    print(f"== {fname}: 顶层 def {len(funcs)} 个，入口 {sorted(entry)}")
    print(f"   可达 {len(seen)} 个；**不可达 {len(dead)} 个**")
    ops = []
    for n in dead:
        s, e = spans[n]
        print(f"   - {n}() 行 {s}-{e}（{e - s + 1} 行）")
        ops.append({"op": "delete", "start": s, "end": e,
                    "first_contains": f"def {n}(",
                    "last_contains": lines[e - 1].strip()[:40] if lines[e - 1].strip() else ""})

    if spec_out:
        # 顺带把「删完会多出来的空行」也收掉：每个被删段后面若还有空行，多删一行
        cleaned = []
        for op in ops:
            s = op["start"]
            e = op["end"]
            if e + 1 < len(lines) and lines[e].strip() == "":
                e = e + 1
            cleaned.append({"op": "delete", "start": s, "end": e,
                            "first_contains": op["first_contains"],
                            "last_contains": op["last_contains"]})
        spec = {"file": fname, "expect_lines": len(lines), "ops": cleaned}
        outp = spec_out if os.path.isabs(spec_out) else os.path.join(SAVE, spec_out)
        with open(outp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)
        print(f"   spec 已写 {outp}（{len(cleaned)} 个 delete op）")
    return 0


sys.exit(main())
