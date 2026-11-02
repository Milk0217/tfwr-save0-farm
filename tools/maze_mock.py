# -*- coding: utf-8 -*-
# ============================================================
# maze_mock.py —— 把 maze_gold2.py **原样**跑在一个假的游戏世界里
#
# 为什么：maze_gold2.py 的核心（探测建图 / BFS 距离场 / 沿场走位 / 复用 / 重建）
# 在游戏里出错一次就要用户手动跑一轮才发现，代价太高。这个 harness 用一个
# 32x32 的假棋盘 + 真的生成树迷宫 + 真的墙，把脚本里的函数**直接执行**，
# 量出「每次宝藏走多少步」，并验证不变量。
#
# 用法：python maze_mock.py
# ============================================================
import os
import random
import sys

SAVE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
N = 32
REG = 8
MULT = 32                      # lv6
GOLD_PER = REG * REG * MULT
SUB_PER = REG * MULT
DIRS = [(0, 1), (1, 0), (0, -1), (-1, 0)]     # 与脚本的 North/East/South/West 同序


class Mock:
    def __init__(self, seed=1, region=(0, 0), drift=0):
        self.rng = random.Random(seed)
        self.N = N
        self.region = region
        self.rx, self.ry = region
        self.drift = drift          # 每次重定位随机拆掉几面墙
        self.moves = 0
        self.gold = 0
        self.weird = 10 ** 9
        self.power = 10 ** 6
        self.unlocks = {"mazes": 6}
        self.ground = "grass"
        self.pos = (0, 0)
        self.maze = None
        self.relocations = 0
        self.built = 0
        self.harvest_hedge = 0
        self.max_reloc = 300
        self.log = []

        def clock():
            t = 0.0
            while True:
                t += 0.001
                yield t

        self.clock = clock()
        # 开局 = clear() 之后的空盘（迷宫由被测脚本自己建）
        self.bush = []

    # ---------- 迷宫 ----------
    def in_region(self, x, y):
        rx, ry = self.rx, self.ry
        dx = (x - rx) % N
        dy = (y - ry) % N
        return dx < REG and dy < REG

    def build_maze(self):
        """区域内一棵生成树；边界封闭（与满场迷宫同样的封闭性）"""
        adj = {}
        for y in range(REG):
            for x in range(REG):
                adj[(x, y)] = set()
        seen = set()
        sx, sy = self.rng.randrange(REG), self.rng.randrange(REG)
        seen.add((sx, sy))
        stack = [(sx, sy)]
        while stack:
            x, y = stack[-1]
            cand = []
            for dx, dy in DIRS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < REG and 0 <= ny < REG and (nx, ny) not in seen:
                    cand.append((nx, ny))
            if not cand:
                stack.pop()
                continue
            nx, ny = self.rng.choice(cand)
            seen.add((nx, ny))
            adj[(x, y)].add((nx, ny))
            adj[(nx, ny)].add((x, y))
            stack.append((nx, ny))
        self.maze = adj
        self.treasure = (self.rng.randrange(REG), self.rng.randrange(REG))
        self.relocations = 0
        self.built += 1

    def passable(self, x, y, d):
        if self.maze == None:
            return True
        if not self.in_region(x, y):
            nx, ny = (x + DIRS[d][0]) % N, (y + DIRS[d][1]) % N
            return not self.in_region(nx, ny)     # 外面：边界挡住
        lx, ly = (x - self.rx) % N, (y - self.ry) % N
        nx, ny = (lx + DIRS[d][0]) % REG, (ly + DIRS[d][1]) % REG
        if (nx, ny) not in self.maze[(lx, ly)]:
            return False
        return True

    def step(self, d):
        nx, ny = (self.pos[0] + DIRS[d][0]) % N, (self.pos[1] + DIRS[d][1]) % N
        self.pos = (nx, ny)

    def relocate_treasure(self):
        for _ in range(self.drift):
            lx, ly = self.rng.randrange(REG), self.rng.randrange(REG)
            dx, dy = DIRS[self.rng.randrange(4)]
            nx, ny = lx + dx, ly + dy
            if 0 <= nx < REG and 0 <= ny < REG:
                self.maze[(lx, ly)].add((nx, ny))
                self.maze[(nx, ny)].add((lx, ly))
        self.treasure = (self.rng.randrange(REG), self.rng.randrange(REG))


# ------------------------------------------------------------
# 把游戏 API 绑成一个命名空间
# ------------------------------------------------------------
def make_namespace(w):
    def get_pos_x():
        return w.pos[0]

    def get_pos_y():
        return w.pos[1]

    def can_move(d):
        return w.passable(w.pos[0], w.pos[1], d)

    def move(d):
        if can_move(d):
            w.step(d)
            w.moves += 1
            if w.moves > 3000000:
                raise RuntimeError("假棋盘：步数超过 300 万 ⇒ 大概率是死循环")
            return True
        return False

    def get_entity_type():
        if w.maze != None:
            tx = (w.treasure[0] + w.rx) % N
            ty = (w.treasure[1] + w.ry) % N
            if w.pos == (tx, ty):
                return "Treasure"
            if w.in_region(w.pos[0], w.pos[1]):
                return "Hedge"
        if w.pos in getattr(w, "bush", []):
            return "Bush"
        return None

    def measure():
        if w.maze == None:
            return None
        if not w.in_region(w.pos[0], w.pos[1]):
            return None
        return ((w.treasure[0] + w.rx) % N, (w.treasure[1] + w.ry) % N)

    def use_item(item, n=1):
        if item == "Weird_Substance":
            if w.maze == None:
                # 在灌木上长迷宫（建迷宫路径）
                if get_entity_type() == "Bush":
                    w.weird -= SUB_PER
                    w.build_maze()
                    return True
                return False
            if w.pos == measure():
                if w.relocations >= w.max_reloc:
                    return True                    # 耗尽：不给金币也不重定位
                w.gold += GOLD_PER
                w.relocations += 1
                w.relocate_treasure()
                return True
            return False
        return False

    def harvest():
        if w.maze != None:
            if w.pos == measure():
                w.gold += GOLD_PER
                return True
            if w.in_region(w.pos[0], w.pos[1]):
                w.maze = None                       # 非宝藏处收割 ⇒ 整座迷宫消失
                w.bush = []
                w.harvest_hedge += 1
                return True
        return False

    def plant(e):
        if e == "Bush":
            if w.maze == None:
                w.bush = [w.pos]
                return True
            return False
        return False

    def till():
        w.ground = "soil"
        return True

    def clear():
        w.maze = None
        w.pos = (0, 0)
        w.bush = []
        return None

    def num_items(it):
        if it == "Gold":
            return w.gold
        if it == "Weird_Substance":
            return w.weird
        if it == "Power":
            return w.power
        return 0

    def num_unlocked(u):
        return w.unlocks.get("mazes", 6)

    ns = {
        "North": 0, "East": 1, "South": 2, "West": 3,
        "Entities": type("E", (), {"Hedge": "Hedge", "Treasure": "Treasure", "Bush": "Bush"}),
        "Items": type("I", (), {"Gold": "Gold", "Weird_Substance": "Weird_Substance",
                                "Power": "Power"}),
        "Grounds": type("G", (), {"Soil": "soil", "Grassland": "grass"}),
        "Unlocks": type("U", (), {"Mazes": "mazes", "Leaderboard": "leaderboard"}),
        "get_pos_x": get_pos_x, "get_pos_y": get_pos_y, "move": move, "can_move": can_move,
        "get_entity_type": get_entity_type, "measure": measure, "use_item": use_item,
        "harvest": harvest, "plant": plant, "till": till, "clear": clear,
        "num_items": num_items, "num_unlocked": num_unlocked,
        "get_ground_type": lambda: w.ground,
        "get_world_size": lambda: N,
        # 假时钟：每次读都前进一点，否则 wait_s() / while get_time() < go_time 会死转
        "get_time": lambda: next(w.clock),
        "get_tick_count": lambda: 0,
        "max_drones": lambda: 32,
        "num_drones": lambda: 1,
        "spawn_drone": lambda f, *a: None,
        "wait_for": lambda d: 0,
        "print": lambda *a: w.log.append(" ".join(str(x) for x in a)),
        "quick_print": lambda *a: None,
        "len": len, "abs": abs, "min": min, "max": max,
        "append": lambda l, v: l.append(v),
        "remove": lambda l, v: l.remove(v),
        "range": range,
    }
    return ns


def load_script(ns):
    path = os.path.join(SAVE, "maze_gold2.py")
    src = open(path, encoding="utf-8").read()
    # 去掉最后的入口调用 main()，只加载函数与常量
    lines = src.split("\n")
    while lines and lines[-1].strip() == "":
        lines.pop()
    assert lines[-1].strip() == "main()", repr(lines[-1])
    src = "\n".join(lines[:-1])
    g = {"__name__": "maze_gold2_mock"}
    g.update(ns)
    exec(compile(src, path, "exec"), g)
    return g


def true_dist(w, src, dst):
    """在 mock 迷宫的真实图上做 BFS（含 drift 拆出来的环）⇒ 真实最短路"""
    if w.maze == None:
        return -1
    from collections import deque
    q = deque([src])
    d = {src: 0}
    while q:
        c = q.popleft()
        if c == dst:
            return d[c]
        for dx, dy in DIRS:
            n = ((c[0] + dx) % REG, (c[1] + dy) % REG)
            if n in w.maze[c] and n not in d:
                d[n] = d[c] + 1
                q.append(n)
    return -1


def run(seed=1, drift=0, region=(0, 0), treasures=150, verbose=True):
    """单架无人机在自己的 8x8 迷宫里连刷 N 次宝藏，返回统计"""
    w = Mock(seed=seed, region=region, drift=drift)
    ns = make_namespace(w)
    g = load_script(ns)
    explore = g["explore"]
    chase = g["chase"]
    build_maze = g["build_maze"]
    do_rebuild = g["do_rebuild"]
    # 建迷宫 + 探测 + 回位（= worker 的前半段）
    ax, ay = region
    ok = build_maze(ax, ay, 3)
    ex = explore(REG)
    g["HOMEX"][0] = ax
    g["HOMEY"][0] = ay
    g["OTHX"][0] = (ax + REG - 1) % N
    g["OTHY"][0] = (ay + REG - 1) % N
    if "home_fields" in g:
        g["DFIELD"][0] = 0
        g["home_fields"]()
    back = g["walk_home"](200) if "walk_home" in g else 0
    problems = []
    if ok != 1:
        problems.append("build_maze 返回 %s" % ok)
    if ex[0] != 1 or ex[1] != REG * REG:
        problems.append("explore ok=%s cells=%s" % (ex[0], ex[1]))
    if back < 0:
        problems.append("回位失败")
    # 逐次宝藏
    steps = []
    reb = 0
    per = []
    ideal1 = []      # 从「区域左上角那个家」出发的真实最短路
    ideal2 = []      # 两个家的较小值（= 2 架 + 分派的上界）
    homeB = (REG - 1, REG - 1)
    for t in range(treasures):
        before = w.moves
        tp = measure_or(w)
        r = chase(tp[0], tp[1])
        if r == 3 or r == 4:
            reb += 1
            if do_rebuild(ax, ay) == 0:
                problems.append("第 %d 次：重建失败" % t)
                break
        elif r != 1:
            problems.append("第 %d 次：chase 返回 %s" % (t, r))
            break
        steps.append(w.moves - before)
        per.append((r, w.relocations, len(steps)))
        tre = ((w.treasure[0]) % REG, (w.treasure[1]) % REG)
        d1 = true_dist(w, (0, 0), tre)
        d2 = true_dist(w, homeB, tre)
        ideal1.append(d1)
        if d1 < 0 or d2 < 0:
            ideal2.append(max(d1, d2))
        else:
            ideal2.append(min(d1, d2))
    if verbose:
        if steps:
            print("seed %d drift %d | 宝藏 %d 次 | **实走平均 %.2f 步**（最大 %d）| "
                  "家的真实最短路 %.2f | 两家的较小值 %.2f | 重建 %d"
                  % (seed, drift, len(steps), sum(steps) / len(steps), max(steps),
                     sum(ideal1) / len(ideal1), sum(ideal2) / len(ideal2), reb))
        else:
            print("seed %d drift %d region %s | **一次都没收到**" % (seed, drift, region))
    return steps, problems, w


def measure_or(w):
    if w.maze == None:
        return (0, 0)
    return ((w.treasure[0] + w.rx) % N, (w.treasure[1] + w.ry) % N)


def sim_two_drones(seed=1, drift=1, treasures=400, policy="dispatch"):
    """
    策略级模拟：两架无人机同处一座 8x8 迷宫，1 个 tick = 1 次移动（两架并行）。
    policy = "chase"    : 永远追（v34 的行为）
             "dispatch" : v1 的规则 —— 我当前位置离宝藏 <= 队友**家**离宝藏 才去（可能两架都不去）
             "home"     : **v2 的规则** —— 两家的距离场判据（对称，恰好一架去），
                          收完宝藏那架不回家（除非轮到它让位）
             "ideal"    : 下界 —— 每次都由"家更近"的那架从家里出发
    返回 (每次宝藏的平均 tick, 每座金币/分)
    """
    w = Mock(seed=seed, region=(0, 0), drift=drift)
    w.bush = []
    w.build_maze()
    homeA = (0, 0)
    homeB = (REG - 1, REG - 1)
    pos = [homeA, homeB]
    mode = ["idle", "idle"]          # idle / home / hunt
    tgt = [None, None]
    gold = 0
    ticks = 0
    collected = []
    for _ in range(treasures):
        tre = (w.treasure[0] % REG, w.treasure[1] % REG)
        # ---- 分派 ----
        if policy == "home":
            # v2：只比"家"的距离（对称 ⇒ 恰好一架去），收完那架不会被要求先回家
            da = true_dist(w, homeA, tre)
            db = true_dist(w, homeB, tre)
            for i in range(2):
                other = true_dist(w, homeB if i == 0 else homeA, tre)
                own = da if i == 0 else db
                if own < other or (own == other and i == 0):
                    mode[i] = "hunt"
                    tgt[i] = tre
                else:
                    mode[i] = "home"
                    tgt[i] = homeA if i == 0 else homeB
        elif policy == "dispatch":
            for i in range(2):
                other = 1 - i
                o = homeA if other == 0 else homeB
                dm = true_dist(w, pos[i], tre)
                do = true_dist(w, o, tre)
                if dm <= do:
                    mode[i] = "hunt"
                    tgt[i] = tre
                else:
                    mode[i] = "home"
                    tgt[i] = homeA if i == 0 else homeB
        else:
            mode[0] = "hunt"
            tgt[0] = tre
            mode[1] = "home"
            tgt[1] = homeB
        # 推进到有人拿到宝藏
        guard = 0
        while guard < 600:
            guard += 1
            ticks += 1
            hit = -1
            for i in range(2):
                if mode[i] == "hunt":
                    if pos[i] == tgt[i]:
                        hit = i
                        break
                    pos[i] = step_toward(w, pos[i], tgt[i])
            if hit >= 0:
                gold += GOLD_PER
                collected.append(guard)
                for _ in range(drift):
                    lx, ly = w.rng.randrange(REG), w.rng.randrange(REG)
                    dx, dy = DIRS[w.rng.randrange(4)]
                    nx, ny = lx + dx, ly + dy
                    if 0 <= nx < REG and 0 <= ny < REG:
                        w.maze[(lx, ly)].add((nx, ny))
                        w.maze[(nx, ny)].add((lx, ly))
                w.treasure = (w.rng.randrange(REG), w.rng.randrange(REG))
                # 收完那架：**不强制回家**（v2 行为）——下一轮分派再决定
                mode[hit] = "idle"
                tgt[hit] = pos[hit]
                break
            for i in range(2):
                if mode[i] == "home":
                    if pos[i] == tgt[i]:
                        mode[i] = "idle"
                    else:
                        pos[i] = step_toward(w, pos[i], tgt[i])
    avg = sum(collected) / len(collected)
    # 1 移动 = 200 tick / 6075 tick每秒 = 0.03292 秒
    # 每次宝藏还要付：分派与走位的语句（v2 已降到约 640 行 ≈ 0.08 秒）
    overhead = 2.5
    per_maze_gold_min = GOLD_PER * 60.0 / ((avg + overhead) * 0.03292)
    return avg, per_maze_gold_min


def step_toward(w, src, dst):
    """沿真实最短路走一步：BFS 的 par[x] 就是 x 朝 dst 的下一跳"""
    from collections import deque
    q = deque([dst])
    par = {dst: None}
    while q:
        c = q.popleft()
        for dx, dy in DIRS:
            n = ((c[0] + dx) % REG, (c[1] + dy) % REG)
            if n in w.maze[c] and n not in par:
                par[n] = c
                q.append(n)
    if src not in par:
        return src
    if par[src] is None:
        return src
    return par[src]


if __name__ == "__main__":
    print("=== maze_gold2 在假棋盘上的核心回归 ===")
    allprob = []
    for seed in (1, 2, 3):
        for drift in (0, 1, 2):
            steps, prob, w = run(seed=seed, drift=drift)
            allprob += prob
    print()
    print("=== 长跑（300 次复用上限 + 重建）===")
    steps, prob, w = run(seed=7, drift=1, treasures=700)
    allprob += prob
    print("    迷宫重建次数", w.built - 1, "| 被拆", w.harvest_hedge, "| gold", w.gold)
    print()
    print("=== 两架同区、不同分派策略的吞吐（1 移动 = 200 tick = 0.0329 秒）===")
    for policy in ("chase", "dispatch"):
        for drift in (0, 1):
            tot = 0.0
            totavg = 0.0
            for seed in (1, 2, 3, 4):
                avg, per_maze = sim_two_drones(seed=seed, drift=drift, policy=policy)
                tot += per_maze
                totavg += avg
            per_maze = tot / 4.0
            print("  policy %-8s drift %d | 平均走位 %.1f 步 | 每座 %.0f 金币/分 "
                  "| **16 座 = %.0f 金币/分**"
                  % (policy, drift, totavg / 4.0, per_maze, per_maze * 16))
    print()
    if allprob:
        print("!!! 可疑点", len(allprob))
        for p in allprob[:20]:
            print("   -", p)
    else:
        print("核心回归：**0 可疑点** ✓")
    sys.stdout.flush()
