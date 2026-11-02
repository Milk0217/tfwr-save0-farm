# ============================================================
# audit_save0.py —— 给这个存档里的脚本做静态体检（用桌面 Python 跑，不是游戏内脚本）
#
# 为什么需要它：游戏内的脚本一旦出错就整轮中断，而且错误只会打到 output.txt 里。
# 常见且致命的两种「编辑残留」：
#   1. **列表下标越界 / 重复声明**：同一个名字被声明两次，后一个（常常是旧版）覆盖前一个。
#      实测：`CHECK = [1,1,1]` 后面还留着旧的 `CHECK = [1,1]` → 运行时报
#      「索引 2 超出了列表 [1,1] 的范围」，整轮开跑即中断。
#   2. **用了没赋值的变量名**：游戏解释器对未定义名字直接报错中断。
#
# 用法：python audit_save0.py [文件名...]
#       默认体检 main.py / maze_gold.py / dino_bones.py / dino_fast.py
# ============================================================
import re
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SAVE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

BUILTIN = set("""get_pos_x get_pos_y move can_move measure harvest plant num_items num_unlocked
get_entity_type get_ground_type get_water get_time get_tick_count clear change_hat get_world_size
max_drones num_drones spawn_drone wait_for for_all range append len print unlock get_cost
use_item till swap do_a_flip quick_print get_companion set_world_size trade can_afford
can_harvest num_items abs min max str remove pop insert add has_finished get_drone_id
get_active_power set_execution_speed simulate leaderboard_run round dict set
Items Entities Grounds Unlocks Hats North East South West Leaderboards""".split())
# ---- 从**权威存根** `__builtins__.py` 补全函数名/类名 ----
# 手抄名单一定会漏：第一次就漏了 `pet_the_piggy`（存根第 2287 行确实有它），
# 于是把一段完全正确的代码报成"未解析名字"。存根是游戏随包生成的，直接读它。
# 读不到就退回手抄名单，不让工具因为缺文件而崩。
STUB_BUILTINS = 0
try:
    _src = open("__builtins__.py", encoding="utf-8", errors="replace").read()
    for _m in re.finditer(r'^\s*(?:def|class)\s+([A-Za-z_]\w*)', _src, re.M):
        BUILTIN.add(_m.group(1))
    STUB_BUILTINS = 1
except Exception:
    STUB_BUILTINS = 0
KW = set("None True False and or not if while for in else elif return break continue def pass".split())


def clean(code):
    code = re.sub(r'"[^"]*"', '""', code)                     # 去掉字符串字面量
    # `a.b` -> `a`：本语言里点号右边要么是枚举成员（Hats.X / Items.Cactus），要么是
    # 跨模块函数（w_pumpkin.loop_pumpkin_smart）。**右边那个名字不是一个变量**，
    # 不剥掉的话，主控里删掉同名函数之后就会误报「未定义名字」（实测踩过）。
    code = re.sub(r"\b([A-Za-z_]\w*)\.[A-Za-z_]\w*", r"\1", code)
    return code


def lhs_names(code):
    # 取出赋值左侧的**所有**名字，兼容嵌套解包 `ptype, (px, py) = cp`
    head = code.split("=")[0]
    return set(re.findall(r"[A-Za-z_]\w*", head))


def audit(path):
    src = open(path, encoding="utf-8").read()
    lines = src.split("\n")
    problems = []
    # `import layout` / `import w_pumpkin` 会引入模块名本身（`w_pumpkin.loop_pumpkin_smart`），
    # 它不是「未定义名字」，先把模块名收进来，避免误报。
    modules = set(re.findall(r"^\s*import\s+([A-Za-z_]\w*)", src, re.M))
    modules |= set(re.findall(r"^\s*from\s+([A-Za-z_]\w*)\s+import", src, re.M))
    # 由 append() 或下标赋值动态增长的列表：长度不是字面量，不参与下标越界判断
    dynamic = set(re.findall(r"append\(\s*([A-Za-z_]\w*)\s*,", src))
    dynamic |= set(re.findall(r"^\s*([A-Za-z_]\w*)\[[^\]]+\]\s*=", src, re.M))
    # --- 1) 顶层列表字面量：重复声明 + 下标越界 ---
    lists = {}
    for n, line in enumerate(lines, 1):
        m = re.match(r"^([A-Z_][A-Z0-9_]*)\s*=\s*\[([^\]]*)\]\s*(#.*)?$", line)
        if m:
            name, body = m.group(1), m.group(2).strip()
            cnt = 0 if body == "" else len(body.split(","))
            if name in lists:
                problems.append(f"重复声明: {name} 第 {n} 行（另有第 {lists[name][1]} 行，后者会覆盖前者）")
            lists[name] = (cnt, n)
    for n, line in enumerate(lines, 1):
        code = line.split("#")[0]
        for m in re.finditer(r"([A-Z_][A-Z0-9_]*)\[(\d+)\]", code):
            name, idx = m.group(1), int(m.group(2))
            if name in dynamic:
                continue
            if name in lists and idx >= lists[name][0]:
                problems.append(f"下标越界: 第 {n} 行 {name}[{idx}]，但 {name} 只有 {lists[name][0]} 项")
    # --- 2) 函数内使用了没赋值的名字 ---
    top, funcs, cur = set(), {}, None
    for n, line in enumerate(lines, 1):
        code0 = line.split("#")[0]
        code = clean(code0)
        m0 = re.match(r"^def\s+(\w+)\s*\(([^)]*)\)", code0)
        if m0:
            cur = m0.group(1)
            top.add(cur)
            funcs[cur] = {"params": set(x.strip().split("=")[0].strip() for x in m0.group(2).split(",") if x.strip()),
                          "asg": set(), "use": []}
            continue
        if re.match(r"^[A-Za-z_]\w*\s*=", code):
            top.add(code.split("=")[0].strip())
        if re.match(r"^[A-Za-z_]", code):
            cur = None
            continue
        if cur is None or not code.strip():
            continue
        lhs = re.match(r"^\s*[A-Za-z_][\w\s,()]*?=(?!=)", code)
        if lhs:
            funcs[cur]["asg"] |= lhs_names(code)
        fm = re.match(r"^\s*for\s+([\w\s,()]+?)\s+in\s", code)
        if fm:
            funcs[cur]["asg"] |= set(re.findall(r"[A-Za-z_]\w*", fm.group(1)))
        for w in re.findall(r"[A-Za-z_]\w*", code):
            funcs[cur]["use"].append((w, n))
    for f, d in funcs.items():
        known = d["asg"] | d["params"] | top | BUILTIN | KW | modules
        for w, n in d["use"]:
            if w not in known:
                problems.append(f"未定义名字: {f}() 第 {n} 行用到 '{w}'")
    return problems


def main():
    names = sys.argv[1:] or ["main.py", "maze_gold.py", "dino_bones.py", "dino_fast.py"]
    total = 0
    for name in names:
        path = os.path.join(SAVE, name)
        if not os.path.exists(path):
            print(f"[skip] {name} 不存在")
            continue
        ps = audit(path)
        print(f"== {name}: {len(ps)} 个可疑点")
        for x in ps:
            print("   -", x)
        total += len(ps)
    print("总计可疑点:", total)


main()
