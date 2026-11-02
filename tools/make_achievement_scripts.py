# -*- coding: utf-8 -*-
# ============================================================
# make_achievement_scripts.py —— 生成四个成就用的脚本
#
# 依据（全部来自游戏自带文档/错误串，不靠外部资料）：
#  1. 循环导入：docs/game/scripting/import.md「Import Cycles」给了**确切会出错**的写法
#     （`from x import *` 互导），而错误串 @error_missing_import 明确提示
#     "If you have imported it, you probably have an import cycle"。
#  2. 栈溢出：错误串 @error_max_stack_size_reached =
#     "The maximum call stack size has been reached. This is most likely due to
#      too many recursive function calls." ⇒ 无终止条件的**非尾**递归。
#  3. 仙人掌错误顺序：Core.dll 里有唯一一个成就判定函数 `CheckWrongOrderAchievement`；
#     文档的 sorted 规则是「N/E 邻居 >= 自己、S/W 邻居 <= 自己」⇒
#     **把两条比较都反向**排出来的就是完全相反的顺序。
#     ⇒ 直接拿已经实测过 34.84M/分的 cactus_big.py，只翻这两处比较（gnome 排序翻比较
#       就是反向排序，移动逻辑不用动）。
#  4. 五顶帽子：docs/game/unlocks/hats.md 的写法（change_hat + do_a_flip）；
#     帽子是"给无人机的" ⇒ 用 spawn_drone 让 5 架各自戴一顶（**必须活着**，所以戴上后要待够时间）。
# ============================================================
import os

SAVE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

FILES = {}

FILES["ach_cycle_a.py"] = '''# 成就「循环导入」—— 跑的是 a，报错就是成功
# 依据 docs/game/scripting/import.md：`from x import *` 互导时，
# b 会在 a 还没执行完时把 a 的**空**全局解包走 ⇒ 之后调用 b 里引用 x 的函数就会报
# "x has never been defined ... you probably have an import cycle"。
print("[ach] cycle_a: 开始，先导入 cycle_b")
from ach_cycle_b import *
x = 0
print("[ach] cycle_a: x 已定义，现在调用 b 的函数（它引用的是空快照里的 x）")
ach_b_func()
print("[ach] cycle_a: 竟然没报错 ⇒ 说明这条路径没触发，请把这几行发我")
'''

FILES["ach_cycle_b.py"] = '''# 成就「循环导入」的另一半：和 ach_cycle_a.py 互相 from ... import *
from ach_cycle_a import *
def ach_b_func():
	print("[ach] cycle_b: 试着读 x ->", x)
'''

FILES["ach_stack_overflow.py"] = '''# 成就「栈溢出」—— 跑它，游戏报 "maximum call stack size has been reached" 就是成功
# 依据错误串 @error_max_stack_size_reached。刻意写成**非尾递归**（返回值还要参与运算），
# 免得被尾调用优化掉。
def ach_boom(n):
	x = ach_boom(n + 1)
	return x + 1

print("[ach] 现在制造栈溢出……")
ach_boom(0)
print("[ach] 没崩？说明这个语言的递归不涨栈 ⇒ 请把这一行发我")
'''

FILES["ach_five_hats.py"] = '''# 成就「五架无人机戴五顶不同的帽子」
# 依据 docs/game/unlocks/hats.md 的写法：change_hat(...) + do_a_flip()
# 关键：帽子属于**无人机**，所以要用 spawn_drone 让 5 架同时各自戴一顶，
# 而且它们**必须活着**（函数返回 = 无人机消失 = 帽子没了）⇒ 戴上后原地翻跟头待够时间。
# 传参只传**整数下标**（枚举对象不保证能跨机传）。
HATS = [Hats.Straw_Hat, Hats.Gray_Hat, Hats.Purple_Hat, Hats.Green_Hat, Hats.Brown_Hat]
HOLD_S = 20.0

def wear(i):
	change_hat(HATS[i])
	do_a_flip()
	print("[ach] 无人机", get_drone_id(), "戴上第", i, "顶帽子")
	t0 = get_time()
	while get_time() - t0 < HOLD_S:
		do_a_flip()
	print("[ach] 无人机", get_drone_id(), "戴帽时间到，收工")

def main():
	print("[ach] 准备让 5 架无人机各戴一顶不同的帽子，保持", HOLD_S, "秒")
	ds = []
	i = 0
	while i < 5:
		d = spawn_drone(wear, i)
		if d != None:
			append(ds, d)
		i = i + 1
	print("[ach] 已经放飞", len(ds), "架")
	i = 0
	while i < len(ds):
		wait_for(ds[i])
		i = i + 1
	# 主线自己也换一顶，凑齐"五顶不同的"
	change_hat(Hats.Traffic_Cone)
	do_a_flip()
	print("[ach] 五顶帽子成就流程结束")

main()
'''

# ---- 仙人掌：拿 cactus_big.py 翻两处比较 ----
src = open(os.path.join(SAVE, "cactus_big.py"), encoding="utf-8").read()
# 只用**子串**做锚点，不依赖缩进（第一次就是栽在缩进上）
FLIP = [
    ("measure(West) <= measure()", "measure(West) >= measure()"),
    ("measure(South) <= measure()", "measure(South) >= measure()"),
]
lines = src.split("\n")
hit_target = 0
for i, l in enumerate(lines):
    if l.startswith("BIG_TARGET_GAIN = 940000000"):
        lines[i] = "BIG_TARGET_GAIN = 1                # 【成就版】只跑一轮就收工"
        hit_target = 1
src = "\n".join(lines)
bad = []
for old, new in FLIP:
    if src.count(old) != 1:
        bad.append(old)
if bad or hit_target != 1:
    print("!! 锚点对不上:", bad, "| target 命中", hit_target)
else:
    for old, new in FLIP:
        src = src.replace(old, new)
    head = ("# 成就「把一片仙人掌按错误的顺序排序」—— cactus_big.py 的**反向**版本\n"
            "# 改动只有两处：行排序与列排序的比较从 `<=` 翻成 `>=`。\n"
            "# gnome 排序翻比较 = 反向排序（移动逻辑不用动）⇒ 整盘变成「向西南递增」的错误顺序。\n"
            "# 原版是「向东北递增」（文档的 sorted 定义）；两处都翻 = 完全相反的 order。\n"
            "# 跑法：直接运行本文件（它会 clear() 整盘，别和别的脚本同时跑）。\n"
            "# ⚠ 反向排完之后**连锁不会扩散**，收割只掉极少量仙人掌 —— 这是预期的，本脚本只为成就。\n" + "#" * 60 + "\n")
    FILES["ach_wrong_order.py"] = head + src
    print("cactus_big.py 反向版已生成（翻转 2 处比较 + 目标改 1）")

for name, text in FILES.items():
    p = os.path.join(SAVE, name)
    open(p, "w", encoding="utf-8", newline="\n").write(text)
    b = open(p, "rb").read()
    print("  %-24s %6d bytes | CRLF %d | lines %d"
          % (name, len(b), b.count(b"\r\n"), b.decode("utf-8").count("\n")))
