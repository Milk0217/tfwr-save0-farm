# -*- coding: utf-8 -*-
# ============================================================
# farm_mock.py —— 用桌面 Python 假扮游戏，把 full_run（P0 档位调度版）**真跑一遍**
#
# 为什么必须有它：本项目已经栽过**四次**「静态检查全绿、跑起来什么都不干」的停滞
#   （v20 / v21 / v65 / v74，最近一次 world 3 卡死 237 轮）。而三个现有工具都查不出来：
#     * py_compile      只查 Python 语法
#     * gamelang.py     只查「这门语言不支持的写法」（三元、f-string…）
#     * audit_save0.py  只查未定义名字 / 重复声明 / 下标越界
#   逻辑性停滞（判据写反、区域算错、门槛永远够不着）**只有真跑才看得见** ✓
#
# 做法照搬 tools/maze_mock.py（已验证过的路子）：
#   把游戏 API 做成一批桩函数，**注入 Python 的 builtins**，再 exec 参赛脚本。
#   于是 `import util / budget / jobs / stage_*` 都能正常加载
#   （它们的模块顶层不读棋盘 —— 这正是 R4 那条铁律，本文件顺带把它验了 ✓）
#
# 假游戏会算的东西：生长时间、增量收成、报价与扣款、Expand 换棋盘（含「一行 → 方块」）。
# 假游戏**不**算的东西：power/水的加成、伴生倍率、南瓜合并、仙人掌排序、迷宫、恐龙。
#   ⇒ 它的用途是「P0 档位调度跑得通不通」，不是产量标定。
#
# 用法：python tools/farm_mock.py [模拟秒数上限，默认 3600]
# ============================================================
import builtins
import os
import sys
import traceback

REAL_PRINT = print
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
SAVE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

# ---- 实测口径（来自 2026-10-06 那跑的 output.txt 与 probe 记录）----
SIZES = [1, 3, 3, 4, 6, 8, 12, 16, 22, 32]      # Expand 等级 -> 边长
ROW_LV = 1                                       # lv1 = 一行（expand_2.md：下一级才不再是 row）
# ⚠ sunflower 的 7.0 是**游戏资产真值**（2026-11-02 用 UnityPy 读 resources.assets 的
#   FarmObjectSO：meanGrowTime=7.0、growTimeDeviationPercent=0.2；旧值 5.0 是估的 ✗）
GROW = {"bush": 4.0, "tree": 8.0, "carrot": 3.0, "pumpkin": 8.0, "sunflower": 7.0}
YIELD = {"bush": ("wood", 1), "tree": ("wood", 5), "carrot": ("carrot", 1)}
GRASS_REGROW = 0.5
CACTUS_GROW = 6.0
PUMPKIN_DEATH = 0.2        # 成熟那一刻 20% 概率变死瓜（docs/game/unlocks/pumpkins.md）
SUN_GATE = 10              # 场上至少 10 株 + 割花瓣最多那株 ⇒ 8 倍 power（sunflowers.md）
PETAL_LO = 7
PETAL_HI = 15

# 迷宫：墙位掩码（1=北 2=东 4=南 8=西），与 MZ_DIRS 的顺序无关，只看 move 的方向名
MZ_BIT = {"North": 1, "East": 2, "South": 4, "West": 8}
MZ_OPP = {"North": "South", "East": "West", "South": "North", "West": "East"}
MZ_DELTA = {"North": (0, 1), "East": (1, 0), "South": (0, -1), "West": (-1, 0)}


def gen_maze(rng, n):
    """生成 n x n 完美迷宫（递归回溯）⇒ 无环，右手法则必定能走到宝藏 ✓"""
    walls = {}
    for y in range(n):
        for x in range(n):
            walls[(x, y)] = 15
    seen = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        x, y = stack[-1]
        cand = []
        for d in ("North", "East", "South", "West"):
            dx, dy = MZ_DELTA[d]
            q = (x + dx, y + dy)
            if 0 <= q[0] < n and 0 <= q[1] < n and q not in seen:
                cand.append((q, d))
        if not cand:
            stack.pop()
            continue
        q, d = cand[rng.randrange(len(cand))]
        walls[(x, y)] &= ~MZ_BIT[d]
        walls[q] &= ~MZ_BIT[MZ_OPP[d]]
        seen.add(q)
        stack.append(q)
    return walls
# ⚠ pumpkin 的产量**不查 YIELD**：它按「连片方块」算（n^3 / n>=6 时 n*n*6），见 harvest()

UNLOCK_COST = {
    "expand": [{"hay": 30}, {"wood": 20}, {"wood": 30, "carrot": 20}, {"wood": 100, "carrot": 50},
               {"pumpkin": 1000}, {"pumpkin": 8000}, {"pumpkin": 64000},
               {"pumpkin": 512000}, {"pumpkin": 4100000}],
    "plant": [{"hay": 50}],
    # Speed / Grass 的后几级是**占位值**（真机只测到 lv1->2：Speed ≈ 100 hay、Grass ≈ 300 hay）
    "speed": [{"hay": 20}, {"hay": 100}, {"hay": 500}, {"hay": 2500}, {"hay": 12500}],
    "grass": [{}, {"hay": 300}, {"hay": 1500}, {"hay": 7500}, {"hay": 37500}],
    "carrots": [{"wood": 50}],
    "watering": [{"wood": 50}],
    "trees": [{"wood": 50, "carrot": 70}],
    "sunflowers": [{"carrot": 500}],
    "pumpkins": [{"wood": 500, "carrot": 200}],
    # 肥料 4 级（真机上限 4）——**后三级是占位价**，真机只测到 lv1 = wood 500
    "fertilizer": [{"wood": 500}, {"wood": 5000}, {"wood": 50000}, {"wood": 500000}],
    "polyculture": [{"pumpkin": 3000}],
    "cactus": [{"pumpkin": 5000}],
    "mazes": [{"weird_substance": 1000}],
    # Megafarm 5 级（真机上限 5）：lv1 = gold 2000 是实测值，后四级是占位价
    "megafarm": [{"gold": 2000}, {"gold": 8000}, {"gold": 32000},
                 {"gold": 128000}, {"gold": 512000}],
    "dinosaurs": [{"cactus": 2000}],
    "hats": [{"hay": 200}],   # 占位价（真机未测）
    "leaderboard": [{"bone": 2000000, "gold": 1000000}],
}
# ⚠ 种一株胡萝卜要多少 wood/hay **真值已由真机确认 = wood 1 + hay 1**
#   （2026-10-07 那跑的 [bg] 行：「种一株 Carrot 要 | wood 1 hay 1」）
PLANT_COST = {"carrot": {"wood": 1, "hay": 1}, "pumpkin": {"carrot": 1},
              "cactus": {"pumpkin": 2},
              "sunflower": {"carrot": 1}}
# 开局白送的等级（真机实测：Grass 白送 lv1 —— 所以 [bg] 打的 Grass 300 hay 是 lv1->2 的价）
START_LV = {"grass": 1}

TICK_ACTION = 0.5        # 一个动作 = 200 tick（timing.md：基础 400 tick/秒）
TICK_QUERY = 0.0025      # 一次查询 ≈ 1 tick
TICK_IDLE = 0.005        # 读一次时钟（= 空转一圈）也要花时间，否则 while get_time() 死转


class StopSim(Exception):
    pass


class NS:
    pass


Unlocks = NS()
Items = NS()
Entities = NS()
Grounds = NS()
Hats = NS()
Leaderboards = NS()
for _k in UNLOCK_COST:
    setattr(Unlocks, _k.capitalize(), _k)
setattr(Unlocks, "Leaderboard", "leaderboard")
for _k in ["hay", "wood", "carrot", "pumpkin", "cactus", "bone", "gold",
           "weird_substance", "water", "fertilizer", "power"]:
    setattr(Items, _k.capitalize(), _k)
setattr(Unlocks, "Hats", "hats")
setattr(Items, "Weird_Substance", "weird_substance")
setattr(Entities, "Apple", "apple")
setattr(Items, "Apple", "apple")
for _k in ["bush", "tree", "carrot", "pumpkin", "sunflower", "cactus", "grass", "hedge", "treasure"]:
    setattr(Entities, _k.capitalize(), _k)
class Hats:
    Dinosaur_Hat = "dinosaur_hat"
    Gray_Hat = "gray_hat"
    Straw_Hat = "straw_hat"


Grounds.Soil = "soil"
Grounds.Grassland = "grass"


class World:
    def __init__(self, limit, seed=20261007):
        self.limit = limit
        self.rng = __import__("random").Random(seed)   # 死瓜也要可复现
        self.clock = 0.0
        self.actions = 0
        self.queries = 0
        self.pos = (0, 0)
        self.drones = 1           # 含主机；Megafarm 每级翻倍上限
        self.lv = {}
        for k in UNLOCK_COST:
            self.lv[k] = 0
        for k in START_LV:
            self.lv[k] = START_LV[k]
        self.items = {"hay": 0, "wood": 0, "carrot": 0, "pumpkin": 0}
        self.ground = {}
        self.ent = {}
        self.planted = {}
        self.ready = {}
        self.rotten = {}          # 死瓜标记：种下的那一刻就掷骰（等价于成熟时掷）
        self.petals = {}          # 向日葵花瓣（种下即定，CONTEXT 的模型 b）
        self.infected = {}        # 被肥料感染的格子（收割时一半产量变 weird）
        self.comp = {}            # 格 -> (想要的物种, 想要的坐标)（polyculture）
        self.cactus = {}          # 格 -> 尺寸 0..9（仙人掌）
        self.comp_hits = 0        # 伴生命中次数（诊断用）
        self.fert_given = 0       # 已发过多少肥料（每 10 秒 1 个，每级翻倍）
        self.maze = None          # {"ox","oy","n","walls","treasure"}；None = 没有迷宫
        self.maze_built = 0       # 累计建了几座迷宫
        self.maze_torn = 0        # 累计抹掉几座
        self.gold_made = 0        # 累计迷宫金币
        self.cactus_made = 0      # 累计仙人掌
        self.bones_made = 0       # 累计骨头
        self.hat = None           # 当前帽子
        self.apple = None         # 苹果位置
        self.eaten = 0            # 已吃苹果数（= 尾巴长度）
        self.tail = []            # 尾巴格（最早的在前）
        self.pumpkin_made = 0     # **累计**产出的南瓜（花掉的也算 ⇒ 才能判「线到底通没通」）
        self.power_made = 0       # 累计产出的 power（同上）
        self.log = []
        self.stages = []          # 换档顺序
        self.buys = []            # 购买顺序
        self.rebuild_board()

    def set_comp(self, p, self_kind):
        # 随机给一个「不一样、且在 3 步以内」的伴生请求（polyculture.md）
        kinds = ["grass", "bush", "tree", "carrot"]
        cand = []
        for k in kinds:
            if k != self_kind:
                cand.append(k)
        dx = self.rng.randrange(-3, 4)
        dy = self.rng.randrange(-3, 4)
        if dx == 0 and dy == 0:
            dx = 1
        if abs(dx) + abs(dy) > 3:
            dy = 3 - abs(dx)
        self.comp[p] = (cand[self.rng.randrange(len(cand))],
                        ((p[0] + dx) % self.shape()[0], (p[1] + dy) % self.shape()[1]))

    # ---- 棋盘 ----
    # 真机实测（2026-10-07）：Expand lv1 的农场是**竖向一行**（x 只有 1 格、y 有 3 格），
    #   而 `get_world_size()` 仍然返回 **3**（不是 x 方向的长度）
    #   ⇒ 这两条都必须照实建模，否则 step_fwd() 的 North 分支根本没被跑到 ✗
    def shape(self):
        if self.lv["expand"] == ROW_LV:
            return 1, SIZES[ROW_LV]
        n = SIZES[self.lv["expand"]]
        return n, n

    def rebuild_board(self):
        # 真游戏里 Expand 会把农场换成新的（新地是草原）
        self.ground = {}
        self.ent = {}
        self.planted = {}
        self.ready = {}
        self.rotten = {}
        self.petals = {}
        self.infected = {}
        self.comp = {}
        self.cactus = {}
        self.tail = []
        dx, dy = self.shape()
        y = 0
        while y < dy:
            x = 0
            while x < dx:
                self.ground[(x, y)] = "grass"
                self.ent[(x, y)] = None
                self.ready[(x, y)] = 0.0
                x = x + 1
            y = y + 1
        self.pos = (0, 0)

    def speed_mul(self):
        return 2 ** self.lv["speed"]

    def charge(self, dt):
        self.clock = self.clock + dt / self.speed_mul()
        # 肥料自动到货：每 10 秒 1 个，每级翻倍（docs/game/unlocks/fertilizer.md）
        lv = self.lv.get("fertilizer", 0)
        if lv > 0:
            want = int(self.clock / 10.0) * (2 ** (lv - 1))
            if want > self.fert_given:
                self.items["fertilizer"] = self.items.get("fertilizer", 0) + (want - self.fert_given)
                self.fert_given = want
        if self.clock > self.limit:
            raise StopSim()

    def act(self):
        self.actions = self.actions + 1
        if self.actions > 4000000:
            raise StopSim()
        self.charge(TICK_ACTION)

    def query(self):
        self.queries = self.queries + 1
        self.charge(TICK_QUERY)


def afford(w, cost):
    for k in cost:
        if w.items.get(k, 0) < cost[k]:
            return False
    return True


def pay(w, cost):
    for k in cost:
        w.items[k] = w.items.get(k, 0) - cost[k]


def make_ns(w):
    def get_pos_x():
        return w.pos[0]

    def get_pos_y():
        return w.pos[1]

    def get_world_size():
        dx, dy = w.shape()
        if dx > dy:
            return dx
        return dy

    def in_maze():
        if w.maze == None:
            return False
        m = w.maze
        p = w.pos
        return m["ox"] <= p[0] < m["ox"] + m["n"] and m["oy"] <= p[1] < m["oy"] + m["n"]

    def move(d):
        if w.hat == "dinosaur_hat" and w.apple != None:
            dx, dy = w.shape()
            q = ((w.pos[0] + MZ_DELTA[d][0]) % dx, (w.pos[1] + MZ_DELTA[d][1]) % dy)
            if q in w.tail and q != (w.tail[0] if len(w.tail) > 0 else None):
                w.act()               # 撞尾巴：只返回 False（撞自己被罚，本项目不撞）
                return False
        if in_maze():
            m = w.maze
            lx = w.pos[0] - m["ox"]
            ly = w.pos[1] - m["oy"]
            if m["walls"][(lx, ly)] & MZ_BIT[d]:
                w.query()
                return False          # 撞墙：只返回 False，不报错（docs/game/unlocks/mazes.md）
        w.act()
        dx, dy = w.shape()
        x, y = w.pos
        if d == "North":
            y = (y + 1) % dy
        elif d == "South":
            y = (y - 1) % dy
        elif d == "East":
            x = (x + 1) % dx
        elif d == "West":
            x = (x - 1) % dx
        if False:
            w.tail.append(w.pos)
            if w.pos == w.apple:
                w.eaten = w.eaten + 1
                while len(w.tail) > w.eaten:
                    w.tail.pop(0)
                # 再随机放一颗（放在空格上）
                for _try in range(200):
                    q = (w.rng.randrange(dx), w.rng.randrange(dy))
                    if q not in w.tail:
                        w.apple = q
                        break
                w.nex_apple = w.apple
        w.pos = (x, y)
        if w.hat == "dinosaur_hat" and w.apple != None:
            w.tail.append(w.pos)
            if w.pos == w.apple:
                w.eaten = w.eaten + 1
                while len(w.tail) > w.eaten:
                    w.tail.pop(0)
                for _try in range(200):
                    q = (w.rng.randrange(dx), w.rng.randrange(dy))
                    if q not in w.tail:
                        w.apple = q
                        break
                w.nex_apple = w.apple
        return True

    def can_move(d):
        w.query()
        if in_maze():
            m = w.maze
            lx = w.pos[0] - m["ox"]
            ly = w.pos[1] - m["oy"]
            if m["walls"][(lx, ly)] & MZ_BIT[d]:
                return False
        return True

    def get_entity_type():
        w.query()
        p = w.pos
        # 恐龙帽的苹果：引擎靠「脚下是不是 Entities.Apple」来决定读 measure()（docs 第 20 行）
        #   ⚠ 漏了这一步 mock 就永远测不出引擎的寻路（它看不到苹果 ⇒ 只能瞎撞）✗
        if w.hat == "dinosaur_hat" and w.apple != None and p == w.apple:
            return "apple"
        if in_maze():
            m = w.maze
            if p == m["treasure"]:
                return "treasure"
            return "hedge"
        e = w.ent.get(p)
        if e == "pumpkin":
            if w.rotten.get(p):
                if w.clock - w.planted.get(p, 0.0) >= GROW["pumpkin"]:
                    return "dead_pumpkin"      # 成熟那一刻才发现死了（等价于成熟时掷骰）
        return e

    def get_ground_type():
        w.query()
        return w.ground.get(w.pos, "grass")

    def is_mature(p):
        e = w.ent.get(p)
        if e == None:
            return False
        return w.clock - w.planted.get(p, 0.0) >= GROW[e]

    def is_live_pumpkin(p):
        if w.ent.get(p) != "pumpkin":
            return False
        if w.rotten.get(p):
            return False
        return is_mature(p)

    def merge_tiles(p):
        # 连通块 = 所有「活着且成熟」的南瓜（种子 docs/game/unlocks/pumpkins.md：
        #   同方块全熟才会合并 ⇒ 收割一刀收整片）
        dx, dy = w.shape()
        seen = [p]
        stack = [p]
        while len(stack) > 0:
            q = stack.pop()
            for d in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                r = ((q[0] + d[0]) % dx, (q[1] + d[1]) % dy)
                if r in seen:
                    continue
                if is_live_pumpkin(r):
                    seen.append(r)
                    stack.append(r)
        return seen

    def can_harvest():
        w.query()
        p = w.pos
        e = w.ent.get(p)
        if e == "cactus":
            return w.clock - w.planted.get(p, 0.0) >= CACTUS_GROW
        if e == None:
            if w.ground.get(p) == "soil":
                return False
            return w.clock >= w.ready.get(p, 0.0)
        if e == "pumpkin":
            return is_live_pumpkin(p)
        if e == "dead_pumpkin":
            return False
        return w.clock - w.planted.get(p, 0.0) >= GROW[e]

    def use_item(item, n=1):
        w.query()
        if item == "weird_substance":
            # docs/game/unlocks/mazes.md：在**灌木**上灌 n 份 ⇒ 长出 n x n 迷宫（锚点=脚下）
            if in_maze():
                # 站在宝藏上再灌 = 收下金币 + 随机重定位（本项目走重建路线，用不到）
                m = w.maze
                if w.pos == m["treasure"]:
                    if w.items.get("weird_substance", 0) < n:
                        return False
                    w.items["weird_substance"] -= n
                    w.items["gold"] = w.items.get("gold", 0) + m["n"] * m["n"]
                    m["treasure"] = (m["ox"] + w.rng.randrange(m["n"]),
                                     m["oy"] + w.rng.randrange(m["n"]))
                    return True
                return False
            if w.ent.get(w.pos) != "bush":
                return False
            if w.items.get("weird_substance", 0) < n:
                return False
            w.items["weird_substance"] = w.items.get("weird_substance", 0) - n
            n2 = int(n)
            walls = gen_maze(w.rng, n2)
            w.maze = {"ox": w.pos[0], "oy": w.pos[1], "n": n2, "walls": walls,
                      "treasure": (w.pos[0] + w.rng.randrange(n2), w.pos[1] + w.rng.randrange(n2))}
            w.ent[w.pos] = None       # 灌木被迷宫取代
            w.maze_built += 1
            return True
        # 肥料：感染的植物收割时一半产量变 weird（docs/game/unlocks/fertilizer.md）
        if item != "fertilizer":
            return False
        if w.items.get("fertilizer", 0) <= 0:
            return False
        p = w.pos
        if w.ent.get(p) == None:
            return False
        w.items["fertilizer"] = w.items.get("fertilizer", 0) - 1
        w.infected[p] = True
        return True

    def get_companion():
        # 伴生请求：(想要的物种, 想要的坐标)。只有 草/灌木/树/胡萝卜 有偏好（polyculture.md）
        w.query()
        return w.comp.get(w.pos)

    def measure(*a):
        # 迷宫里 measure() 返回**宝藏坐标**（mazes.md）；仙人掌返回尺寸（cactus.md）
        w.query()
        if len(a) > 0:
            dx, dy = MZ_DELTA[a[0]]
            q = ((w.pos[0] + dx) % w.shape()[0], (w.pos[1] + dy) % w.shape()[1])
            if q in w.cactus:
                return w.cactus[q]
            return None
        if w.pos in w.cactus:
            return w.cactus[w.pos]
        if w.hat == "dinosaur_hat" and w.pos == w.apple:
            return w.nex_apple
        if in_maze():
            return w.maze["treasure"]
        p = w.pos
        if w.ent.get(p) == "sunflower":
            return w.petals.get(p, PETAL_LO)
        return None

    def sun_count_and_max():
        # 场上活着的向日葵数与最大花瓣（未成熟的也算 —— CONTEXT.md 的 Petal Gate 口径）
        n = 0
        mx = -1
        for q in w.ent:
            if w.ent.get(q) == "sunflower":
                n = n + 1
                if w.petals.get(q, PETAL_LO) > mx:
                    mx = w.petals.get(q, PETAL_LO)
        return n, mx

    def swap(d):
        w.query()
        dx, dy = MZ_DELTA[d]
        q = ((w.pos[0] + dx) % w.shape()[0], (w.pos[1] + dy) % w.shape()[1])
        if w.pos not in w.cactus or q not in w.cactus:
            return False
        a = w.cactus[w.pos]
        w.cactus[w.pos] = w.cactus[q]
        w.cactus[q] = a
        w.act()
        return True

    def cactus_sorted_square(x0, y0, n):
        # 文档的「有序」= N/E 邻居 >= 自己、S/W <= 自己（等价于行、列都朝东北递增）
        i = 0
        while i < n:
            j = 0
            while j < n:
                if (x0 + i, y0 + j) not in w.cactus:
                    return False
                if i + 1 < n and (x0 + i + 1, y0 + j) in w.cactus:
                    if w.cactus[(x0 + i + 1, y0 + j)] < w.cactus[(x0 + i, y0 + j)]:
                        return False
                if j + 1 < n and (x0 + i, y0 + j + 1) in w.cactus:
                    if w.cactus[(x0 + i, y0 + j + 1)] < w.cactus[(x0 + i, y0 + j)]:
                        return False
                j = j + 1
            i = i + 1
        return True

    def harvest():
        p = w.pos
        # 仙人掌：找**包含脚下的最大有序方块**，一刀连锁收掉 n^2 x 等级倍率
        if p in w.cactus:
            ws2 = w.shape()[0]
            best = 0
            bx = 0
            by = 0
            n = ws2
            while n >= 1:
                x0 = 0
                while x0 <= ws2 - n:
                    y0 = 0
                    while y0 <= ws2 - n:
                        if x0 <= p[0] < x0 + n and y0 <= p[1] < y0 + n:
                            if cactus_sorted_square(x0, y0, n):
                                if n > best:
                                    best = n
                                    bx = x0
                                    by = y0
                        y0 = y0 + 1
                    x0 = x0 + 1
                n = n - 1
            if best > 0:
                w.act()
                # docs 原文：收下 n 株就给 n^2 —— 而 n = side^2 ⇒ 一刀 = side^4 x 等级倍率
                gain = (best * best) * (best * best) * (2 ** max(0, w.lv.get("cactus", 1) - 1))
                i = 0
                while i < best:
                    j = 0
                    while j < best:
                        w.cactus.pop((bx + i, by + j), None)
                        w.ent.pop((bx + i, by + j), None)     # ⚠ 必须连 ent 一起清！
                        j = j + 1
                    i = i + 1
                w.items["cactus"] = w.items.get("cactus", 0) + gain
                w.cactus_made += gain
                return True
        if in_maze():
            m = w.maze
            w.act()
            if p == m["treasure"]:
                w.items["gold"] = w.items.get("gold", 0) + m["n"] * m["n"]
                w.gold_made += m["n"] * m["n"]
                return True
            w.maze = None                 # 非宝藏处收割 ⇒ 整座迷宫消失（docs 原文）
            w.maze_torn += 1
            return True
        e = w.ent.get(p)
        # 死瓜：收割**不产出**，但会把它清掉（plant_block 就是靠这一手清死瓜的）
        if e == "pumpkin":
            if w.rotten.get(p):
                if w.clock - w.planted.get(p, 0.0) >= GROW["pumpkin"]:
                    w.act()
                    w.ent[p] = None
                    w.rotten[p] = False
                    return True
        if not can_harvest():
            return False
        w.act()
        if e == None:
            w.items["hay"] = w.items.get("hay", 0) + 1
            w.ready[p] = w.clock + GRASS_REGROW
            return True
        if e == "pumpkin":
            tiles = merge_tiles(p)
            xs = [t[0] for t in tiles]
            ys = [t[1] for t in tiles]
            n = max(xs) - min(xs) + 1
            if n == max(ys) - min(ys) + 1 and len(tiles) == n * n:
                if n >= 6:
                    gain = n * n * 6
                else:
                    gain = n * n * n
            else:
                gain = 1                       # 没成形：单株只值 1 个
            i = 0
            while i < len(tiles):
                t = tiles[i]
                w.ent[t] = None
                w.rotten[t] = False
                if w.ground.get(t) == "soil":
                    w.ready[t] = 1e18
                else:
                    w.ready[t] = w.clock + GRASS_REGROW
                i = i + 1
            w.items["pumpkin"] = w.items.get("pumpkin", 0) + gain
            w.pumpkin_made += gain
            return True
        if e == "sunflower":
            # 依据 docs/game/unlocks/sunflowers.md：场上 >= 10 株且割的是花瓣最多那株 ⇒ 8 倍
            n, mx = sun_count_and_max()
            gain = 1
            if n >= SUN_GATE:
                if w.petals.get(p, PETAL_LO) >= mx:
                    gain = 8
            w.items["power"] = w.items.get("power", 0) + gain
            w.power_made = w.power_made + gain
            w.ent[p] = None
            w.petals[p] = 0
            if w.ground.get(p) == "soil":
                w.ready[p] = 1e18
            else:
                w.ready[p] = w.clock + GRASS_REGROW
            return True
        it = YIELD[e][0]
        amt = YIELD[e][1]
        # 伴生加成：请求格上种着它要的物种 ⇒ 产量 × 5·2^等级（polyculture.md）
        cp = w.comp.get(p)
        if cp != None:
            if w.ent.get(cp[1]) == cp[0]:
                amt = amt * 5 * (2 ** w.lv.get("polyculture", 0))
                w.comp_hits += 1
        # 感染的植物：**一半产量变 weird**（fertilizer.md）—— 所以产量倍率直接放大 weird ✓
        if w.infected.get(p):
            w.items["weird_substance"] = w.items.get("weird_substance", 0) + amt // 2
            amt = amt - amt // 2
            w.infected[p] = False
        w.items[it] = w.items.get(it, 0) + amt
        w.ent[p] = None
        if w.ground.get(p) == "soil":
            w.ready[p] = 1e18
        else:
            w.ready[p] = w.clock + GRASS_REGROW
        return True

    def plant(e):
        w.act()
        p = w.pos
        if e == "cactus":
            if w.lv.get("cactus", 0) <= 0:
                return False
            if w.ground.get(p) != "soil":
                return False
            if not afford(w, PLANT_COST["cactus"]):
                return False
            pay(w, PLANT_COST["cactus"])
            w.ent[p] = "cactus"
            w.planted[p] = w.clock
            w.cactus[p] = w.rng.randrange(0, 10)
            return True
        if e == "bush" or e == "tree":
            if w.lv["plant"] <= 0:
                return False
            if e == "tree" and w.lv["trees"] <= 0:
                return False
            w.ent[p] = e
            w.planted[p] = w.clock
            w.set_comp(p, e)
            return True
        if e == "carrot":
            if w.lv["carrots"] <= 0:
                return False
            if w.ground.get(p) != "soil":
                return False
            if not afford(w, PLANT_COST["carrot"]):
                return False
            pay(w, PLANT_COST["carrot"])
            w.ent[p] = "carrot"
            w.planted[p] = w.clock
            w.set_comp(p, "carrot")
            return True
        if e == "sunflower":
            if w.lv["sunflowers"] <= 0:
                return False
            if w.ground.get(p) != "soil":
                return False
            if not afford(w, PLANT_COST["sunflower"]):
                return False
            pay(w, PLANT_COST["sunflower"])
            w.ent[p] = "sunflower"
            w.planted[p] = w.clock
            w.petals[p] = w.rng.randrange(PETAL_LO, PETAL_HI + 1)   # 花瓣种下即定（模型 b）
            return True
        if e == "pumpkin":
            if w.lv["pumpkins"] <= 0:
                return False
            if w.ground.get(p) != "soil":
                return False
            if not afford(w, PLANT_COST["pumpkin"]):
                return False
            pay(w, PLANT_COST["pumpkin"])
            w.ent[p] = "pumpkin"
            w.planted[p] = w.clock
            w.rotten[p] = w.rng.random() < PUMPKIN_DEATH
            return True
        return False

    def till():
        w.act()
        p = w.pos
        if w.ground.get(p) == "soil":
            w.ground[p] = "grass"
        else:
            w.ground[p] = "soil"
        return True

    def clear():
        w.act()
        w.rebuild_board()

    def num_items(it):
        w.query()
        return w.items.get(it, 0)

    def num_unlocked(u):
        w.query()
        if u in w.lv:
            return w.lv[u]
        return 1

    def get_cost(t):
        w.query()
        if t in w.lv:
            lv = w.lv[t]
            seq = UNLOCK_COST[t]
            if lv >= len(seq):
                return None
            return dict(seq[lv])
        if t == "carrot":
            return dict(PLANT_COST["carrot"])
        if t == "pumpkin":
            return dict(PLANT_COST["pumpkin"])
        return {}

    def unlock(t):
        w.query()
        if t in w.lv:
            lv = w.lv[t]
            seq = UNLOCK_COST[t]
            if lv >= len(seq):
                return False
            if not afford(w, seq[lv]):
                return False
            pay(w, seq[lv])
            w.lv[t] = lv + 1
            w.buys.append(t)
            if t == "expand":
                w.rebuild_board()
            return True
        return False

    def spawn_drone(f, *a):
        # 假游戏是单线程：**同步**把这一班跑完 —— 副机本来就是「有限班次」（R2）⇒ 语义等价 ✓
        # 跑的时候 num_drones 会 +1，于是主机的 R1 闸门（键只在无副机时变）也照实生效 ✓
        cap = 2 ** w.lv.get("megafarm", 0)
        if w.drones >= cap:
            return None
        w.drones += 1
        try:
            f(*a)
        finally:
            w.drones -= 1
        return "drone_handle"

    def change_hat(h):
        w.query()
        if h == "dinosaur_hat":
            if w.lv.get("dinosaurs", 0) <= 0:
                return False
            if w.hat == "dinosaur_hat":
                return False
            if w.items.get("cactus", 0) < 2:
                return False
            w.items["cactus"] = w.items.get("cactus", 0) - 2
            w.hat = h
            w.eaten = 0
            w.tail = [w.pos]
            w.apple = w.pos
            w.nex_apple = w.pos
            return True
        if w.hat == "dinosaur_hat":
            n = len(w.tail) + w.eaten - len(w.tail)     # 尾巴长度 = 吃掉的苹果数
            n = w.eaten
            w.items["bone"] = w.items.get("bone", 0) + n * n * (2 ** max(0, w.lv.get("dinosaurs", 1) - 1))
            w.bones_made += n * n * (2 ** max(0, w.lv.get("dinosaurs", 1) - 1))
            w.hat = None
            w.tail = []
            w.apple = None
        w.hat = h
        return True

    def num_drones():
        return w.drones

    def max_drones():
        return 2 ** w.lv.get("megafarm", 0)

    def get_time():
        w.charge(TICK_IDLE)
        return w.clock

    ns = {
        "North": "North", "East": "East", "South": "South", "West": "West",
        "True": True, "False": False, "None": None,
        "Unlocks": Unlocks, "Items": Items, "Entities": Entities,
        "Grounds": Grounds, "Hats": Hats, "Leaderboards": Leaderboards,
        "get_pos_x": get_pos_x, "get_pos_y": get_pos_y, "get_world_size": get_world_size,
        "move": move, "can_move": can_move, "get_entity_type": get_entity_type,
        "get_ground_type": get_ground_type, "can_harvest": can_harvest,
        "harvest": harvest, "plant": plant, "till": till, "clear": clear,
        "num_items": num_items, "num_unlocked": num_unlocked,
        "get_cost": get_cost, "unlock": unlock, "get_time": get_time,
        "get_tick_count": lambda: int(w.clock * 400),
        "max_drones": max_drones,
        "num_drones": num_drones,
        "spawn_drone": spawn_drone,
        "wait_for": lambda d: 0,
        "has_finished": lambda d: True,
        "measure": measure,
        "get_companion": lambda: None,
        "use_item": use_item,
        "swap": swap,
        "change_hat": change_hat,
        "do_a_flip": lambda: None,
        "trade": lambda *a: False,
        "set_world_size": lambda n: None,
        "print": lambda *a: w.log.append(" ".join(str(x) for x in a)),
        "quick_print": lambda *a: w.log.append(" ".join(str(x) for x in a)),
        "str": str, "len": len, "range": range, "abs": abs, "min": min, "max": max,
        "round": round, "append": lambda l, v: l.append(v),
        "remove": lambda l, v: l.remove(v), "pop": lambda l, i=-1: l.pop(i),
        "insert": lambda l, i, v: l.insert(i, v),
    }
    return ns


def report(w):
    # 换档顺序从日志里读（w.stages 不会被参赛脚本写入 —— 它是另一个进程里的对象）
    stages = []
    for line in w.log:
        if line.startswith("[st] 换档"):
            stages.append(line)
    REAL_PRINT("=" * 72)
    REAL_PRINT("模拟结束：游戏内时间 %.1f 秒 | 动作 %d | 查询 %d" % (w.clock, w.actions, w.queries))
    REAL_PRINT("换档次数：", len(stages))
    for s in stages:
        REAL_PRINT("    ", s)
    REAL_PRINT("购买顺序：", " ".join(w.buys))
    REAL_PRINT("最终物品：", dict((k, v) for k, v in w.items.items() if v))
    REAL_PRINT("解锁等级：", dict((k, v) for k, v in w.lv.items() if v))
    REAL_PRINT("-" * 72)
    for line in w.log:
        REAL_PRINT("   ", line)
    REAL_PRINT("-" * 72)
    names = " ".join(stages)
    ok = 0
    bad = 0
    if "w1" in names:
        REAL_PRINT("PASS 1x1 档位进过")
        ok += 1
    else:
        REAL_PRINT("FAIL 1x1 档位没进过 —— 开局就错了")
        bad += 1
    if "row" in names:
        REAL_PRINT("PASS 一行档位（Expand lv1）进过 => 形状探测生效")
        ok += 1
    else:
        REAL_PRINT("WARN 没进过一行档位：可能 Expand lv1 的农场本来就是方块（假设要复核）")
    if "w3" in names:
        REAL_PRINT("PASS 3x3 档位进过")
        ok += 1
    else:
        REAL_PRINT("FAIL 3x3 档位没进过 —— 没走到 Expand lv2")
        bad += 1
    if "w4" in names:
        REAL_PRINT("PASS 4x4 档位进过（P2）")
        ok += 1
    else:
        REAL_PRINT("WARN 4x4 档位没进过 —— 还没买到 Expand lv3")
    if "w6" in names:
        REAL_PRINT("PASS 6x6 档位进过（P2，含南瓜方块）")
        ok += 1
    else:
        REAL_PRINT("WARN 6x6 档位没进过 —— 还没买到 Expand lv4")
    if "w8" in names:
        REAL_PRINT("PASS 8x8 档位进过（P5，含向日葵带）")
        ok += 1
    else:
        REAL_PRINT("WARN 8x8 档位没进过 —— 还没买到 Expand lv5")
    if "w12" in names:
        REAL_PRINT("PASS 12x12 档位进过（P5 主战场，方块 6x6 满倍率）")
        ok += 1
    else:
        REAL_PRINT("WARN 12x12 档位没进过 —— 还没买到 Expand lv6")
    if "w16" in names:
        REAL_PRINT("PASS 16x16 档位进过（末档：方块 + 迷宫区 + 向日葵带）")
        ok += 1
    else:
        REAL_PRINT("WARN 16x16 档位没进过 —— 还没买到 Expand lv7")
    if w.items.get("weird_substance", 0) > 0:
        REAL_PRINT("PASS 奇异物质线通：现存", w.items.get("weird_substance"),
                   "（喂树 → 感染 → 收割一半变 weird）")
        ok += 1
    else:
        REAL_PRINT("WARN 奇异物质仍为 0（Fertilizer 未解锁或没有树列）")
    if w.comp_hits > 0:
        REAL_PRINT("PASS 混合种植（Polyculture）真的生效：伴生命中", w.comp_hits, "次")
        ok += 1
    else:
        REAL_PRINT("WARN 一次伴生都没命中（Polyculture 未解锁 / 只对树做 / 请求落在区外）")
    if w.maze_built > 0:
        REAL_PRINT("PASS 迷宫金币线通：建了", w.maze_built, "座、抹掉", w.maze_torn,
                   "座、累计金币", w.gold_made)
        ok += 1
    else:
        REAL_PRINT("WARN 迷宫一座都没建成（Mazes 未解锁 / 区域不对 / 物质不足）")
    if w.lv.get("megafarm", 0) > 0:
        REAL_PRINT("PASS Megafarm 到手 ⇒ 下次真机跑就会有副机了")
        ok += 1
    else:
        REAL_PRINT("WARN Megafarm 还没买到（金币不够 2000）")
    if w.power_made > 0:
        REAL_PRINT("PASS power 线通：累计产出", w.power_made)
        ok += 1
    else:
        REAL_PRINT("WARN power 累计为 0（Sunflowers 未解锁或时长不够）")
    if w.pumpkin_made > 0:
        REAL_PRINT("PASS 南瓜线通：**累计**产出", w.pumpkin_made,
                   "（现存", w.items.get("pumpkin", 0), "—— 花在 Expand 上的也算通）")
        ok += 1
    else:
        REAL_PRINT("WARN 南瓜累计产出仍为 0（Pumpkins 未解锁或时长不够）")
    if w.items.get("wood", 0) > 0 and w.items.get("hay", 0) > 0:
        REAL_PRINT("PASS wood/hay 都在涨（v75 的停滞判据就是这条）| wood",
                   w.items.get("wood"), "hay", w.items.get("hay"))
        ok += 1
    else:
        REAL_PRINT("FAIL 没有木/草收入 —— 就是 v75 那次停滞")
        bad += 1
    if w.items.get("carrot", 0) > 0:
        REAL_PRINT("PASS 胡萝卜线产出了", w.items.get("carrot"))
        ok += 1
    else:
        REAL_PRINT("WARN 胡萝卜还没产出（可能是模拟时长不够）")
    stall = 0
    for line in w.log:
        if "停滞看门狗" in line:
            stall += 1
    if stall == 0:
        REAL_PRINT("PASS 停滞看门狗没有报警")
        ok += 1
    else:
        REAL_PRINT("FAIL 停滞看门狗报警了", stall, "次")
        bad += 1
    REAL_PRINT("=" * 72)
    REAL_PRINT("结果：PASS", ok, "/ FAIL", bad)
    return bad


def main():
    limit = 3600.0
    if len(sys.argv) > 1:
        limit = float(sys.argv[1])
    w = World(limit)
    ns = make_ns(w)
    # 注入 builtins：游戏里这些就是全局可用的内建（含 Unlocks / Items 这些枚举）
    for k in ns:
        setattr(builtins, k, ns[k])
    for name in ["util", "budget", "jobs", "stage_w1", "stage_row", "stage_w3", "full_run"]:
        sys.modules.pop(name, None)
    if SAVE not in sys.path:
        sys.path.insert(0, SAVE)
    path = os.path.join(SAVE, "full_run.py")
    src = open(path, encoding="utf-8").read()
    try:
        exec(compile(src, path, "exec"), {"__name__": "__main__"})
    except StopSim:
        w.log.append("[mock] 到达模拟时长上限 %s 秒，停在这里" % limit)
    except Exception:
        # 注意：builtins.print 已被替换成游戏的 print（它不认 file= 参数）
        # ⇒ 这里必须用 REAL_PRINT + format_exc()，否则报错处理本身又抛一个错 ✗
        REAL_PRINT("!! 参赛脚本抛异常：")
        REAL_PRINT(traceback.format_exc())
        w.log.append("[mock] 脚本抛异常，见上方 traceback")
    return report(w)


if __name__ == "__main__":
    sys.exit(main())
