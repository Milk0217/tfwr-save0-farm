# -*- coding: utf-8 -*-
# diag_cactus.py —— 最小诊断：种一株仙人掌，立刻读回它的尺寸
#   目的：把「measure() 返回 None」这层黑盒拆开，看是 mock 的哪个环节没接上
import builtins
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import farm_mock as FM

P = FM.REAL_PRINT


def main():
    w = FM.World(10000.0)
    w.lv["expand"] = 8
    w.lv["plant"] = 1
    w.lv["cactus"] = 1
    w.rebuild_board()
    w.items["pumpkin"] = 500
    ns = FM.make_ns(w)
    for k in ns:
        setattr(builtins, k, ns[k])
    for nm in ["util", "budget", "jobs", "block_farm"]:
        sys.modules.pop(nm, None)
    sys.path.insert(0, FM.SAVE)
    import util

    P("Entities.Cactus =", repr(ns["Entities"].Cactus))
    P("ground(6,16) =", w.ground.get((6, 16)))
    util.go_to(6, 16)
    ns["till"]()
    P("till 之后 ground =", w.ground.get((6, 16)))
    r = ns["plant"](ns["Entities"].Cactus)
    P("plant 返回 =", r, "| w.cactus =", w.cactus, "| ent =", w.ent.get((6, 16)))
    P("get_entity_type() =", ns["get_entity_type"]())
    P("measure() =", ns["measure"]())
    ns["move"]("East")
    P("挪到 (7,16) 后 measure(West) =", ns["measure"]("West"), "（应为刚才那株的尺寸）")
    return 0


sys.exit(main())
