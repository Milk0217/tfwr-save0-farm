# 成就「五架无人机戴五顶不同的帽子」
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
