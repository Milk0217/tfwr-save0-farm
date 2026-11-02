# -*- coding: utf-8 -*-
# ============================================================
# maze_sim3.py —— 离线模拟三：一座迷宫的完整生命周期（复用 300 次）值多少金币/分
#
# 关键机制（docs/game/unlocks/mazes.md）：
#   * 在宝藏上再灌一次物质 = 收掉当前宝藏 + 在**同一座迷宫**里随机重定位，最多 300 次；
#   * **每次重定位会随机拆掉一些墙** ⇒ 迷宫越来越开阔 ⇒ 走路越来越短；
#   * 一座 k x k 迷宫的内部墙槽 = 2k(k-1)，生成树占 k^2-1 条通道
#     ⇒ 初始墙数 = 2k(k-1) - (k^2-1) = k^2 - 2k + 1 = (k-1)^2
#     ⇒ **k=4 只有 9 面墙、k=8 有 49 面**，而重定位有 300 次 ⇒ 小迷宫会**被拆到全开**，
#       大迷宫（k=32：961 面墙）在 300 次里根本开不了 ⇒ 这是「小迷宫」结构性优势的来源。
#
# 本脚本给出：不同 k / 每座猎人数 m 下，整条生命周期上的平均「胜者步数」与金币/分。
# ============================================================

import random
from collections import deque

DIRS = [(0, 1), (1, 0), (0, -1), (-1, 0)]
ENGINE_TICKS = 6075.0
LIFE = 301                      # 1 次建迷宫 + 300 次重定位


def build(rng, k):
    adj = [set() for _ in range(k * k)]
    seen = [False] * (k * k)

    def idx(x, y):
        return y * k + x

    x, y = rng.randrange(k), rng.randrange(k)
    seen[idx(x, y)] = True
    stack = [(x, y)]
    while stack:
        x, y = stack[-1]
        cand = []
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < k and 0 <= ny < k and not seen[idx(nx, ny)]:
                cand.append((nx, ny))
        if not cand:
            stack.pop()
            continue
        nx, ny = rng.choice(cand)
        seen[idx(nx, ny)] = True
        adj[idx(x, y)].add(idx(nx, ny))
        adj[idx(nx, ny)].add(idx(x, y))
        stack.append((nx, ny))
    return adj


def wall_slots(k):
    out = []
    for y in range(k):
        for x in range(k):
            for dx, dy in ((0, 1), (1, 0)):
                nx, ny = x + dx, y + dy
                if nx < k and ny < k:
                    out.append((y * k + x, ny * k + nx))
    return out


def greedy(adj, k, start, target, limit):
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
        best, bd = None, 10 ** 9
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < k and 0 <= ny < k):
                continue
            cand = ny * k + nx
            if cand in adj[cur] and cand not in visited:
                dd = abs(nx - tx) + abs(ny - ty)
                if dd < bd:
                    bd, best = dd, cand
        if best is not None:
            stack.append(cur)
            visited.add(best)
            cur = best
        else:
            if not stack:
                return limit
            cur = stack.pop()
    return limit


def life_avg(k, m, rng, remove_per_reloc, samples_per_phase=6):
    """模拟一座迷宫的一生：返回平均胜者步数"""
    adj = build(rng, k)
    slots = wall_slots(k)
    homes = rng.sample(range(k * k), m)
    total = 0.0
    cnt = 0
    for reloc in range(LIFE):
        if reloc > 0:
            for _ in range(remove_per_reloc):
                a, b = rng.choice(slots)
                adj[a].add(b)
                adj[b].add(a)
        for _ in range(samples_per_phase):
            tgt = rng.randrange(k * k)
            best = 10 ** 9
            for h in homes:
                s = greedy(adj, k, h, tgt, 4 * k * k + 40)
                if s < best:
                    best = s
            total += best
            cnt += 1
    return total / cnt


def rate(k, m, steps, tick):
    n_mazes = (32 // k) ** 2
    drones = n_mazes * m
    if drones > 32:
        return None
    t = steps * tick / ENGINE_TICKS
    return n_mazes * (32 * k * k) / t * 60


if __name__ == "__main__":
    rng = random.Random(20261005)
    print("每宝藏金币(lv6)=32k^2；一座迷宫一生 = %d 次宝藏；一 move = 200 tick" % LIFE)
    print()
    print("  k  m 座数 机数 | 拆墙/次 | 一生平均步数 | 金币/分(200t) | 金币/分(94t)")
    for rpr in (0, 1, 2):
        for k, m in ((4, 1), (8, 1), (8, 2), (16, 2), (16, 8), (32, 32)):
            nm = (32 // k) ** 2
            if nm * m > 32:
                continue
            s = life_avg(k, m, rng, rpr)
            r200 = rate(k, m, s, 200.0)
            r94 = rate(k, m, s, 94.0)
            print("%3d %3d %4d %4d | %7d | %12.1f | %13.0f | %12.0f"
                  % (k, m, nm, nm * m, rpr, s, r200, r94))
        print()
    print("实测参照：现行 32x32 单迷宫 + 复用 = 688,000 金币/分")
