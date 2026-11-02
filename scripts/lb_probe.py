# ============================================================
# lb_probe.py —— 【二分定位用】逐模块 import，每步先打印
#
# 背景（2026-10-27）：
#   跑 `lb_enter` 的 WHICH=2（点名 full_run）时报
#     `Error: 导入的模块存在语法错误。  In:`（空栈）
#   而 WHICH=3（点名 probe_expand）**正常跑完** ✓ ⇒ 加载机制没问题 ✓
#   ⇒ 问题在 full_run 的依赖链里 ✓ ⇒ 用本文件二分：
#      每次跑，日志最后一条 `[p] ...` 就是**最后一个成功的模块** ✓
#      下一条（没打印出来）就是**出问题的那个** ✓
#
# 用法：lb_enter.py 里 WHICH = 4 ⇒ 点名本文件 ✓
# ============================================================

print("[p] 0 start")
import util
print("[p] 1 util ok")
import budget
print("[p] 2 budget ok")
import block_farm
print("[p] 3 block_farm ok")
import jobs
print("[p] 4 jobs ok")
import stage_w1
print("[p] 5 stage_w1 ok")
import stage_row
print("[p] 6 stage_row ok")
import stage_w3
print("[p] 7 stage_w3 ok")
import stage_w4
print("[p] 8 stage_w4 ok")
import stage_w6
print("[p] 9 stage_w6 ok")
import stage_w8
print("[p] 10 stage_w8 ok")
import stage_w12
print("[p] 11 stage_w12 ok")
import stage_w16
print("[p] 12 stage_w16 ok")
import stage_w22
print("[p] 13 stage_w22 ok")
print("[p] === 全部 import 成功（那问题就不在 import，而在 full_run 的模块级代码）===")
