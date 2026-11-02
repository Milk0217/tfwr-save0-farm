# 成就「循环导入」的另一半：和 ach_cycle_a.py 互相 from ... import *
from ach_cycle_a import *
def ach_b_func():
	print("[ach] cycle_b: 试着读 x ->", x)
