# -*- coding: utf-8 -*-
# 蛇形路径：下标 <-> 格子 必须**互为逆映射**，且相邻下标在棋盘上真的相邻
def serp_idx(x, y, W):
    if y % 2 == 1:
        return y * W + (W - 1 - x)
    return y * W + x


def serp_cell(i, W):
    y = i // W
    r = i % W
    if y % 2 == 1:
        return W - 1 - r, y
    return r, y


bad = 0
for W in (3, 4, 8, 9, 12, 16, 22):
    seen = set()
    prev = None
    for i in range(W * W):
        x, y = serp_cell(i, W)
        assert 0 <= x < W and 0 <= y < W, (W, i, x, y)
        assert serp_idx(x, y, W) == i, ("逆映射失败", W, i, x, y)
        assert (x, y) not in seen, ("重复格子", W, i, x, y)
        seen.add((x, y))
        if prev is not None:
            d = abs(x - prev[0]) + abs(y - prev[1])
            assert d == 1, ("相邻下标不相邻", W, i, prev, (x, y))
        prev = (x, y)
    print("W=%2d: 覆盖 %d 格、无重复、逐格相邻  OK" % (W, len(seen)))
print("蛇形路径单测 PASS")
