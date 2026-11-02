# -*- coding: utf-8 -*-
# ============================================================
# loop_check.py —— 第 6 类判据：**循环必须能收敛**
#
# 为什么（真机三次教训，2026-10~11）：
#   ① `maze_map_walk` 起点越界 ⇒ 崩 ✗
#   ② `cactus_sort_line` 跳过空格但允许回退 ⇒ **空转** ✗
#   ③ 同上的回退在病态序列里 ⇒ **卡死**（`[cz] 仙人掌 69542` 冻住不动 ✗✗）
#   ⇒ 规律：凡是可能不收敛的循环（排序/搜索/绕行），**必须有迭代上限或必然更新的条件** ✓
#
# 判据（两条，都能静态查）：
#   A. `while <常量真值>`（True/1）⇒ 体内必须有 `break` 或 `return` ✓
#   B. `while <条件>` ⇒ 条件里至少有一个变量**在体内被更新**（`x = x + c` 之类）✓
#      否则条件永不改变 ⇒ 死循环 ✗
# 白名单：体内含 `break`/`return` 的循环视为"有出口" ✓（B 也放行，避免误报 ✓）
# ============================================================
import ast
import os
import sys

SAVE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
FILES = ["full_run.py", "util.py", "budget.py", "jobs.py", "block_farm.py",
         "stage_w1.py", "stage_row.py", "stage_w3.py", "stage_w4.py", "stage_w6.py",
         "stage_w8.py", "stage_w12.py", "stage_w16.py", "stage_w22.py"]


def is_true_const(t):
    if isinstance(t, ast.Constant):
        return bool(t.value)
    return False


def has_exit(body):
    for n in body:
        for sub in ast.walk(n):
            if isinstance(sub, (ast.Break, ast.Return)):
                return True
    return False


def updated_names(body):
    # 收集 "x = x + c" / "x += c" 形式的被更新变量名
    out = set()
    for stmt in body:
        for n in ast.walk(stmt):
            if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
                out.add(n.target.id)
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        for sub in ast.walk(n.value):
                            if isinstance(sub, ast.Name) and sub.id == t.id:
                                out.add(t.id)
    return out


def test_names(t):
    out = set()
    for n in ast.walk(t):
        if isinstance(n, ast.Name):
            out.add(n.id)
    return out


def check_src(src):
    tree = ast.parse(src)
    bad = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.While):
            continue
        if is_true_const(n.test):
            if not has_exit(n.body):
                bad.append((n.lineno, "while 常量真值且体内无 break/return"))
            continue
        # ⚠ 若条件里有**函数调用**（get_time()/get_entity_type()/num_items()…）
        #   ⇒ 条件由游戏状态驱动 ✓ 会自己变 ⇒ 不算死循环 ✓（消除误报 ✗）
        has_call = False
        for sub in ast.walk(n.test):
            if isinstance(sub, ast.Call):
                has_call = True
        if has_call:
            continue
        tn = test_names(n.test)
        up = updated_names(n.body)
        if tn and not (tn & up):
            if not has_exit(n.body):
                bad.append((n.lineno, "条件里没有任何变量在体内被更新（条件永不变）"))
    return bad


def main():
    total = 0
    for fn in FILES:
        p = os.path.join(SAVE, fn)
        if not os.path.exists(p):
            continue
        bad = check_src(open(p, encoding="utf-8").read())
        if bad:
            for ln, why in bad:
                print("  !! %s:L%d %s" % (fn, ln, why))
                total = total + 1
        else:
            print("  ok", fn)
    # 自测①：死循环必须被抓到
    demo1 = "i = 0\nwhile True:\n\tprint(i)\n"
    h1 = check_src(demo1)
    print("自测（常量真值死循环）：", "抓到 ✓" if len(h1) == 1 else "没抓到 ✗（工具失效）")
    # 自测②：条件永不更新的 while 必须被抓到
    demo2 = "i = 0\nwhile i < 10:\n\tprint(i)\n"
    h2 = check_src(demo2)
    print("自测（条件永不更新）：", "抓到 ✓" if len(h2) == 1 else "没抓到 ✗（工具失效）")
    # 自测③：正常循环不应误报
    demo3 = "i = 0\nwhile i < 10:\n\ti = i + 1\n"
    h3 = check_src(demo3)
    print("自测（正常循环不误报）：", "通过 ✓" if len(h3) == 0 else "误报 ✗")
    print("总计可疑点:", total)
    ok = (total == 0 and len(h1) == 1 and len(h2) == 1 and len(h3) == 0)
    return 0 if ok else 1


sys.exit(main())
