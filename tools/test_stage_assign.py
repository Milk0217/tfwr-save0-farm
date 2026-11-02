# -*- coding: utf-8 -*-
# ============================================================
# test_stage_assign.py —— 多无人机利用率：各档位 assign(cap) 的机械验收
#
# 背景（Lead 2026-11-02）：真机利用率  cap=4 49.4% / cap=8 30.6% / cap=16 21.8% ✗
#   怀疑点：每个档位的任务名单只有 5~7 个槽位，不随 cap 增长 ⇒ 想"按 cap 增加迷宫区"。
#   本测试回答三个问题（全部机械验，不靠猜）：
#     ① 每档 assign(cap) 在 cap=2/4/8/16 下到底给几个任务、能放飞几个（=min(任务数, cap-1)）
#     ② 任务区域是否两两不相交、是否都在棋盘内（"一区一架"的硬约束 ✓）
#     ③ 迷宫区能否扩容：各档 lands() 是否还有空余格？现有迷宫区能否切成更多正方形？
#        （w12 的 6x6 切成 2 个等面积正方形 = 每块 18 格 ⇒ 不是平方数 ⇒ 物理上不可能 ✓）
#
# 结论口径（写死在断言里）：
#   * 所有档位 lands() 都已**铺满**（空余格 0）⇒ 在不占用其它产线地块的前提下，
#     **无法新增迷宫区**（w8/w12/w16/w22 全部）✓
#   * w16/w22 的迷宫任务在实际 cap 下**始终在可放飞名额内**（不会被轮作切片挤掉）✓
#   * 利用率低的根因**分成两半**：
#     ① w8/w12 的「非迷宫任务槽位」太少 —— **2026-11-02 已由 cactus-fixer 扩容**：
#        w8: 1 → 7 个任务（maze+pumpkin+rot0..3+sun）；w12: ROT_MAX 4 → 6（共 7 个）
#        ⇒ 见下面每档的机械期望值（w8 可放飞 1/3/7/7；w12 可放飞 1/3/7/7）
#        ⇒ 主机侧配套：按「区域是否有副机」判断，绝不同时碰副机的区（R5）
#     ② w16/w22 槽位本已够（w22 cap=16 任务 16 > 可放飞 15）⇒ 剩余瓶颈在 full_run 的
#        ACTIVEB「全体副机死光才清零 + ACTIVE_TTL」语义：短命任务死掉后 wave 内不补派
#        （这是 Lead/full_run 侧的策略，见回报 ✓）
# ============================================================
import builtins
import contextlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import farm_mock as FM                      # noqa: E402

SAVE = FM.SAVE
REAL = FM.REAL_PRINT
CAPS = [2, 4, 8, 16]
# (模块名, Expand 等级, 该档世界边长)
STAGES = [("stage_w8", 5, 8), ("stage_w12", 6, 12),
          ("stage_w16", 7, 16), ("stage_w22", 8, 22)]


def prep(lv, name):
    """造一个假世界 + 注入 builtins + 重新 import 该档模块（模块全局要干净的一份）"""
    w = FM.World(100000.0)
    w.lv["expand"] = lv
    for k in ["plant", "carrots", "trees", "sunflowers", "pumpkins",
              "mazes", "megafarm", "cactus"]:
        w.lv[k] = 1
    w.rebuild_board()
    ns = FM.make_ns(w)
    for k in ns:
        setattr(builtins, k, ns[k])
    for nm in ["util", "budget", "jobs", "block_farm", name]:
        sys.modules.pop(nm, None)
    sys.path.insert(0, SAVE)
    mod = __import__(name)
    return mod, ns


def overlap(a, b):
    # a/b = (x, y, w, h)；1 = 有重叠
    if a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]:
        return 0
    if a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]:
        return 0
    return 1


def task_region(j, has_x):
    if has_x:
        return (j["x0"], j["y0"], j["w"], j["h"])
    return None


def run_stage(name, lv, side):
    mod, ns = prep(lv, name)
    errs = []
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        e = mod.enter()
        v = mod.verify_lands()
    if e != 1:
        errs.append("%s enter()=%r（应 1）" % (name, e))
    if v != 1:
        errs.append("%s verify_lands()=%r（应 1）" % (name, v))
    lnd = mod.lands()
    covered = 0
    for r in lnd:
        covered = covered + r[3] * r[4]
    free = side * side - covered
    maze_rects = [r for r in lnd if r[0].startswith("maze")]
    REAL("== %s（world %d）| lands %d 格 / 空余 %d 格 | 迷宫区 %d 座 %r"
         % (name, side, covered, free, len(maze_rects),
            [(r[1], r[2], r[3], r[4]) for r in maze_rects]))
    if free != 0:
        errs.append("%s lands() 有空余 %d 格（与预期'全铺满'不符）" % (name, free))
    rows = []
    for cap in CAPS:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            js = mod.assign(cap)
        tasks = len(js)
        spawnable = tasks
        if cap - 1 < spawnable:
            spawnable = cap - 1
        n_maze = 0
        n_maze_spawn = 0
        regions = []
        for j in js:
            has_x = "x0" in j
            nm = j["name"]
            is_maze = (nm == "maze" or nm == "maze0" or nm == "maze1"
                       or nm == "maze2" or nm == "maze3" or nm == "sun+maze")
            if is_maze:
                n_maze = n_maze + 1
            if has_x:
                r = (j["x0"], j["y0"], j["w"], j["h"])
                regions.append((nm, r))
                # 界检查
                if r[0] < 0 or r[1] < 0 or r[0] + r[2] > side or r[1] + r[3] > side:
                    errs.append("%s cap=%d 任务 %s 区域 %r 越界" % (name, cap, nm, r))
                # 迷宫必须正方形（maze_life 的硬要求）
                if nm != "sun+maze" and is_maze:
                    if r[2] != r[3]:
                        errs.append("%s 迷宫任务 %s 不是正方形 %r" % (name, nm, r))
            # 迷宫名额是否在可放飞范围内（cap 实际用得到的情况）
            if is_maze:
                if js_to_index(js, j) < spawnable:
                    n_maze_spawn = n_maze_spawn + 1
        # 槽位瓶颈判据：任务数 < cap-1 ⇒ 有副机位却没人可派（任务名单不够长）
        slot_short = 0
        if tasks < cap - 1:
            slot_short = 1
        # 区域两两不相交（"一区一架"硬约束）
        i = 0
        while i < len(regions):
            k = i + 1
            while k < len(regions):
                if overlap(regions[i][1], regions[k][1]) == 1:
                    errs.append("%s cap=%d 任务区域重叠：%s %r ✗ %s %r"
                                % (name, cap, regions[i][0], regions[i][1],
                                   regions[k][0], regions[k][1]))
                k = k + 1
            i = i + 1
        rows.append((cap, tasks, spawnable, n_maze, n_maze_spawn, slot_short))
        REAL("   cap=%2d => 任务数 %2d（可放飞 %2d）| 迷宫任务 %d 座（可放飞 %d 座）"
             "| 槽位瓶颈 %s | 区域 %d 块两两不相交 ✓"
             % (cap, tasks, spawnable, n_maze, n_maze_spawn,
                "是 ✗" if slot_short == 1 else "否", len(regions)))
    return rows, errs


def js_to_index(js, target):
    i = 0
    while i < len(js):
        if js[i] is target:
            return i
        i = i + 1
    return -1


def main():
    REAL("=== test_stage_assign：各档 assign(cap) 任务数 / 区域 / 迷宫扩容可行性 ===")
    all_rows = {}
    errs = []
    for name, lv, side in STAGES:
        rows, e = run_stage(name, lv, side)
        all_rows[name] = (side, rows)
        errs = errs + e
        REAL("")

    # ---- 汇总表（Lead 要的"可派任务数表"）----
    REAL("=" * 96)
    REAL("档位      | cap=2 任务/可放飞 | cap=4 | cap=8 | cap=16 | 迷宫座数(不随cap变)")
    for name, lv, side in STAGES:
        side2, rows = all_rows[name]
        cells = []
        nmaze = 0
        for (cap, tasks, sp, nm, nms, slot) in rows:
            cells.append("%d/%d" % (tasks, sp))
            nmaze = nm
        REAL("%-9s | %-15s | %-5s | %-5s | %-6s | %d 座"
             % (name, cells[0], cells[1], cells[2], cells[3], nmaze))

    # ---- 机械断言：迷宫扩容可行性 ----
    REAL("=" * 96)
    for name, lv, side in STAGES:
        side2, rows = all_rows[name]
        # 所有 cap 下任务数都 <= 可放飞 ⇒ 说明"任务数随 cap 扩张"这件事**本来就没做到**
        cap16 = rows[3]
        REAL("%-9s：cap=16 任务数 %d / 可放飞 %d；迷宫任务 %d 座"
             % (name, cap16[1], cap16[2], cap16[3]))
    # w8（2026-11-02 cactus-fixer 扩容）：任务数 1 → **7**
    #   （maze + pumpkin + rot0..rot3 + sun，区域两两不相交，全部取自 lands() 已有的 4 块地 ✓）
    #   可放飞 = min(7, cap-1)：cap=2/4/8/16 ⇒ 1/3/7/7
    w8rows = all_rows["stage_w8"][1]
    w8_tasks_expect = 7
    w8_spawn_expect = {2: 1, 4: 3, 8: 7, 16: 7}
    for (cap, tasks, sp, nm, nms, slot) in w8rows:
        if tasks != w8_tasks_expect:
            errs.append("stage_w8 cap=%d 任务数 %d != %d（扩容后应为 maze+pumpkin+rot0..3+sun）"
                        % (cap, tasks, w8_tasks_expect))
        if sp != w8_spawn_expect[cap]:
            errs.append("stage_w8 cap=%d 可放飞 %d != %d"
                        % (cap, sp, w8_spawn_expect[cap]))
    # w12（2026-11-02 cactus-fixer 扩容）：ROT_MAX 4 → 6 ⇒ 任务数 = 1(sun+maze) + min(cap-2, 6, 6)
    #   cap=2/4/8/16 ⇒ 任务数 1/3/7/7；可放飞 = min(任务数, cap-1) ⇒ 1/3/7/7
    w12rows = all_rows["stage_w12"][1]
    w12_tasks_expect = {2: 1, 4: 3, 8: 7, 16: 7}
    w12_spawn_expect = {2: 1, 4: 3, 8: 7, 16: 7}
    for (cap, tasks, sp, nm, nms, slot) in w12rows:
        if tasks != w12_tasks_expect[cap]:
            errs.append("stage_w12 cap=%d 任务数 %d != %d（ROT_MAX=6 后应为 1+min(cap-2,6,6)）"
                        % (cap, tasks, w12_tasks_expect[cap]))
        if sp != w12_spawn_expect[cap]:
            errs.append("stage_w12 cap=%d 可放飞 %d != %d"
                        % (cap, sp, w12_spawn_expect[cap]))
    # w16/w22：实际 cap（8/16）下，全部迷宫任务必须在可放飞名额内
    for name, capname in (("stage_w16", 8), ("stage_w22", 16)):
        rows = all_rows[name][1]
        for (cap, tasks, sp, nm, nms, slot) in rows:
            if cap == capname:
                if nms < nm:
                    errs.append("%s cap=%d 只有 %d/%d 座迷宫可放飞（迷宫被挤掉 ✗）"
                                % (name, cap, nms, nm))

    # ---- 用户报的 w8/w12 扩容诉求：机械证明"物理不可行" ----
    REAL("")
    REAL("迷宫扩容物理约束（不改其它 owner 地块的前提下）：")
    for name, lv, side in STAGES:
        side2, rows = all_rows[name]
        lnd_free = side * side - sum(r[3] * r[4] for r in __import__(name).lands())
        REAL("  %-9s：棋盘 %2dx%2d=%3d 格，lands 已用满（空余 %d 格）⇒ 新增一座同尺寸迷宫**无地可用** ✗"
             % (name, side, side, side * side, lnd_free))
    REAL("  stage_w12 追加证明：现有迷宫 6x6=36 格，切成 2 个等面积**正方形**需每块 18 格，"
         "而 18 不是平方数 ⇒ 数学上不可能；切成 4 个 3x3 可以，但 gold/物质 从 6 掉到 3（×0.5）✗")
    REAL("  stage_w8  追加证明：现有迷宫 4x4=16 格，2 座 4x4 需 32 格；全盘 64 格已 4 块各 16 格占满 ⇒ 不可能 ✗")
    REAL("  ⇒ 结论：**w8/w12/w16/w22 都无法在不占用其它产线地块的前提下新增迷宫区**（如实回报 ✓）")
    REAL("  ⇒ 但 **非迷宫任务槽位**已于 2026-11-02 扩容：")
    REAL("     stage_w8  任务数 1 -> 7（maze+pumpkin+rot0..3+sun）| 可放飞 cap=2/4/8/16 => 1/3/7/7")
    REAL("     stage_w12 任务数 1+min(cap-2,6,6)（ROT_MAX 4 -> 6）| 可放飞 => 1/3/7/7")
    REAL("  ⇒ 剩余利用率瓶颈 = full_run 的 ACTIVEB「全体副机死光才清零 + ACTIVE_TTL」语义")
    REAL("     （w22 cap=16 任务数 16 > 可放飞 15 ⇒ 槽位已满；短命任务死后 wave 内不补派 —— Lead 侧策略）")
    REAL("=" * 96)
    if errs:
        REAL("FAIL %d 项：" % len(errs))
        for e in errs:
            REAL("  !", e)
        REAL("结果：FAIL %d" % len(errs))
        return 1
    REAL("结果：PASS（各档 assign 任务数/区域不相交/扩容可行性全部机械验收）")
    return 0


sys.exit(main())
