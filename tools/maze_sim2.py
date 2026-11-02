# -*- coding: utf-8 -*-
# ============================================================
# maze_sim2.py —— 离线模拟二：把 32x32 拆成 N 座 k x k 小迷宫值不值？
#
# 第一轮结论（maze_sim.py）：
#   32x32、32 个猎人时，宝藏到「最近的家」的**真实树距离只有约 10 步**，
#   而现行贪心 DFS 要走 **约 700 步** ⇒ 现行算法浪费了约 70 倍！
#   实测 2.857 秒/宝藏 ↔ 若一 move = 94 tick、6075 tick/s（0.0155 秒）则约 185 步
#   ⇒ 实测的 185 步 = 「多架并行的贪心 DFS 里最先到达的那一架」。
#
# 本脚本要回答：k 与「每座迷宫的猎人数 m」怎么选，才能让胜者步数最小、
# 同时金币/秒最大。金币/宝藏 = k^2 x 2^(lv-1) = 32 k^2（lv6）。
# ============================================================

import random
from collections import deque

DIRS = [(0, 1), (1, 0), (0, -1), (-1, 0)]
TICK_PER_ACTION = 94.0          # 2 倍速下的实测值（另一口径 200 也一起算）
ENGINE_TICKS = 6075.0


def make_maze(rng, k, torus):
    def idx(x, y):
        return (y % k) * k + (x % k)

    def nb(x, y):
        out = []
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if torus:
                out.append((nx % k, ny % k))
            elif 0 <= nx < k and 0 <= ny < k:
                out.append((nx, ny))
        return out

    adj = [[] for _ in range(k * k)]
    seen = [False] * (k * k)
    x, y = rng.randrange(k), rng.randrange(k)
    seen[idx(x, y)] = True
    stack = [(x, y)]
    while stack:
        x, y = stack[-1]
        cand = [(a, b) for a, b in nb(x, y) if not seen[idx(a, b)]]
        if not cand:
            stack.pop()
            continue
        nx, ny = rng.choice(cand)
        seen[idx(nx, ny)] = True
        adj[idx(x, y)].append(idx(nx, ny))
        adj[idx(nx, ny)].append(idx(x, y))
        stack.append((nx, ny))
    return adj


def remove_walls(rng, adj, k, torus, count):
    """每次 relocation「随机拆掉一些墙」⇒ 树上加 count 条额外边"""
    def idx(x, y):
        return (y % k) * k + (x % k)
    added = 0
    tries = 0
    while added < count and tries < count * 40:
        tries += 1
        x, y = rng.randrange(k), rng.randrange(k)
        dx, dy = rng.choice(DIRS)
        nx, ny = x + dx, y + dy
        if not torus and not (0 <= nx < k and 0 <= ny < k):
            continue
        a, b = idx(x, y), idx(nx, ny)
        if b in adj[a]:
            continue
        adj[a].append(b)
        adj[b].append(a)
        added += 1
    return added


def bfs_dist(adj, src, k):
    d = [-1] * (k * k)
    d[src] = 0
    q = deque([src])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if d[v] < 0:
                d[v] = d[u] + 1
                q.append(v)
    return d


def greedy_dfs(adj, k, start, target, limit):
    x0, y0 = start % k, start // k
    tx, ty = target % k, target // k
    visited = {start}
    stack = []
    cur = start
    steps = 0
    while steps < limit:
        steps += 1
        if cur == target:
            return steps
        x, y = cur % k, cur // k
        best, best_d = None, 10 ** 9
        for dx, dy in DIRS:
            nx, ny = (x + dx) % k, (y + dy) % k
            cand = (ny % k) * k + (nx % k)
            if cand in adj[cur] and cand not in visited:
                dd = abs(nx - tx) + abs(ny - ty)
                if dd < best_d:
                    best_d, best = dd, cand
        if best is not None:
            stack.append(cur)
            visited.add(best)
            cur = best
        else:
            if not stack:
                return limit
            cur = stack.pop()
    return limit


def hunters_in_maze(rng, k, m, torus):
    """m 个猎人均匀铺在 k x k 迷宫里（避免重叠）"""
    cells = [(x, y) for y in range(k) for x in range(k)]
    if m >= len(cells):
        sel = cells
    else:
        sel = rng.sample(cells, m)
    return [(y % k) * k + (x % k) for x, y in sel]


def scenario(k, m, ntrials=15, relocations=0, torus=True, seed=7):
    """返回 [最优树距离均值, 贪心DFS胜者步数均值]"""
    rng = random.Random(seed)
    opt, grd = [], []
    for _ in range(ntrials):
        adj = make_maze(rng, k, torus)
        if relocations:
            remove_walls(rng, adj, k, torus, relocations)
        H = hunters_in_maze(rng, k, m, torus)
        multi = [10 ** 9] * (k * k)
        for h in H:
            dd = bfs_dist(adj, h, k)
            for i in range(k * k):
                if dd[i] >= 0 and dd[i] < multi[i]:
                    multi[i] = dd[i]
        for _ in range(12):
            tgt = rng.randrange(k * k)
            opt.append(multi[tgt])
            # 所有猎人同时搜 ⇒ 胜者 = 最先到达的那一架
            best = 10 ** 9
            for h in H:
                s = greedy_dfs(adj, k, h, tgt, 4 * k * k + 40)
                if s < best:
                    best = s
            grd.append(best)
    return sum(opt) / len(opt), sum(grd) / len(grd)


def rate(k, m, steps, tick=TICK_PER_ACTION):
    """每座迷宫一机一份，N 座并行 ⇒ 金币/秒（lv6：每宝藏 32 k^2）"""
    n_mazes = (32 // k) ** 2
    drones = n_mazes * m
    if drones > 32:
        return None, n_mazes, drones
    t = steps * tick / ENGINE_TICKS
    return n_mazes * (32 * k * k) / t, n_mazes, drones


if __name__ == "__main__":
    print("tick/action =", TICK_PER_ACTION, " engine =", ENGINE_TICKS, "tick/s")
    print()
    print("  k   m  mazes drones | 最优树距离 | 贪心DFS胜者步数 | 金币/分(94t) | 金币/分(200t)")
    for k in (4, 8, 16, 32):
        for m in (1, 2, 4, 8, 32):
            nm = (32 // k) ** 2
            if nm * m > 32 or m > k * k:
                continue
            o, g = scenario(k, m)
            r94, nm2, dr = rate(k, m, g, 94.0)
            r200, _, _ = rate(k, m, g, 200.0)
            print("%3d %3d %6d %6d | %10.1f | %14.1f | %12.0f | %12.0f"
                  % (k, m, nm, dr, o, g, r94 * 60, r200 * 60))
    print()
    print("参照：现行 32x32 + 32 猎人的实测 = 688,000 金币/分（2.857 秒/宝藏）")
