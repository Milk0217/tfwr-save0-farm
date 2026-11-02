# 回路构造的单测：覆盖性、无重复、逐格相邻、首尾相邻（闭合）
def build(W):
    cx = []
    cy = []
    y = 0
    while y < W:
        cx.append(0); cy.append(y); y += 1
    c = 1
    while c < W:
        if c % 2 == 1:
            y = W - 1
            while y >= 1:
                cx.append(c); cy.append(y); y -= 1
        else:
            y = 1
            while y <= W - 1:
                cx.append(c); cy.append(y); y += 1
        c += 1
    cx.append(W - 1); cy.append(0)
    c = W - 2
    while c >= 1:
        cx.append(c); cy.append(0); c -= 1
    return cx, cy

bad = 0
for W in (4, 6, 8, 12, 16, 22):
    cx, cy = build(W)
    n = W * W
    assert len(cx) == n, ("长度", W, len(cx))
    seen = set(zip(cx, cy))
    assert len(seen) == n, ("重复", W, len(seen))
    for i in range(n):
        x0, y0 = cx[i], cy[i]
        x1, y1 = cx[(i + 1) % n], cy[(i + 1) % n]
        d = abs(x0 - x1) + abs(y0 - y1)
        assert d == 1, ("不相邻", W, i, (x0, y0), (x1, y1))
    print("W=%2d: %d 格全覆盖、无重复、逐格相邻、首尾闭合  OK" % (W, n))
print("哈密顿回路单测 PASS")
