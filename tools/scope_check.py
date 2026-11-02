# -*- coding: utf-8 -*-
# ============================================================
# scope_check.py —— 第 7 道门：**跨函数引用局部变量**（真机会整轮中止 ✗）
#
# 真机报错实录（2026-10-08）：
#   `Error: KEYS 从未被定义。在使用变量之前必须先给它赋值。`
#   `In: main <- key_affordable`
#   —— KEYS 是 key_change_allowed() 里的**局部变量**，我在另一个函数里引用了它 ✗
#   而 audit_save0.py **没拦住**（它只做名字层面的检查、不做作用域分析 ✗）
#
# 判据（静态可查 ✓）：
#   某个名字 **只在别的函数内部被赋值**、却在**本函数里被读取而本函数没赋值**、
#   且它不是模块级名字、也不是内置 ⇒ 必定是作用域错误 ✓
#
# 自测：文件末尾用一段**故意写错的代码**验证本工具报得出来 ✓
# 用法：python tools/scope_check.py [文件...]
# ============================================================
import ast
import os
import sys

SAVE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
FILES = ["full_run.py", "util.py", "budget.py", "jobs.py", "block_farm.py",
         "stage_w1.py", "stage_row.py", "stage_w3.py", "stage_w4.py", "stage_w6.py",
         "stage_w8.py", "stage_w12.py", "stage_w16.py", "stage_w22.py"]

BUILTINS = set(dir(__builtins__)) | {
    "North", "East", "South", "West", "Entities", "Items", "Unlocks", "Grounds", "Hats",
    "get_world_size", "get_pos_x", "get_pos_y", "move", "can_move", "harvest", "plant",
    "till", "use_item", "num_items", "num_unlocked", "get_cost", "get_time", "measure",
    "swap", "change_hat", "spawn_drone", "num_drones", "max_drones", "clear", "do_a_flip",
    "get_entity_type", "get_ground_type", "can_harvest", "get_companion", "print", "len",
    "range", "append", "insert", "pop", "remove", "world_changed", "get_tick_count",
    "unlock", "do_a_flip", "set_world_size",
    "has_finished",
}


def assigned_names(node):
    # 一个 AST 子树里**被赋值的顶层名字**（含 for 目标、参数、with as 等）
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(n.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                out.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                out.add(a.asname or a.name)
    return out


def module_level_names(tree):
    # ⚠⚠ 只能看**顶层语句**：用 ast.walk(tree) 会把函数体内的赋值也算成模块级 ✗
    #   （本工具第一版就这么写了 ⇒ 自测显示「没抓到」⇒ 那 14 个 ok 全是假绿 ✗✗）
    out = set()
    for st in tree.body:
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(st.name)          # 只取**函数名**，不下潜进函数体 ✓
        else:
            out = out | assigned_names(st)
    return out


def check(src, label):
    tree = ast.parse(src)
    module_names = module_level_names(tree)
    funcs = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    # 「只在函数里被赋值」的名字 → 记下是哪些函数
    own = {}
    for f in funcs:
        own[f.name] = assigned_names(f)
    bad = []
    for f in funcs:
        local = own[f.name]
        for n in ast.walk(f):
            if not isinstance(n, ast.Name) or not isinstance(n.ctx, ast.Load):
                continue
            nm = n.id
            if nm in local or nm in module_names or nm in BUILTINS:
                continue
            owners = [g for g in own if g != f.name and nm in own[g]]
            if len(owners) > 0:
                bad.append((n.lineno, f.name, nm, owners[0]))
    return bad


def undefined_check(src):
    # 第二类判据（2026-10-08 补）：**整个文件里都没定义**却被读取的顶层名字 ✗
    #   真实事故：stage_w12/w16/w22 的 ROLES 表被我一次"顺手清理"切掉了 ✗
    #   ⇒ 定义 0 条、引用 3~8 处 ⇒ 进档即 NameError ⇒ **整轮中止** ✓
    #   旧判据只查「别的函数的局部变量」✗ ⇒ 抓不到"谁都没定义"这种 ✓
    tree = ast.parse(src)
    defined = assigned_names(tree)          # 任何地方被赋值的（超集 ⇒ 保守，少误报 ✓）
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            pass
    bad = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Name) or not isinstance(n.ctx, ast.Load):
            continue
        nm = n.id
        if nm in defined or nm in BUILTINS:
            continue
        bad.append((n.lineno, nm))
    return bad


def main(argv):
    files = argv if len(argv) > 0 else FILES
    total = 0
    for name in files:
        p = os.path.join(SAVE, name)
        if not os.path.exists(p):
            continue
        src = open(p, encoding="utf-8").read()
        bad = check(src, name)
        if bad:
            total = total + len(bad)
            print("  !!", name, "有", len(bad), "处跨函数引用局部变量：")
            for ln, f, nm, owner in bad:
                print("     L%d %s() 里用到 %s，而它只是 %s() 的局部变量 ✗" % (ln, f, nm, owner))
        else:
            print("  ok", name)
        for ln, nm in undefined_check(src):
            print("     !! L%d 读取了 %s，但**本文件里从未定义** ✗（进档即 NameError ⇒ 整轮中止）" % (ln, nm))
            total = total + 1
    # ---- 自测：故意写一个和真机一模一样的错误，本工具必须报出来 ✓ ----
    demo = ("def other():\n\tKEYS = [1, 2]\n\treturn KEYS\n\n\n"
            "def user():\n\treturn KEYS[0]\n")
    hit = check(demo, "selftest")
    print("自测（跨函数引用局部变量）：", "抓到 ✓" if len(hit) == 1 else "没抓到 ✗（工具失效）")
    demo2 = ("def run():\n\tprint(ROLES_TOP[0])\n")
    hit2 = undefined_check(demo2)
    print("自测（整文件未定义的名字）：", "抓到 ✓" if len(hit2) == 1 else "没抓到 ✗（工具失效）")
    print("总计可疑点:", total)
    return 0 if (total == 0 and len(hit) == 1 and len(hit2) == 1) else 1


sys.exit(main(sys.argv[1:]))
