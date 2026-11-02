# 成就「栈溢出」—— 跑它，游戏报 "maximum call stack size has been reached" 就是成功
# 依据错误串 @error_max_stack_size_reached。刻意写成**非尾递归**（返回值还要参与运算），
# 免得被尾调用优化掉。
def ach_boom(n):
	x = ach_boom(n + 1)
	return x + 1

print("[ach] 现在制造栈溢出……")
ach_boom(0)
print("[ach] 没崩？说明这个语言的递归不涨栈 ⇒ 请把这一行发我")
