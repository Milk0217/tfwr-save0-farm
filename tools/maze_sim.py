# -*- coding: utf-8 -*-
# ============================================================
# maze_sim.py —— 离线模拟「刷迷宫换金币」的走位成本
#
# 为什么要它：maze_gold.py 的实测是 164 次宝藏 / 468 秒 = 688k 金币/分，
# 而目标 2M/分 需要把「每次宝藏的胜者步数」压到约 1/3。游戏内试错很贵
# （每次改动都要用户手动跑），所以先在本地把「走位步数」这件事算清楚。
#
# 模型（全部来自 docs/game/unlocks/mazes.md 与实测）：
#   * 迷宫是一棵生成树（无环），宝藏位置随机；
#   * 每次 relocation 会「随机拆掉一些墙」⇒ 树 + 若干条额外边（有环）；
#   * measure() 全场返回宝藏坐标（免费）⇒ 问题纯粹是「走到那个格子」；
#   * 一个 move = 200 tick，引擎 6075 tick/s ⇒ 一次宝藏的墙钟 = 步数 x 0.0329 秒。
#
# 产出：三种结构 x 两种策略下的「胜者平均步数」，以及拆分小迷宫后的对比。
# ============================================================

import random
import sys
from collections import deque

N = 32
DIRS = [(0, 1), (1, 0), (0, -1), (-1, 0)]   # N E S W


def idx(x, y):
    return (y % N) * N + (x % N)


def neighbors(x, y, torus=True):
    if torus:
        return [((x + dx) % N, (y + dy) % N) for dx, dy in DIRS]
    out = []
    for dx, dy in DIRS:
        nx, ny = x + dx, y + dy
        if 0 <= nx < N and 0 <= ny < N:
            out.append((nx, ny))
    return out


# ------------------------------------------------------------
# 迷宫生成：三棵树，全部是「生成树」（无环）
# ------------------------------------------------------------
def maze_dfs(rng, torus=True):
    """递归回溯（游戏里最可能的实现，走廊又长又绕）"""
    adj = [[] for _ in range(N * N)]
    seen = [False] * (N * N)
    x, y = rng.randrange(N), rng.randrange(N)
    seen[idx(x, y)] = True
    stack = [(x, y)]
    while stack:
        x, y = stack[-1]
        cand = [(nx, ny) for nx, ny in neighbors(x, y, torus) if not seen[idx(nx, ny)]]
        if not cand:
            stack.pop()
            continue
        nx, ny = rng.choice(cand)
        seen[idx(nx, ny)] = True
        adj[idx(x, y)].append(idx(nx, ny))
        adj[idx(nx, ny)].append(idx(x, y))
        stack.append((nx, ny))
    return adj


def maze_kruskal(rng, torus=True):
    """Kruskal 随机生成树（走廊短、分叉多）"""
    parent = list(range(N * N))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    edges = []
    for y in range(N):
        for x in range(N):
            for nx, ny in neighbors(x, y, torus):
                a, b = idx(x, y), idx(nx, ny)
                if a < b:
                    edges.append((a, b))
    rng.shuffle(edges)
    adj = [[] for _ in range(N * N)]
    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
            adj[a].append(b)
            adj[b].append(a)
    return adj


def maze_wilson(rng, torus=True):
    """Wilson 算法 = 均匀生成树（UST），平均距离最短的一类"""
    adj = [[] for _ in range(N * N)]
    intree = [False] * (N * N)
    root = rng.randrange(N * N)
    intree[root] = True
    remaining = [i for i in range(N * N) if i != root]
    rng.shuffle(remaining)
    for start in remaining:
        if intree[start]:
            continue
        path = [start]
        pos = start
        while not intree[pos]:
            x, y = pos % N, pos // N
            nxt = idx(*rng.choice(neighbors(x, y, torus)))
            if nxt in path:
                path = path[: path.index(nxt) + 1]
            else:
                path.append(nxt)
            pos = nxt
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            adj[a].append(b)
            adj[b].append(a)
            intree[a] = True
    return adj


# ------------------------------------------------------------
# 距离表
# ------------------------------------------------------------
def all_dist(adj, src):
    d = [-1] * (N * N)
    d[src] = 0
    q = deque([src])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if d[v] < 0:
                d[v] = d[u] + 1
                q.append(v)
    return d


def all_dist_multi(adj, srcs):
    d = [-1] * (N * N)
    q = deque()
    for s in srcs:
        d[s] = 0
        q.append(s)
    while q:
        u = q.popleft()
        for v in adj[u]:
            if d[v] < 0:
                d[v] = d[u] + 1
                q.append(v)
    return d


# ------------------------------------------------------------
# 现行的贪心 DFS（照抄 maze_gold.py 的 hunt()）
# ------------------------------------------------------------
def greedy_dfs_steps(adj, start, target, limit=4000):
    visited = {start}
    path = []
    cur = start
    steps = 0
    while steps < limit:
        steps += 1
        if cur == target:
            return steps
        x, y = cur % N, cur // N
        tx, ty = target % N, target // N
        best, best_d = None, 10 ** 9
        for d, (dx, dy) in enumerate(DIRS):
            nx, ny = (x + dx) % N, (y + dy) % N
            cand = idx(nx, ny)
            if cand in adj[cur] and cand not in visited:
                dd = abs(nx - tx) + abs(ny - ty)
                if dd < best_d:
                    best_d, best = dd, cand
        if best is not None:
            path.append(cur)
            visited.add(best)
            cur = best
        else:
            if not path:
                return 0
            cur = path.pop()
    return 0


# 现行脚本的 32 个「家」（BUILD 45 公式）
def homes():
    out = []
    for k in range(32):
        out.append(((k % 8) * 4 + 2, (k // 8) * 8 + 4))
    return out


def run(kind, torus=True, ntrials=40, seed=1, greedysamples=40, verbose=True):
    rng = random.Random(seed)
    gen = {"dfs": maze_dfs, "kruskal": maze_kruskal, "wilson": maze_wilson}[kind]
    opt_home, opt_any, greedy_home, greedy_any, diam = [], [], [], [], []
    for t in range(ntrials):
        adj = gen(rng, torus)
        H = [idx(x, y) for x, y in homes()]
        d = all_dist_multi(adj, H)          # 每个格子到「最近的家」的距离
        # 胜者 = 离宝藏最近的猎人（曼哈顿最近的家 = 脚本的 Voronoi 规则）
        d_all = [all_dist(adj, h) for h in H]
        for _ in range(200):
            tgt = rng.randrange(N * N)
            opt_home.append(min(dd[tgt] for dd in d_all))
        # 上界：32 个猎人放在「k-中位」上（多源 BFS 的贪心选点）
        sel = []
        for _ in range(32):
            dd = all_dist_multi(adj, sel) if sel else [10 ** 9] * (N * N)
            far = max(range(N * N), key=lambda i: dd[i])
            sel.append(far)
        dd = all_dist_multi(adj, sel)
        for _ in range(200):
            opt_any.append(dd[rng.randrange(N * N)])
        # 贪心 DFS 的实际步数（脚本真正的算法）
        for _ in range(greedysamples):
            tgt = rng.randrange(N * N)
            h = min(H, key=lambda s: d[s] if d[s] >= 0 else 10 ** 9)
            greedy_home.append(greedy_dfs_steps(adj, h, tgt))
            greedy_any.append(greedy_dfs_steps(adj, rng.choice(H), tgt))
        diam.append(max(all_dist(adj, 0)))
    def avg(v):
        return sum(v) / len(v)
    if verbose:
        print("[%s torus=%s] 最优走位(最近的家的树距离) 平均 %.1f | 32 个中位点 %.1f"
              % (kind, torus, avg(opt_home), avg(opt_any)))
        print("          贪心DFS(从最近的家出发) 平均 %.1f | 贪心DFS(随机家) 平均 %.1f | 直径 %.1f"
              % (avg(greedy_home), avg(greedy_any), avg(diam)))
    return avg(opt_home), avg(opt_any), avg(greedy_home), avg(greedy_any)


if __name__ == "__main__":
    print("=== 32x32、32 个猎人：每次宝藏要走多少步 ===")
    for kind in ("dfs", "kruskal", "wilson"):
        for torus in (True, False):
            run(kind, torus, ntrials=12, greedysamples=25)
    print()
    print("=== 参照：脚本实测（200 tick/动作、6075 tick/s）===")
    print("2.857 秒/宝藏 -> 约 87 步 ; 主机自报平均 952 步（它没有 Voronoi 门控）")
    sys.stdout.flush()
