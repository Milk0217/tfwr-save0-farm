# -*- coding: utf-8 -*-
# ============================================================
# test_stage_owner.py —— 多无人机「一区一 owner」的**运行期**机械验收（R5）
#
# 背景（2026-11-02，Lead 利用率优化）：w8/w12 的任务槽位扩容后，新增了
#   pumpkin / rot0..3 / sun 等副机任务。扩容的**硬约束**是：
#     「同一块地只有一个 owner」—— 副机在飞时，主机**绝不许**碰那块区域 ✗
#   （这个 bug 项目里踩过好几次：主机与副机同时建/收同一座迷宫 ⇒ 互相抹掉 ✗）
#
# 本测试怎么验（不靠读代码、靠**真跑**）：
#   1) 把 jobs 的四个"动手入口"（sweep_columns / sun_shift / pumpkin_shift / maze_shift）
#      换成**记录器**（不真的干活，只记下区域参数）
#   2) 对每个档位造一个假世界、`import` 档位模块、`mod.set_active(mask)` 后调 `mod.run()`
#      —— 这正是 full_run 每轮的真实顺序（先 spawn 置 ACTIVEB → set_active → run）
#   3) 对每个 mask，断言「主机调用的每个区域」与「ACTIVE=1 的任务区域」**两两不重叠** ✓
#      另外用「全空闲」场景验证主机**确实**会干活（否则测试可能空转通过 ✗）
#
# 覆盖档位：stage_w8（本次扩容）/ stage_w12（本次扩容）/ stage_w16、stage_w22（回归）
# 用法：python tools/test_stage_owner.py
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

# (模块名, Expand 等级, 世界边长)
STAGES = [("stage_w8", 5, 8), ("stage_w12", 6, 12),
          ("stage_w16", 7, 16), ("stage_w22", 8, 22)]


def prep(lv, name):
    """假世界 + 注入 builtins + 重新 import 该档模块（与 test_stage_assign 同口径）"""
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
    import jobs as J
    return w, mod, J, ns


def overlap(a, b):
    if a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]:
        return 0
    if a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]:
        return 0
    return 1


def task_regions(j, mod):
    """一个任务实际会碰的**全部**区域：大多数就是 (x0,y0,w,h)；
    w12 的 sun+maze 组合任务还额外含向日葵带（由 roles 指定）⇒ 都算上 ✓"""
    regs = []
    has = "x0" in j
    if has:
        regs.append((j["x0"], j["y0"], j["w"], j["h"]))
    nm = j["name"]
    if nm == "sun+maze":
        rl = j["roles"]
        if len(rl) >= 4:
            regs.append((rl[0], rl[1], rl[2], rl[3]))
    if nm == "pumpkin":
        b = mod.BLOCK
        regs.append((0, 0, b, b))
    return regs


def patch_jobs(J, rec):
    """把 jobs 的四个动手入口换成记录器；返回恢复函数"""
    orig = {}

    def mk(name):
        def f(*a):
            rec.append((name, a))
            return 0
        return f

    for nm in ["sweep_columns", "sun_shift", "pumpkin_shift", "maze_shift"]:
        orig[nm] = getattr(J, nm)
        setattr(J, nm, mk(nm))

    def restore():
        for nm in orig:
            setattr(J, nm, orig[nm])
    return restore


def call_region(name, a, mod):
    if name == "sweep_columns":
        return (a[0], a[1], a[2], a[3])
    if name == "sun_shift":
        return (a[0], a[1], a[2], a[3])
    if name == "maze_shift":
        return (a[0], a[1], a[2], a[2])       # maze_shift(x0,y0,side,cycles)
    if name == "pumpkin_shift":
        b = mod.BLOCK
        return (0, 0, b, b)                    # 方块固定在 (0,0)
    return None


def check_stage(name, lv, side):
    errs = []
    w, mod, J, ns = prep(lv, name)
    js = mod.assign(8)
    ntasks = len(js)
    REAL("== %s（world %d）| 任务数 %d ==" % (name, side, ntasks))

    # ---- 场景 A：全空闲（没有副机在飞）⇒ 主机应该干活（否则测试可能空转通过 ✗）----
    rec = []
    restore = patch_jobs(J, rec)
    try:
        mod.set_active([0] * ntasks)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.run()
    finally:
        restore()
    if len(rec) == 0:
        errs.append("%s 全空闲时主机**什么都没干**（主机该兜底 ✗）" % name)
    REAL("   全空闲：主机调用 %d 次（%s）"
         % (len(rec), ",".join(sorted(set(x[0] for x in rec)))))

    # ---- 场景 B/C：各种 ACTIVE 组合 ⇒ 主机绝不许碰在飞任务的区域 ----
    masks = []
    masks.append(("全部在飞", [1] * ntasks))
    i = 0
    while i < ntasks:
        m = [0] * ntasks
        m[i] = 1
        masks.append(("只 %s 在飞" % js[i]["name"], m))
        i = i + 1
    for label, mask in masks:
        # 模拟"有副机在飞"：mock 的 num_drones = w.drones（host 1 + 副机）
        w.drones = 1 + sum(mask)
        rec = []
        restore = patch_jobs(J, rec)
        try:
            mod.set_active(mask)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                mod.run()
        finally:
            restore()
        active_regs = []
        k = 0
        while k < ntasks:
            if mask[k] == 1:
                active_regs = active_regs + task_regions(js[k], mod)
            k = k + 1
        bad = 0
        for (nm, a) in rec:
            r = call_region(nm, a, mod)
            if r == None:
                continue
            for tr in active_regs:
                if overlap(r, tr) == 1:
                    bad = bad + 1
                    errs.append("%s [%s] 主机的 %s 区域 %r 与在飞任务区域 %r 重叠 ✗（R5 违规）"
                                % (name, label, nm, r, tr))
        if bad == 0:
            REAL("   [%s] 主机 %d 次调用均不碰在飞任务区域 ✓" % (label, len(rec)))
    w.drones = 1
    return errs, ntasks


def run_tasks_once(name, side):
    """把 assign(cap) 给出的**每个任务都真跑一遍**（mock 的 spawn_drone 是同步执行 ⇒
    等于把任务函数按 full_run 的口径调一次）。
    目的：机械验证新增任务的参数自洽（区域在界内、w>=1、rotation 的 roles 长度 == w、
    cycles>=1），以及**运行期不抛异常**（真机抛异常会整轮中止 ✗）。"""
    errs = []
    w, mod, J, ns = prep(lv_of(name), name)
    w.lv["megafarm"] = 4                      # cap=16，保证同步 spawn 不会被名额挡住 ✓
    w.drones = 1
    cap = 8
    js = mod.assign(cap)
    REAL("== %s：把 %d 个任务各真跑一遍 ==" % (name, len(js)))
    for j in js:
        nm = j["name"]
        x0 = j["x0"]
        y0 = j["y0"]
        wd = j["w"]
        ht = j["h"]
        if x0 < 0 or y0 < 0 or x0 + wd > side or y0 + ht > side:
            errs.append("%s 任务 %s 区域越界 (%d,%d,%d,%d)" % (name, nm, x0, y0, wd, ht))
        if wd < 1 or ht < 1:
            errs.append("%s 任务 %s 区域非正 w=%d h=%d" % (name, nm, wd, ht))
        if j["cycles"] < 1:
            errs.append("%s 任务 %s cycles=%d < 1" % (name, nm, j["cycles"]))
        if nm.startswith("rot") or nm == "sun+maze":
            rl = j["roles"]
            if not isinstance(rl, list):
                errs.append("%s 任务 %s 的 roles 不是列表" % (name, nm))
            elif nm != "sun+maze" and len(rl) != wd:
                errs.append("%s 任务 %s roles 长度 %d != w %d"
                            % (name, nm, len(rl), wd))
        buf = io.StringIO()
        try:
            # full_run 的 spawn 口径：entry(x0, y0, w, h, cycles, world, roles)
            with contextlib.redirect_stdout(buf):
                ns["spawn_drone"](j["entry"], x0, y0, wd, ht,
                                  j["cycles"], side, j["roles"])
            ok = 1
        except Exception as e:
            ok = 0
            errs.append("%s 任务 %s 真跑抛异常：%r" % (name, nm, e))
        if ok == 1:
            REAL("   %-9s @(%2d,%2d) %dx%d cycles=%-2d 真跑通过 ✓"
                 % (nm, x0, y0, wd, ht, j["cycles"]))
    return errs


def lv_of(name):
    for n, lv, side in STAGES:
        if n == name:
            return lv
    return 7


def main():
    REAL("=== test_stage_owner：一区一 owner（R5）运行期机械验收 ===")
    errs = []
    total = 0
    for name, lv, side in STAGES:
        e, n = check_stage(name, lv, side)
        errs = errs + e
        total = total + n
        REAL("")
    # ---- 本次扩容的档位：新增任务**逐个真跑**（参数自洽 + 不抛异常）----
    errs = errs + run_tasks_once("stage_w8", 8)
    REAL("")
    errs = errs + run_tasks_once("stage_w12", 12)
    REAL("")
    REAL("=" * 96)
    REAL("任务总数 %d；违规 %d 项" % (total, len(errs)))
    if errs:
        i = 0
        while i < len(errs) and i < 30:
            REAL("  !", errs[i])
            i = i + 1
        REAL("结果：FAIL %d" % len(errs))
        return 1
    REAL("结果：PASS（每个档位、每种 ACTIVE 组合下，主机都不碰在飞副机的区域 ✓）")
    return 0


sys.exit(main())
