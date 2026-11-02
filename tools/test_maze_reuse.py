# -*- coding: utf-8 -*-
# ============================================================
# test_maze_reuse.py —— 迷宫「复用」与「寻宝走路」的 mock 回归
#
# ⚠⚠ 本 mock 的语义**全部来自 2026-11-01 对游戏本体 `Core.dll` 的反编译**
#     （`ilspycmd`，见 jobs.py 里 MZ_REUSE_MAX 上面那段长注释），不是猜的：
#   ① `Treasure.Harvest` → `HedgePlant.Harvest` → **RemoveMaze()**：
#      `harvest()` 在**宝藏上** = 收金币 + **抹掉整座迷宫**；
#      在**非宝藏树篱**上 harvest 同样抹整座（不给金币）。
#      ⇒ 旧实现「先 harvest 收第一颗、再 use_item 想复用」**结构性不可能成功** ✗✗
#      （真机症状：每座只吃 1~2 颗、`复用第` 长期为 0 ✓）
#   ② 站在宝藏上 `use_item(Items.Weird_Substance, sub)` → `RepositionTreasure()`：
#      立刻收金币（= 面积 × 2^(Mazes lv−1)）+ 200 tick 后把宝藏**随机搬到迷宫内另一格**，
#      并随机拆掉几面墙（`CompleteRepositioning` 里对 (i+j) 偶数格、每个方向 0.2% 概率
#      ⇒ 每次重定位期望拆约 0.26 面；8x8 的 49 面内墙约 190 次复用就拆光 ⇒ 越刷越短 ✓）
#      ⇒ 这才是"复用"；上限 **300** 次（`treasureFactor` 1→301）
#   ③ 复用上限过后 `use_item` 不再给金币也不再搬 ⇒ 最后用 `harvest()` 收**第 301 颗**
#      并抹掉迷宫（官方排行榜口径：`Maze = 301 × 32,768` ✓）
#   ④ `GenerateHedgeMaze`：`lowLeftCorner = max(0, pos - size/2)` ⇒ 迷宫以无人机为**中心**长出来
#   ⑤ `plant(Bush)` 在**已有植物**的格上**静默失败**（无 warning）；随后 `use_item(weird)` 会把
#      脚下的 Grass 当 Growable 做 ToggleWeird（施肥）⇒ **物质白烧、没有迷宫** ✗
#      （这就是真机 51 次 `迷宫没长出来（脚下是 Entities.Grass）` 的根因 ✓）
#
# 测试内容：
#   (a) 整座寿命+耗尽分支：只建 **1 次**迷宫 → 连续收 **301 颗**（300 次复用 + 收尾）→ 只拆 1 次
#   (b) 第二次建迷宫：地上是 Grass 时也必须种得上（覆盖"迷宫没长出来"的根因）；物质只花 1 份
#   (c) 走到宝藏途中**注入 `move()` 失败**（模拟"墙被拆后地图过期/现实与地图不符"）
#       ⇒ 走路必须自愈（记墙+重算），并且复用继续 ≥ 5 颗 ✓
#   (d) 迷宫中途被别的无人机抹掉（measure()=None）⇒ 走路安全返回 0，不崩
#   (e) 地图整张过期（迷宫被重建过、墙完全变了）⇒ 重探一次后又能走到 ✓
#   (f) 生产参数 MZ_REUSE_MAX=300 的正常路径（循环自然结束 → 走到新宝藏收第 301 颗）
#   (g) maze_worker 班次有界（MZ_SHIFT_SEC）+ 收尾必抹迷宫（不能留场 ✗）
#   (h) 布局门禁：stage_w16 的轮作区必须与迷宫区**不相交**（用 stage_w16.lands()/assign(8) 机械验）
#   (i) util.go_to：能走环形近端（不穿迷宫）；目标在封闭迷宫内时**有界放弃**（不再永久卡死）
# ============================================================
import builtins
import contextlib
import io
import os
import random
import sys

SAVE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
SIDE = 8
X0 = 6
Y0 = 0
LV = 3                     # Mazes 等级 3 ⇒ sub = 8*4 = 32，per = 64*4 = 256

DIRS = ["North", "East", "South", "West"]
BIT = {"North": 1, "East": 2, "South": 4, "West": 8}
OPP = {"North": "South", "East": "West", "South": "North", "West": "East"}
DELTA = {"North": (0, 1), "East": (1, 0), "South": (0, -1), "West": (-1, 0)}

MAX_RELOC = 300            # 源码 MAX_TREASURE_FACTOR = 301 ⇒ 最多 300 次重定位
RELOC_TICKS = 25           # 模拟 200 tick 重定位定时器：use_item 返回后还要过若干 tick 才可见


class MazeWorld:
    """只实现 jobs.py 迷宫段用到的游戏 API；语义按 Core.dll 反编译结果建模。"""

    def __init__(self, ws=16, x0=X0, y0=Y0, side=SIDE, lv=LV, seed=7):
        self.rng = random.Random(seed)
        self.ws = ws
        self.x0 = x0
        self.y0 = y0
        self.side = side
        self.lv = lv
        self.pos = [0, 0]
        self.maze = None            # {"walls": {(lx,ly): mask}}
        self.treasure = None        # 宝藏本地坐标 (lx,ly)
        self.pending = 0            # 重定位剩余 tick（>0 ⇒ 宝藏还显示在旧格）
        self.gold = 0
        self.weird = 10 ** 6
        self.relocations = 0
        self.built = 0
        self.torn = 0
        self.entity = None          # 迷宫外的实体（None / bush / grass / 作物）
        self.ground = "grassland"   # 当前格地面：grassland / soil（till 切换）
        self.move_fail_next = 0
        self.move_calls = 0
        self.move_inject_every = 0  # >0 ⇒ 每 N 次 move 注入一次失败
        self.collect = []           # [(kind, built_id, gold)]：每次真正收到金币
        self.now = 0.0
        self.tick_sec = 0.0         # 每次游戏 API 调用推进的虚拟时间（>0 才能测班次时间上限）

    # ---------- 迷宫模型 ----------
    def _gen_maze(self, n):
        walls = {}
        for y in range(n):
            for x in range(n):
                walls[(x, y)] = 15      # 四向都是墙
        seen = {(0, 0)}
        stack = [(0, 0)]
        while stack:
            x, y = stack[-1]
            cand = []
            for d in DIRS:
                dx, dy = DELTA[d]
                q = (x + dx, y + dy)
                if 0 <= q[0] < n and 0 <= q[1] < n and q not in seen:
                    cand.append((q, d))
            if not cand:
                stack.pop()
                continue
            q, d = cand[self.rng.randrange(len(cand))]
            walls[(x, y)] &= ~BIT[d]
            walls[q] &= ~BIT[OPP[d]]
            seen.add(q)
            stack.append(q)
        return walls

    def per(self):
        return self.side * self.side * (1 << (self.lv - 1))

    def sub(self):
        return self.side * (1 << (self.lv - 1))

    def in_maze(self):
        if self.maze is None:
            return False
        x, y = self.pos
        return self.x0 <= x < self.x0 + self.side and self.y0 <= y < self.y0 + self.side

    def _local(self):
        return (self.pos[0] - self.x0, self.pos[1] - self.y0)

    def _abs_treasure(self):
        return (self.x0 + self.treasure[0], self.y0 + self.treasure[1])

    def _tick(self):
        if self.tick_sec > 0.0:
            self.now += self.tick_sec
        if self.pending > 0:
            self.pending -= 1
            if self.pending == 0:
                self._finish_relocate()

    def _finish_relocate(self):
        # CompleteRepositioning：宝藏搬到 nextPos，并把若干墙拆掉
        n = self.side
        for i in range(n):
            for j in range(n):
                if (i + j) % 2 == 1:
                    continue
                for d in DIRS:
                    if self.rng.random() > 0.002:
                        continue
                    dx, dy = DELTA[d]
                    kx = i + dx
                    ky = j + dy
                    if 0 <= kx < n and 0 <= ky < n:
                        self.maze["walls"][(i, j)] &= ~BIT[d]
                        self.maze["walls"][(kx, ky)] &= ~BIT[OPP[d]]
        old = self.treasure
        new = (self.rng.randrange(n), self.rng.randrange(n))
        guard = 0
        while new == old and guard < 100:
            new = (self.rng.randrange(n), self.rng.randrange(n))
            guard += 1
        self.treasure = new

    def _build(self, size):
        # GenerateHedgeMaze：lowLeftCorner = max(0, pos - size/2)，超出棋盘就往回挪
        lowx = self.pos[0] - size // 2
        lowy = self.pos[1] - size // 2
        if lowx < 0:
            lowx = 0
        if lowy < 0:
            lowy = 0
        while lowx + size > self.ws:
            lowx -= 1
        while lowy + size > self.ws:
            lowy -= 1
        self.x0 = lowx
        self.y0 = lowy
        self.side = size
        self.maze = {"walls": self._gen_maze(size)}
        self.treasure = (self.rng.randrange(size), self.rng.randrange(size))
        self.relocations = 0
        self.pending = 0
        self.entity = None
        # 源码 GenerateHedgeMaze 把整片迷宫的地面都设成 grassland
        self.ground = "grassland"
        self.built += 1


def make_ns(w):
    """把游戏 API 绑定成一个 dict（用 setattr 注入 builtins）。"""

    def get_pos_x():
        return w.pos[0]

    def get_pos_y():
        return w.pos[1]

    def get_world_size():
        return w.ws

    def get_time():
        # 每次读时钟推进 0.001 秒：保证游戏代码里 `while get_time() - t0 < x` 的
        # 有界等待能自然收敛（真机的时钟也在走）✓
        w.now += 0.001
        return w.now

    def get_ground_type():
        return w.ground

    def num_unlocked(u):
        if u == "mazes":
            return w.lv
        return 1

    def num_items(it):
        if it == "gold":
            return w.gold
        if it == "weird_substance":
            return w.weird
        return 0

    def get_cost(u):
        return None

    def can_move(d):
        w._tick()
        if not w.in_maze():
            return True
        lx, ly = w._local()
        return (w.maze["walls"][(lx, ly)] & BIT[d]) == 0

    def move(d):
        w._tick()
        w.move_calls += 1
        if w.move_fail_next > 0:
            w.move_fail_next -= 1
            return False
        if w.move_inject_every > 0 and w.move_calls % w.move_inject_every == 0:
            return False
        if not can_move(d):
            return False
        dx, dy = DELTA[d]
        w.pos = [(w.pos[0] + dx) % w.ws, (w.pos[1] + dy) % w.ws]
        return True

    def get_entity_type():
        w._tick()
        if w.in_maze():
            if tuple(w.pos) == w._abs_treasure():
                return "treasure"
            return "hedge"
        return w.entity

    def measure():
        w._tick()
        if not w.in_maze():
            return None
        return w._abs_treasure()

    def can_harvest():
        w._tick()
        if w.in_maze():
            return False
        if w.entity == "grass":
            return True
        return False

    def _regrow_grass():
        # 源码 `RemoveEntity(pos)` 默认 regrowGrass=true：grassland 上移除实体后**立刻**补一棵 grass
        if w.ground == "grassland":
            w.entity = "grass"
        else:
            w.entity = None

    def harvest():
        w._tick()
        if w.in_maze():
            # 源码：HedgePlant.Harvest → RemoveMaze()；在宝藏上还先收金币
            if tuple(w.pos) == w._abs_treasure():
                w.gold += w.per()
                w.collect.append(("harvest", w.built, w.gold))
            w.maze = None
            w.torn += 1
            # RemoveMaze 对每格也是 RemoveEntity(默认 regrowGrass=true) ⇒ 草地立刻重新长草
            _regrow_grass()
            return True
        if w.entity is not None:
            # Growable.Harvest → RemoveEntity(regrowGrass=true) ⇒ 在 grassland 上收完又长草
            _regrow_grass()
            return True
        return False

    def plant(e):
        w._tick()
        if e != "bush":
            return False
        if w.entity is not None:
            # 源码 Plant：已有实体且它 canBeOverplanted=false ⇒ **静默失败**（Grass 就是这种 ✗）
            return False
        if not w.in_maze():
            w.entity = "bush"
            return True
        return False

    def till():
        w._tick()
        if w.in_maze():
            return None
        # 源码 Drone.ChangeGround("soil")：
        #   非 HedgePlant 的实体先 RemoveEntity(regrowGrass=false)（真清掉，不补草）
        #   然后 grassland → soil（反过来 soil → grassland 时会补一棵 grass）
        if w.ground == "soil":
            w.ground = "grassland"
            w.entity = "grass"
        else:
            w.ground = "soil"
            w.entity = None
        return None

    def use_item(item, n=1):
        if item != "weird_substance":
            return False
        if w.weird < n:
            return False
        if w.in_maze():
            # 只能站在宝藏上复用（源码 RepositionTreasure）
            if tuple(w.pos) != w._abs_treasure():
                return False
            if w.relocations >= MAX_RELOC:
                return False      # 复用耗尽：不给金币、也不搬
            w.weird -= n
            w.gold += w.per()
            w.relocations += 1
            w.collect.append(("reuse", w.built, w.gold))
            w.pending = RELOC_TICKS       # 200 tick 定时器 ⇒ 稍后才可见重定位
            return True
        if w.entity == "grass":
            # 源码 UseItem：非 Bush/Treasure 的 Growable ⇒ ToggleWeird（施肥）
            #   ⇒ 旧 bug 在这里白烧一份物质却长不出迷宫（测试要能识别这种浪费 ✓）
            w.weird -= n
            return True
        if w.entity != "bush":
            return False
        size = int(n) // (1 << (w.lv - 1))
        if size < 1:
            return False
        w.weird -= n
        w._build(size)
        return True

    return {
        "get_pos_x": get_pos_x,
        "get_pos_y": get_pos_y,
        "get_world_size": get_world_size,
        "get_time": get_time,
        "get_ground_type": get_ground_type,
        "num_unlocked": num_unlocked,
        "num_items": num_items,
        "get_cost": get_cost,
        "can_move": can_move,
        "move": move,
        "get_entity_type": get_entity_type,
        "measure": measure,
        "can_harvest": can_harvest,
        "harvest": harvest,
        "plant": plant,
        "till": till,
        "use_item": use_item,
        "Entities": type("E", (), {
            "Bush": "bush", "Grass": "grass", "Hedge": "hedge", "Treasure": "treasure",
            "Carrot": "carrot", "Cactus": "cactus", "Pumpkin": "pumpkin",
            "Sunflower": "sunflower", "Tree": "tree"}),
        "Items": type("I", (), {
            "Gold": "gold", "Weird_Substance": "weird_substance", "Hay": "hay",
            "Wood": "wood", "Carrot": "carrot", "Pumpkin": "pumpkin",
            "Cactus": "cactus", "Bone": "bone", "Power": "power",
            "Fertilizer": "fertilizer"}),
        "Unlocks": type("U", (), {
            "Expand": "expand", "Plant": "plant", "Speed": "speed", "Grass": "grass",
            "Carrots": "carrots", "Watering": "watering", "Trees": "trees",
            "Sunflowers": "sunflowers", "Pumpkins": "pumpkins",
            "Fertilizer": "fertilizer", "Polyculture": "polyculture",
            "Cactus": "cactus", "Mazes": "mazes", "Dinosaurs": "dinosaurs",
            "Hats": "hats", "Megafarm": "megafarm", "Leaderboard": "leaderboard"}),
        "Grounds": type("G", (), {"Soil": "soil", "Grassland": "grassland"}),
        # 方向常量（游戏里是全局名字，不是枚举成员）
        "North": "North", "East": "East", "South": "South", "West": "West",
        # 游戏语言的内置列表函数（是全局函数，不是方法）
        "append": lambda lst, v: lst.append(v),
        "pop": lambda lst: lst.pop(),
        "insert": lambda lst, i, v: lst.insert(i, v),
        "remove": lambda lst, v: lst.remove(v),
    }


def install(w):
    """注入 builtins + 重新 import 游戏代码模块（jobs 的模块全局要全新的一份）。"""
    ns = make_ns(w)
    for k in ns:
        setattr(builtins, k, ns[k])
    for nm in ["util", "budget", "block_farm", "jobs"]:
        sys.modules.pop(nm, None)
    if SAVE not in sys.path:
        sys.path.insert(0, SAVE)
    import util            # noqa: F401
    import budget
    import jobs
    # 测试里不让"金币目标/留升级本钱/骨头目标"打断寿命（它们与复用协议无关）
    budget.gold_goal = lambda: 10 ** 12
    budget.mazes_keep = lambda: 0
    budget.bone_goal = lambda: 10 ** 12
    return ns, jobs, budget


def run_quiet(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ret = fn(*args)
    return ret, buf.getvalue()


# ============================================================
# (a) 整座寿命：建 1 次 → 连续 301 颗 → 拆 1 次
#     把 MZ_REUSE_MAX 临时调成 305：多出的 5 次用来**覆盖"复用耗尽"分支** ✓
# ============================================================
def test_lifetime():
    w = MazeWorld()
    ns, jobs, budget = install(w)
    jobs.MZ_REUSE_MAX = 305
    before = w.gold
    got, log = run_quiet(jobs.maze_shift, X0, Y0, SIDE, 1)
    per = w.per()
    errs = []
    if w.built != 1:
        errs.append("maze_built=%d（应 1：整座寿命只建一次）" % w.built)
    if w.torn != 1:
        errs.append("maze_torn=%d（应 1：最后 harvest 收尾抹一次）" % w.torn)
    if w.relocations != MAX_RELOC:
        errs.append("relocations=%d（应 %d：复用上限）" % (w.relocations, MAX_RELOC))
    if w.gold - before != 301 * per:
        errs.append("gold +%d（应 %d = 301 x %d）" % (w.gold - before, 301 * per, per))
    if w.maze is not None:
        errs.append("迷宫没被抹掉（无人机被困 ✗）")
    n_reuse = len([e for e in w.collect if e[0] == "reuse"])
    n_harv = len([e for e in w.collect if e[0] == "harvest"])
    if n_reuse != 300:
        errs.append("use_item 收货 %d 次（应 300）" % n_reuse)
    if n_harv != 1:
        errs.append("收尾 harvest %d 次（应 1）" % n_harv)
    if len(set(e[1] for e in w.collect)) != 1:
        errs.append("金币来自多座迷宫（应全部来自同一座）")
    if got != 301 * per:
        errs.append("maze_shift 返回 %d（应 %d）" % (got, 301 * per))
    if "本座寿命结束" not in log:
        errs.append("缺少 `本座寿命结束` 日志")
    if "复用耗尽" not in log:
        errs.append("缺少 `复用耗尽` 日志（耗尽分支没覆盖到）")
    if "复用第" not in log:
        errs.append("缺少 `复用第 N 颗` 日志（复用没生效）")
    for k in ["复用第", "本座寿命结束", "复用耗尽"]:
        for line in log.split("\n"):
            if k in line:
                print("    |", line)
                break
    return errs


# ============================================================
# (b) 第二次建迷宫：地上有 **Grass 且地面是 Grassland** ⇒ 必须先清格再种
#     真机 w22 事故（2026-11-01）：`[mz] !! 建图点 18 4 种不上灌木（脚下 Entities.Grass |
#     地面 Grounds.Grassland）` 反复出现 5,529 次 ⇒ 两座迷宫几乎零产能 ✗
#     根因（源码）：`harvest()` 草用 RemoveEntity(默认 regrowGrass=true) ⇒ 在 grassland 上
#     收完**立刻又长一棵** ♻ ⇒ 只有 `till()` 能真清（regrowGrass=false + 变 Soil）✓
# ============================================================
def test_build_on_grass():
    w = MazeWorld(seed=11)
    ns, jobs, budget = install(w)
    jobs.MZ_REUSE_MAX = 3
    # 用一次短寿命把 anchor 学出来（真机上 roles 会直接传 -4,-4）
    run_quiet(jobs.maze_shift, X0, Y0, SIDE, 1)
    if jobs.MZ_ANCHOR[0] != -4 or jobs.MZ_ANCHOR[1] != -4:
        return ["锚点没学出来：%s（居中锚点应为 -4,-4）" % (jobs.MZ_ANCHOR,)]
    errs = []
    built_before = w.built
    weird_before = w.weird
    # 模拟"迷宫拆除后草重新长满 Grassland"：建图点上是 Grass + Grounds.Grassland（真机现场 ✓）
    w.entity = "grass"
    w.ground = "grassland"
    w.pos = [X0 + SIDE // 2, Y0 + SIDE // 2]
    ok = jobs.maze_build(X0, Y0, SIDE, w.sub(), X0 + SIDE // 2, Y0 + SIDE // 2)
    if ok != 1:
        errs.append("Grass+Grassland 时 maze_build 返回 %d（应 1）" % ok)
    if w.built != built_before + 1:
        errs.append("没有真的建出迷宫（built %d -> %d）⇒ 清格失败，plant 被 Grass 挡住"
                    % (built_before, w.built))
    if weird_before - w.weird != w.sub():
        errs.append("物质花了 %d（应 %d：只花一份；多花说明 use_item 去给 Grass 施肥了）"
                    % (weird_before - w.weird, w.sub()))
    return errs


# ============================================================
# (j) 单元级：mz_plant_bush 必须能清掉 **Grassland 上的 Grass** 并种出 Bush
#     （这是 w22 事故的最小复现；旧实现会 harvest 8 次、每次草又长回来 ⇒ 返回 0 ✗）
# ============================================================
def test_plant_bush_clears_grass():
    w = MazeWorld(seed=83)
    ns, jobs, budget = install(w)
    errs = []
    # 场景 ①：grassland + grass（真机现场）
    w.pos = [10, 4]
    w.ground = "grassland"
    w.entity = "grass"
    ok = jobs.mz_plant_bush()
    if ok != 1:
        errs.append("grassland+grass：mz_plant_bush 返回 %d（应 1）" % ok)
    if w.entity != "bush":
        errs.append("grassland+grass：脚下不是 Bush（是 %r）" % (w.entity,))
    if w.ground != "soil":
        errs.append("grassland+grass：清格后地面应被 till 成 Soil（是 %r）" % (w.ground,))
    # 场景 ②：soil + grass（草地也能长在 soil 上）⇒ 收完草后 soil 上**不会**再补草 ⇒ 直接种
    w.pos = [10, 4]
    w.ground = "soil"
    w.entity = "grass"
    ok2 = jobs.mz_plant_bush()
    if ok2 != 1:
        errs.append("soil+grass：mz_plant_bush 返回 %d（应 1）" % ok2)
    if w.entity != "bush":
        errs.append("soil+grass：脚下不是 Bush（是 %r）" % (w.entity,))
    # 场景 ③：已经空地 ⇒ 直接种
    w.entity = None
    ok3 = jobs.mz_plant_bush()
    if ok3 != 1 or w.entity != "bush":
        errs.append("空地：mz_plant_bush 返回 %d / 实体 %r（应 1 / bush）" % (ok3, w.entity))
    return errs


# ============================================================
# (k) 清格失败诊断：plant 永远失败时必须**有界放弃**并打印
#     「清格失败 + 实际实体 + 地面 + 试过的动作序列」（真机排障用 ✓）
# ============================================================
def test_plant_fail_diagnostics():
    w = MazeWorld(seed=91)
    ns, jobs, budget = install(w)
    errs = []
    w.pos = [10, 4]
    w.ground = "grassland"
    w.entity = "grass"
    orig_plant = builtins.plant

    def bad_plant(e):
        return False

    builtins.plant = bad_plant
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = jobs.mz_plant_bush()
        log = buf.getvalue()
    finally:
        builtins.plant = orig_plant
    if ok != 0:
        errs.append("plant 永远失败时 mz_plant_bush 返回 %d（应 0）" % ok)
    if "清格失败" not in log:
        errs.append("缺少 `清格失败` 诊断打印")
    if "Entities.Grass" not in log and "grass" not in log:
        errs.append("诊断里缺少实际实体")
    if "Grassland" not in log and "grassland" not in log:
        errs.append("诊断里缺少实际地面")
    if "harvest" not in log and "till" not in log:
        errs.append("诊断里缺少试过的动作序列")
    for line in log.split("\n"):
        if "清格失败" in line:
            print("    |", line)
            break
    return errs


# ============================================================
# (c) 走到宝藏途中注入 move() 失败（地图过期/现实与地图不符）⇒ 走位自愈 + 继续复用 ≥5 颗
# ============================================================
def test_walk_self_heal():
    w = MazeWorld(seed=23)
    ns, jobs, budget = install(w)
    jobs.MZ_REUSE_MAX = 3
    run_quiet(jobs.maze_shift, X0, Y0, SIDE, 1)      # 学锚点 + 建一次
    # 再建一座（上一个 lifetime 结束时已抹掉）
    w.entity = "grass"
    w.pos = [X0 + SIDE // 2, Y0 + SIDE // 2]
    if jobs.maze_build(X0, Y0, SIDE, w.sub(), X0 + SIDE // 2, Y0 + SIDE // 2) != 1:
        return ["自测准备失败：第二座迷宫没建出来"]
    errs = []
    if jobs.maze_map_walk(X0, Y0, SIDE) != 1:
        return ["自测准备失败：建图失败"]
    # 每 9 次 move 注入一次失败（模拟"墙被拆后地图过期"/别的无人机干扰）
    w.move_inject_every = 9
    per = w.per()
    before = w.gold
    okcnt = 0
    k = 0
    while k < 6:
        k = k + 1
        ok = jobs.maze_walk_to_treasure(X0, Y0, SIDE, SIDE * SIDE * 3 + 300)
        if ok != 1:
            errs.append("第 %d 次走位在注入 move 失败后返回 %d（应 1：必须自愈）" % (k, ok))
            break
        g0 = w.gold
        ns["use_item"]("weird_substance", w.sub())
        if w.gold < g0 + per:
            errs.append("第 %d 次复用没收到金币（%d -> %d）" % (k, g0, w.gold))
            break
        okcnt = okcnt + 1
        # 等"重定位"可见（模拟 200 tick 定时器）
        guard = 0
        while w.pending > 0 and guard < 500:
            ns["measure"]()
            guard = guard + 1
    if okcnt < 5:
        errs.append("只连续收了 %d 颗（要求 >= 5）" % okcnt)
    if w.gold - before != okcnt * per:
        errs.append("金币 +%d（应 %d）" % (w.gold - before, okcnt * per))
    return errs


# ============================================================
# (d) 迷宫中途被别的无人机抹掉（measure()=None）⇒ 走路安全返回 0，不崩
# ============================================================
def test_maze_vanishes():
    w = MazeWorld(seed=31)
    ns, jobs, budget = install(w)
    jobs.MZ_REUSE_MAX = 3
    run_quiet(jobs.maze_shift, X0, Y0, SIDE, 1)
    w.entity = None
    w.pos = [X0 + SIDE // 2, Y0 + SIDE // 2]
    jobs.maze_build(X0, Y0, SIDE, w.sub(), X0 + SIDE // 2, Y0 + SIDE // 2)
    jobs.maze_map_walk(X0, Y0, SIDE)
    w.maze = None                       # 被同区另一架 harvest 掉了
    errs = []
    ok = jobs.maze_walk_to_treasure(X0, Y0, SIDE, SIDE * SIDE * 3 + 300)
    if ok != 0:
        errs.append("迷宫没了却返回 %d（应 0）" % ok)
    try:
        jobs.maze_escape()              # 不应崩
    except Exception as e:              # noqa: BLE001
        errs.append("maze_escape 在空地上崩了：%r" % (e,))
    return errs


# ============================================================
# (e) 整张地图过期（迷宫被重建、墙完全变了）⇒ 重探一次后又能走到 ✓
# ============================================================
def test_stale_whole_map():
    w = MazeWorld(seed=41)
    ns, jobs, budget = install(w)
    jobs.MZ_REUSE_MAX = 3
    run_quiet(jobs.maze_shift, X0, Y0, SIDE, 1)
    w.entity = None
    w.pos = [X0 + SIDE // 2, Y0 + SIDE // 2]
    jobs.maze_build(X0, Y0, SIDE, w.sub(), X0 + SIDE // 2, Y0 + SIDE // 2)
    jobs.maze_map_walk(X0, Y0, SIDE)
    errs = []
    # 模拟另一架把迷宫拆了重建（同一位置、全新墙图）⇒ 我们手里的图整张过期
    w.maze = {"walls": w._gen_maze(SIDE)}
    w.treasure = (w.rng.randrange(SIDE), w.rng.randrange(SIDE))
    w.relocations = 0
    # 1) 旧图可能走不到（这是允许的）；2) 调用方（maze_life）会整张重探；3) 再走必须成功
    jobs.maze_walk_to_treasure(X0, Y0, SIDE, SIDE * SIDE * 3 + 300)
    jobs.MZ_IN[0] = 1
    if jobs.maze_map_walk(X0, Y0, SIDE) != 1:
        errs.append("重探建图失败（应 1）")
        return errs
    ok = jobs.maze_walk_to_treasure(X0, Y0, SIDE, SIDE * SIDE * 3 + 300)
    if ok != 1:
        errs.append("重探后仍走不到（应 1）")
    return errs


# ============================================================
# (f) 生产参数（MZ_REUSE_MAX=300）的正常路径：
#     300 次复用全部成功 ⇒ 循环自然结束（不是"耗尽"分支）⇒ 走到新宝藏收第 301 颗 ✓
# ============================================================
def test_lifetime_production_max():
    w = MazeWorld(seed=13)
    ns, jobs, budget = install(w)
    before = w.gold
    got, log = run_quiet(jobs.maze_shift, X0, Y0, SIDE, 1)
    per = w.per()
    errs = []
    if jobs.MZ_REUSE_MAX != 300:
        errs.append("MZ_REUSE_MAX=%d（生产值应为 300）" % jobs.MZ_REUSE_MAX)
    if w.built != 1 or w.torn != 1:
        errs.append("built=%d torn=%d（应 1/1）" % (w.built, w.torn))
    if w.relocations != 300:
        errs.append("relocations=%d（应 300）" % w.relocations)
    if w.gold - before != 301 * per:
        errs.append("gold +%d（应 %d）" % (w.gold - before, 301 * per))
    if got != 301 * per:
        errs.append("返回 %d（应 %d）" % (got, 301 * per))
    if "本座寿命结束" not in log:
        errs.append("缺少 `本座寿命结束` 日志")
    return errs


# ============================================================
# (g) 生产形态：maze_worker 一个班次 ①时间有界（R2）②收尾必把迷宫抹掉
#     （新副机只在主机位置 (0,0) 出生 + 迷宫边界封闭 ⇒ 留场 = 该区域永远进不去 ✗✗）
# ============================================================
def test_worker_shift_bounded():
    w = MazeWorld(seed=17)
    w.tick_sec = 0.02                 # 模拟真实时间流逝（每动作 0.02 秒量级）
    ns, jobs, budget = install(w)
    jobs.MZ_REUSE_MAX = 300
    n, log = run_quiet(jobs.maze_worker, X0, Y0, SIDE, SIDE, 12, w.ws,
                       [-4, -4])      # roles 传锚点（= stage_w16 的写法 ✓）
    errs = []
    if w.maze is not None:
        errs.append("班次结束后迷宫还留在场上（下一班从 (0,0) 出生、进不去 ⇒ 该区域报废 ✗）")
    if w.torn < 1:
        errs.append("torn=%d（应 >=1：收尾 harvest 抹迷宫）" % w.torn)
    if n < 1:
        errs.append("n=%d（应 >=1 座）" % n)
    ev = [e for e in w.collect if e[0] in ("reuse", "harvest")]
    if len(ev) < 5:
        errs.append("只收了 %d 颗（应 >= 5）" % len(ev))
    if w.now > jobs.MZ_SHIFT_SEC + 40.0:
        errs.append("班次用时 %.1fs 超过上限 %.1fs（R2 被破坏）"
                    % (w.now, jobs.MZ_SHIFT_SEC + 40.0))
    if "副机班次结束" not in log:
        errs.append("缺少 `副机班次结束` 日志")
    if "复用第" not in log:
        errs.append("缺少 `复用第 N 颗` 日志（复用没生效）")
    for line in log.split("\n"):
        if "副机班次结束" in line or "本座寿命结束" in line:
            print("    |", line)
    print("    | 班次虚拟用时 %.1fs | 建 %d 座 | 收 %d 颗 | 迷宫留场: %r"
          % (w.now, w.built, len(ev), w.maze is not None))
    return errs


# ============================================================
# (h) 布局门禁：stage_w16 的**轮作区必须与迷宫区不相交**
#   真机 bug（2026-11-01）：轮作切片曾切到 (6,8,8,8) = 现在的 maze1 ⇒ 轮作副机被困在迷宫里，
#   它的 work_tile 对树篱 `can_harvest()` 返回 true（源码 FarmObject.Harvestable=>true）
#   ⇒ harvest() = RemoveMaze ⇒ 整座迷宫被秒毁 ✗；且主机 sweep 会被 maze0 挡死（util.go_to 旧版无界）✗✗
#   ⇒ 用 stage_w16.lands() + stage_w16.assign(8) **机械验**：每片轮作都必须落在 farm_a 内、
#     与任一迷宫区不相交、且彼此不重叠 ✓
# ============================================================
def _overlap(a, b):
    # a/b = (x, y, w, h)；返回 1 = 有重叠
    if a[0] + a[2] <= b[0]:
        return 0
    if b[0] + b[2] <= a[0]:
        return 0
    if a[1] + a[3] <= b[1]:
        return 0
    if b[1] + b[3] <= a[1]:
        return 0
    return 1


def test_w16_layout():
    w = MazeWorld(seed=5)
    ns, jobs, budget = install(w)
    sys.modules.pop("stage_w16", None)
    import stage_w16

    errs = []
    lnd = stage_w16.lands()
    rects = []
    i = 0
    while i < len(lnd):
        rects.append(lnd[i])
        i = i + 1
    mazes = [r for r in rects if r[0] == "maze0" or r[0] == "maze1"]
    if len(mazes) < 2:
        errs.append("stage_w16.lands() 里迷宫区少于 2 座：%r" % (mazes,))
        return errs
    farm = [r for r in rects if r[0] == "farm_a"][0]
    farm_rect = (farm[1], farm[2], farm[3], farm[4])
    # 1) lands() 本身必须铺满 16x16 且不重叠
    if ns["get_world_size"]() != 16:
        errs.append("测试世界不是 16x16")
    import util as u2
    if u2.check_lands(lnd, 16) != 1:
        errs.append("stage_w16.lands() 没通过 check_lands(16)")
    # 2) assign(8) 返回的轮作切片
    js = stage_w16.assign(8)
    rots = [j for j in js if j["entry"] == jobs.rotation_worker]
    if len(rots) < 1:
        errs.append("stage_w16.assign(8) 没派轮作切片")
        return errs
    rect_a = []
    for j in rots:
        a = (j["x0"], j["y0"], j["w"], j["h"])
        rect_a.append(a)
        if len(j["roles"]) != j["w"]:
            errs.append("轮作切片 %s 的 roles 列数 %d != w %d"
                        % (j["name"], len(j["roles"]), j["w"]))
        if a[0] < farm_rect[0] or a[1] < farm_rect[1]:
            errs.append("轮作切片 %s @%r 超出 farm_a %r" % (j["name"], a, farm_rect))
        if a[0] + a[2] > farm_rect[0] + farm_rect[2]:
            errs.append("轮作切片 %s @%r 超出 farm_a %r" % (j["name"], a, farm_rect))
        if a[1] + a[3] > farm_rect[1] + farm_rect[3]:
            errs.append("轮作切片 %s @%r 超出 farm_a %r" % (j["name"], a, farm_rect))
        for m in mazes:
            mr = (m[1], m[2], m[3], m[4])
            if _overlap(a, mr) == 1:
                errs.append("!! 轮作切片 %s @%r 与 %s @%r 重叠（轮作会 harvest 树篱毁迷宫 ✗）"
                            % (j["name"], a, m[0], mr))
    # 3) 切片彼此不重叠、且总面积 = farm_a 面积
    k = 0
    area = 0
    while k < len(rect_a):
        area = area + rect_a[k][2] * rect_a[k][3]
        m = k + 1
        while m < len(rect_a):
            if _overlap(rect_a[k], rect_a[m]) == 1:
                errs.append("轮作切片 %r 与 %r 互相重叠" % (rect_a[k], rect_a[m]))
            m = m + 1
        k = k + 1
    if area != farm_rect[2] * farm_rect[3]:
        errs.append("轮作切片总面积 %d != farm_a 面积 %d"
                    % (area, farm_rect[2] * farm_rect[3]))
    # 4) 配比不变量（**按整块轮作区合计**，不是按切片：util.check_ratio 也是合计口径 ✓）
    tot_hay = 0
    tot_carrot = 0
    for j in rots:
        for role in j["roles"]:
            if role == "hay":
                tot_hay = tot_hay + j["h"]
            if role == "carrot":
                tot_carrot = tot_carrot + j["h"]
    if tot_carrot > tot_hay:
        errs.append("轮作区配比违反不变量：草 %d 格 < 胡萝卜 %d 格（每株胡萝卜要 1 草 + 1 木）"
                    % (tot_hay, tot_carrot))
    print("    | 轮作切片:", [(j["name"], j["x0"], j["y0"], j["w"], j["h"]) for j in rots])
    print("    | 迷宫区:", [(m[0], m[1], m[2], m[3], m[4]) for m in mazes],
          "| farm_a:", farm_rect)
    return errs


# ============================================================
# (i) util.go_to 的边界行为：
#   ① 必须仍然**能到**环形的近端目标（(0,0)→(14,0) 走 West 两步，不穿 maze0 ✓）
#   ② 目标在封闭迷宫**内部**时**必须放弃**（旧版无界 while ⇒ 永久卡死 ✗）
#   真机风险链：迷宫边界封闭 ⇒ 副机撞墙 move() 只返回 False 不报错 ⇒ 旧 go_to 死循环
#   ⇒ 配合 full_run 的 ACTIVEB「只有 live==0 才清零」⇒ 一架卡死 = 所有副机不再放飞 ✗✗
# ============================================================
def test_go_to_bounded():
    w = MazeWorld(seed=61)
    ns, jobs, budget = install(w)
    import util
    errs = []
    # 在 (6,0) 建一座 8x8 迷宫（边界全封闭）当障碍
    w.pos = [10, 4]
    w.entity = "bush"
    ns["use_item"]("weird_substance", w.sub())
    if w.maze is None:
        return ["准备失败：迷宫没建出来"]
    # ① 环形近端：从 (0,0) 去 (14,0) ⇒ 走 West 2 步（若按旧版"数值方向"会被 maze0 挡死 ✗）
    w.pos = [0, 0]
    moves0 = w.move_calls
    ret = util.go_to(14, 0)
    moves = w.move_calls - moves0
    if ret != 1:
        errs.append("环形近端目标 (14,0) 没走到（返回 %r）" % (ret,))
    if moves > 4:
        errs.append("去 (14,0) 走了 %d 步（应约 2 步 West，不能穿迷宫）" % moves)
    # ② 目标在封闭迷宫内部 (10,4) ⇒ 必须**有界放弃**，不能永久卡死
    w.pos = [0, 0]
    moves0 = w.move_calls
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ret2 = util.go_to(10, 4)
    moves2 = w.move_calls - moves0
    log = buf.getvalue()
    if ret2 != 0:
        errs.append("目标在迷宫内部时 go_to 返回 %r（应 0）" % (ret2,))
    if moves2 > 200:
        errs.append("被挡时 go_to 走了 %d 步（应有界，<= 100 量级）" % moves2)
    if "[ut] !! go_to 走不到" not in log:
        errs.append("缺少 `[ut] !! go_to 走不到` 诊断打印")
    print("    | 环形近端 go_to: 返回 %r 走 %d 步 ✓ | 被迷宫挡住: 返回 %r 走 %d 步 ✓"
          % (ret, moves, ret2, moves2))
    return errs


# ============================================================
# (l) 布局门禁：stage_w22 的**轮作切片必须与 4 座迷宫区不相交**（机械验）
#   真机（2026-11-01）：w22 的 maze2/maze3 建图点 (18,4)/(18,12) 反复"种不上灌木"，
#   已定位为 Grass 清格 bug（见 (b)/(j)），这里再机械确认布局本身没问题 ✓
# ============================================================
def test_w22_layout():
    w = MazeWorld(ws=22, seed=5)
    ns, jobs, budget = install(w)
    sys.modules.pop("stage_w22", None)
    import stage_w22
    import util as u2

    errs = []
    lnd = stage_w22.lands()
    if u2.check_lands(lnd, 22) != 1:
        errs.append("stage_w22.lands() 没通过 check_lands(22)")
    rects = []
    for r in lnd:
        rects.append(r)
    mazes = [r for r in rects if r[0] == "maze0" or r[0] == "maze1"
             or r[0] == "maze2" or r[0] == "maze3"]
    if len(mazes) < 4:
        errs.append("stage_w22.lands() 里迷宫区少于 4 座：%r" % (mazes,))
        return errs
    js = stage_w22.assign(8)
    rots = [j for j in js if j["entry"] == jobs.rotation_worker]
    if len(rots) < 1:
        errs.append("stage_w22.assign(8) 没派轮作切片")
        return errs
    for j in rots:
        a = (j["x0"], j["y0"], j["w"], j["h"])
        for m in mazes:
            mr = (m[1], m[2], m[3], m[4])
            if _overlap(a, mr) == 1:
                errs.append("!! w22 轮作切片 %s @%r 与 %s @%r 重叠"
                            "（轮作会 harvest 树篱毁迷宫 ✗）" % (j["name"], a, m[0], mr))
    # 迷宫区本身也不能互相重叠
    k = 0
    while k < len(mazes):
        m = k + 1
        while m < len(mazes):
            if _overlap((mazes[k][1], mazes[k][2], mazes[k][3], mazes[k][4]),
                        (mazes[m][1], mazes[m][2], mazes[m][3], mazes[m][4])) == 1:
                errs.append("w22 迷宫区 %s 与 %s 重叠" % (mazes[k][0], mazes[m][0]))
            m = m + 1
        k = k + 1
    print("    | w22 轮作切片:", [(j["name"], j["x0"], j["y0"], j["w"], j["h"]) for j in rots])
    print("    | w22 迷宫区:", [(m[0], m[1], m[2], m[3], m[4]) for m in mazes])
    return errs


# ============================================================
# (m) 性能回归：寻宝走路**不允许每步重算 BFS**
#   真机实测（2026-11-01）：旧实现每步调一次 maze_bfs_dir（64 格 BFS ≈2,000 tick）
#   ⇒ 单颗 ~20,000 tick（≈30~50 游戏秒）⇒ 每座寿命 140s 只收 6.4 颗 ✗✗
#   ⇒ 现在必须：① 走到宝藏过程中 **0 次** maze_bfs_dir；② 每颗最多 2 次 maze_field
#     （正常 1 次；若中途撞墙记墙导致场作废，最多再 1 次）
# ============================================================
def test_walk_uses_distance_field():
    w = MazeWorld(seed=97)
    ns, jobs, budget = install(w)
    jobs.MZ_REUSE_MAX = 3
    run_quiet(jobs.maze_shift, X0, Y0, SIDE, 1)      # 学锚点 + 建一次
    w.pos = [X0 + SIDE // 2, Y0 + SIDE // 2]
    if jobs.maze_build(X0, Y0, SIDE, w.sub(), X0 + SIDE // 2, Y0 + SIDE // 2) != 1:
        return ["自测准备失败：第二座迷宫没建出来"]
    if jobs.maze_map_walk(X0, Y0, SIDE) != 1:
        return ["自测准备失败：建图失败"]
    errs = []
    field_calls = [0]
    bfs_calls = [0]
    orig_field = jobs.maze_field
    orig_bfs = jobs.maze_bfs_dir

    def counted_field(*a):
        field_calls[0] = field_calls[0] + 1
        return orig_field(*a)

    def bad_bfs(*a):
        bfs_calls[0] = bfs_calls[0] + 1
        return orig_bfs(*a)

    jobs.maze_field = counted_field
    jobs.maze_bfs_dir = bad_bfs
    try:
        ok = jobs.maze_walk_to_treasure(X0, Y0, SIDE, SIDE * SIDE * 3 + 300)
    finally:
        jobs.maze_field = orig_field
        jobs.maze_bfs_dir = orig_bfs
    if ok != 1:
        errs.append("走位返回 %d（应 1）" % ok)
    if bfs_calls[0] > 0:
        errs.append("走位过程中调了 %d 次 maze_bfs_dir（应 0：每步重算 BFS = 旧性能 bug ✗）"
                    % bfs_calls[0])
    if field_calls[0] > 2:
        errs.append("一颗宝藏算了 %d 次距离场（应 <=2：正常 1 次）" % field_calls[0])
    print("    | 一颗宝藏：距离场计算 %d 次 / 每步 BFS %d 次 ✓"
          % (field_calls[0], bfs_calls[0]))
    return errs


# ============================================================
# (n) 布局门禁：stage_w16 的**主机 sweep 矩形**必须与 cactus / 迷宫区不相交
#   真机 bug 2026-11-02（用户报「仙人掌田和混合种植冲突」）：主机 sweep 原参数是
#   (0, BLOCK, BLOCK, SIDE-BLOCK) = (0,6,6,10) ⇒ 覆盖 cactus (0,6,6,6) + farm_a (0,12,6,4)
#   ⇒ 主机会 harvest/plant 仙人掌方块 ⇒ 与仙人掌副机抢地（R5）、破坏排序块 ✗✗
#   本测试**实际执行 stage_w16.run()**（stub 掉其它产线），抓 sweep_columns 的入参做机械验 ✓
# ============================================================
def test_w16_host_sweep():
    w = MazeWorld(seed=17)
    ns, jobs, budget = install(w)
    import util
    sys.modules.pop("stage_w16", None)
    import stage_w16

    errs = []
    calls = []
    orig = {
        "sweep": jobs.sweep_columns,
        "sun": jobs.sun_shift,
        "cactus": jobs.cactus_shift,
        "pumpkin": jobs.pumpkin_shift,
        "maze": jobs.maze_shift,
        "full": jobs.full_maze_run,
        "dino": jobs.dino_run,
        "report": stage_w16.s16_report,
        "drones": util.drone_count,
    }

    def rec_sweep(x0, y0, ww, hh, roles):
        calls.append((x0, y0, ww, hh, roles))
        return 1

    jobs.sweep_columns = rec_sweep
    jobs.sun_shift = lambda *a: 0
    jobs.cactus_shift = lambda *a: 0
    jobs.pumpkin_shift = lambda *a: 0
    jobs.maze_shift = lambda *a: 0
    jobs.full_maze_run = lambda *a: 0
    jobs.dino_run = lambda *a: 0
    stage_w16.s16_report = lambda a, b: None
    util.drone_count = lambda: 1          # 走"主机独自在飞"的分支（不含迷宫区）
    try:
        stage_w16.run()
    finally:
        jobs.sweep_columns = orig["sweep"]
        jobs.sun_shift = orig["sun"]
        jobs.cactus_shift = orig["cactus"]
        jobs.pumpkin_shift = orig["pumpkin"]
        jobs.maze_shift = orig["maze"]
        jobs.full_maze_run = orig["full"]
        jobs.dino_run = orig["dino"]
        stage_w16.s16_report = orig["report"]
        util.drone_count = orig["drones"]

    if len(calls) != 1:
        errs.append("主机 run() 里 sweep_columns 调用 %d 次（应 1 次：只扫 farm_a）" % len(calls))
        return errs
    x0, y0, ww, hh, roles = calls[0]
    sweep_rect = (x0, y0, ww, hh)
    # 1) 4 个参数逐一核对：farm_a = (0,12,6,4)
    if sweep_rect != (0, 12, 6, 4):
        errs.append("主机 sweep 矩形 %r ≠ farm_a (0,12,6,4)" % (sweep_rect,))
    # 2) 角色表长度必须 = 列数
    if len(roles) != ww:
        errs.append("sweep 角色表长度 %d ≠ 列数 %d" % (len(roles), ww))
    # 3) 与 lands() 里 cactus / 迷宫区**不相交**（farm_a 允许相交，它就是 farm_a）
    lnd = stage_w16.lands()
    for r in lnd:
        if r[0] == "farm_a":
            continue
        other = (r[1], r[2], r[3], r[4])
        if _overlap(sweep_rect, other) == 1:
            errs.append("!! 主机 sweep %r 与 %s %r 重叠（会抢仙人掌/迷宫的地 ✗）"
                        % (sweep_rect, r[0], other))
    # 4) check_ratio 仍通过（草 >= 胡萝卜）
    import contextlib
    import io as _io
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = util.check_ratio("w16", [("farm_a", 4, roles)])
    if ok != 1:
        errs.append("check_ratio 不通过（草 < 胡萝卜）")
    if len(stage_w16.ROLES_A) != 6:
        errs.append("ROLES_A 长度 %d ≠ 6" % len(stage_w16.ROLES_A))
    print("    | 主机 sweep =", sweep_rect, "roles =", roles)
    print("    | cactus =", [r[1:] for r in lnd if r[0] == "cactus"],
          "| mazes =", [r[1:] for r in lnd if r[0].startswith("maze")])
    return errs


# ============================================================
# (o) 进区路线：spawn 在 (0,0) + **maze0 已经在场上** ⇒ 去 maze1(6,8) 必须绕得过去
#   真机风险（2026-11-02 用户/Lead 怀疑点）：从 (0,0) 出发若"先 x 走 y=0"会撞 maze0 树篱；
#   必须"先沿 x=0 走到 y、再横穿自己区域"（mz_goto_best 的 y 先路线）✓
# ============================================================
def test_entry_route_past_maze0():
    w = MazeWorld(seed=77)
    ns, jobs, budget = install(w)
    errs = []
    # 手工在 maze0 区 (6,0) 建一座迷宫当障碍
    w.pos = [10, 4]
    w.entity = "bush"
    ns["use_item"]("weird_substance", w.sub())
    if w.maze is None or (w.x0, w.y0) != (6, 0):
        return ["准备失败：maze0 障碍没建出来（%r）" % ((w.x0, w.y0),)]
    w.pos = [0, 0]                      # 模拟副机 spawn 点
    built_before = w.built
    # 去 maze1 区 (6,8) 的建图点 (10,12)
    ok = jobs.maze_build(6, 8, 8, w.sub(), 10, 12)
    if ok != 1:
        errs.append("从 (0,0) 去 maze1 建图点 (10,12) 失败（返回 %d）⇒ y 先路线没生效 ✗" % ok)
    if w.built != built_before + 1:
        errs.append("maze1 没建出来（built %d -> %d）" % (built_before, w.built))
    if (w.x0, w.y0) != (6, 8):
        errs.append("maze1 落点 %r ≠ (6,8)（锚点补偿错）" % ((w.x0, w.y0),))
    # 再来一次 maze0 路线：从 (0,0) 去 (10,4)，周围没有别的迷宫
    w.pos = [0, 0]
    ok2 = jobs.maze_build(6, 0, 8, w.sub(), 10, 4)
    if ok2 != 1:
        errs.append("从 (0,0) 去 maze0 建图点 (10,4) 失败（返回 %d）" % ok2)
    print("    | (0,0)→maze1(6,8) 建图返回", ok, "| (0,0)→maze0(6,0) 建图返回", ok2)
    return errs


# ============================================================
# (p) 物质不足时 maze_worker 必须**提前收工**（别空转整班）且打印可区分
#   真机 2026-11-02：物质不足时旧版每秒重试、打印"疑似被邻区干扰"，还占着 ACTIVEB 不清零
#   ⇒ 农场类副机不重派 ⇒ 物质永远产不上来（hay 5/power 0 反馈环）✗✗
# ============================================================
def test_worker_exits_on_low_weird():
    w = MazeWorld(seed=99)
    ns, jobs, budget = install(w)
    w.weird = 0
    n, log = run_quiet(jobs.maze_worker, X0, Y0, SIDE, SIDE, 12, w.ws, [-4, -4])
    errs = []
    if n != 0:
        errs.append("n=%d（应 0）" % n)
    if w.built != 0:
        errs.append("物质为 0 却建了 %d 座迷宫" % w.built)
    if "物质不足" not in log:
        errs.append("缺少 `物质不足 ⇒ 提前收工` 诊断打印")
    if "连续 3 次没收到金币" in log:
        errs.append("物质不足时不该打印误导性的 `连续 3 次没收到金币` ✗")
    if w.now > 10.0:
        errs.append("物质不足时班次却耗了 %.1f 游戏秒（应提前收工，别空转）" % w.now)
    for line in log.split("\n"):
        if "物质不足" in line:
            print("    |", line)
            break
    return errs


def main():
    print("=== test_maze_reuse：按 Core.dll 反编译语义建的迷宫 mock ===")
    print("  ① harvest 在宝藏/树篱上 = 收金币(仅宝藏) + RemoveMaze")
    print("  ② use_item(weird, sub) 在宝藏上 = 收金币 + 重定位 + 随机拆墙（上限 300）")
    print("  ③ 复用耗尽后 harvest 收第 301 颗并抹掉迷宫")
    print()
    cases = [
        ("(a) 整座寿命+耗尽分支：建 1 次 → 连续收 301 颗 → 只拆 1 次", test_lifetime),
        ("(b) 地上有 Grass 也能建迷宫（覆盖'迷宫没长出来'根因）", test_build_on_grass),
        ("(c) move() 失败注入 ⇒ 走位自愈 + 连续复用 >= 5 颗", test_walk_self_heal),
        ("(d) 迷宫被抹掉 ⇒ 走路安全返回 0 不崩", test_maze_vanishes),
        ("(e) 整张地图过期 ⇒ 重探后又能走到", test_stale_whole_map),
        ("(f) 生产参数 300 次复用的正常路径（收第 301 颗）", test_lifetime_production_max),
        ("(g) maze_worker 班次有界 + 收尾必抹迷宫（不留场）", test_worker_shift_bounded),
        ("(h) 布局门禁：stage_w16 轮作区与迷宫区不相交（机械验）", test_w16_layout),
        ("(i) util.go_to 被迷宫挡住时有界放弃（不再永久卡死）", test_go_to_bounded),
        ("(j) Grassland+Grass 清格并种出 Bush（w22 事故最小复现）", test_plant_bush_clears_grass),
        ("(k) 清格失败必须有界放弃 + 打印实体/地面/动作序列", test_plant_fail_diagnostics),
        ("(l) 布局门禁：stage_w22 轮作区与 4 座迷宫区不相交（机械验）", test_w22_layout),
        ("(m) 性能回归：寻宝只算 1 次距离场、绝不每步重算 BFS", test_walk_uses_distance_field),
        ("(n) 布局门禁：stage_w16 主机 sweep 与 cactus/迷宫不相交（机械验）", test_w16_host_sweep),
        ("(o) 进区路线：spawn(0,0) + maze0 在场上 ⇒ 仍能到 maze1 建图", test_entry_route_past_maze0),
        ("(p) 物质不足 ⇒ maze_worker 提前收工、打印可区分（不空转整班）",
         test_worker_exits_on_low_weird),
    ]
    npass = 0
    nfail = 0
    for name, fn in cases:
        errs = fn()
        if errs:
            nfail = nfail + 1
            print("FAIL", name)
            for e in errs:
                print("    !", e)
        else:
            npass = npass + 1
            print("PASS", name)
    print("=" * 72)
    print("结果：PASS %d / FAIL %d" % (npass, nfail))
    return 0 if nfail == 0 else 1


sys.exit(main())
