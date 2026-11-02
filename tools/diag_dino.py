# -*- coding: utf-8 -*-
# diag_dino.py —— 定点验证「委托 dino_fast」这条链：
#   建一个 world 16 的假世界、解锁恐龙、给足仙人掌，直接调 jobs.dino_run，
#   看它能不能吃满目标颗数、骨头是不是 = 尾巴²（这是判据，不是 PASS 计数）
import builtins
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import farm_mock as FM

P = FM.REAL_PRINT


def main():
    w = FM.World(300000.0)
    w.lv["expand"] = 7          # 16x16
    for k in ["plant", "carrots", "trees", "sunflowers", "pumpkins", "cactus",
              "mazes", "megafarm", "dinosaurs", "hats"]:
        w.lv[k] = 1
    w.rebuild_board()
    w.items["cactus"] = 100000
    w.items["pumpkin"] = 100000
    ns = FM.make_ns(w)
    for k in ns:
        setattr(builtins, k, ns[k])
    for nm in ["util", "budget", "jobs", "block_farm", "dino_fast"]:
        sys.modules.pop(nm, None)
    sys.path.insert(0, FM.SAVE)
    import jobs
    import budget

    P("world =", ns["get_world_size"](), "| 骨头目标 =", budget.bone_goal(),
      "| 一颗苹果 =", jobs.cactus_per_apple(), "仙人掌 | 倍率 =", jobs.dino_bone_mult())
    b0 = w.items.get("bone", 0)
    c0 = w.items.get("cactus", 0)
    eaten = jobs.dino_run(ns["get_world_size"]())
    b1 = w.items.get("bone", 0)
    c1 = w.items.get("cactus", 0)
    P("dino_run 返回", eaten, "| 骨头", b0, "->", b1, "（+", b1 - b0, "）",
      "| 仙人掌", c0, "->", c1, "（-", c0 - c1, "）")
    n = 0
    while n * n <= b1 - b0:
        n = n + 1
    P("反推尾巴长度 ≈", n - 1, "（骨头应 = 尾巴²）| 尾巴长度实测 =", w.eaten,
      "| 步数 =", w.clock)
    P("=" * 60)
    ok = (b1 - b0) > 0
    P("结果：", "PASS" if ok else "FAIL", "| 这一趟拿到", b1 - b0, "骨头")
    return 0 if ok else 1


sys.exit(main())
