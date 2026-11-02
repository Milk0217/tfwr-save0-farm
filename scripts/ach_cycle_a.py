# 成就「循环导入」—— 跑的是 a，报错就是成功
# 依据 docs/game/scripting/import.md：`from x import *` 互导时，
# b 会在 a 还没执行完时把 a 的**空**全局解包走 ⇒ 之后调用 b 里引用 x 的函数就会报
# "x has never been defined ... you probably have an import cycle"。
print("[ach] cycle_a: 开始，先导入 cycle_b")
from ach_cycle_b import *
x = 0
print("[ach] cycle_a: x 已定义，现在调用 b 的函数（它引用的是空快照里的 x）")
ach_b_func()
print("[ach] cycle_a: 竟然没报错 ⇒ 说明这条路径没触发，请把这几行发我")
