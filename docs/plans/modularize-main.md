# main.py 模块化方案（分四步，每步独立可回退）

> 现状：`main.py` ≈ 2000 行、BUILD 36；农场 32×32、14 个南瓜方阵、约 23/32 架工人。
> 目标：拆成"布局 / 工人 / 主控"三层，让改布局只改一处、改工人互不影响。

## 第 0 步（**阻塞项，必须先做**）：验证 import + spawn_drone

写两个临时小文件，5 分钟出结论：

```
# m_probe.py
CFG = [7]                     # 模块级可变状态
def who():
	CFG[0] = CFG[0] + 1
	print("[probe] CFG[0] =", CFG[0], "pos", get_pos_x(), get_pos_y())
```
```
# t_probe.py
import m_probe
print("[probe] parent before:", m_probe.CFG[0])
d = spawn_drone(m_probe.who)
wait_for(d)
print("[probe] parent after:", m_probe.CFG[0])
```

**判读**：
- 副机打印 `CFG[0] = 8`、主机 `after` 仍是 `7` ⇒ 副机**重新执行了 import**、且内存独立
  ⇒ **跨模块派无人机安全**，可以做第 3 步的工人拆分 ✓
- 副机报错 / 打印 `CFG[0] = 1`（列表是空的或初始值）⇒ import **没有**在副机里重跑
  ⇒ **永远不要跨文件派无人机** ✗；模块化只能做到"主控文件 + 纯函数库"（第 2 步），
  工人循环必须留在主控文件里。

## 第 1 步：删死代码（零结构风险，可读性收益最大）

现在文件里同时躺着两套以上的历史路径，它们不只是占行数，**本身就是陷阱**：
- `main4()` / `run_one_sweep4()` / `work_left()` / `work_right()`（4 架时代）
- `game_loop()`（单机时代）、`tend_sunflowers()`（向日葵 v1，用 `SUNFLOWER_W/H` 老几何）
- 旧 `work_pumpkin()` —— **它只数第 0 号方阵的 36 格**，误用就会出现"南瓜只收一片"的怪象
- `replant_pumpkin_band()`（兼容包装）、`init_board()` / `init_left()` / `init_right()`（旧初始化）

保留：`main8()` 一条路径、`sort_cacti()`（v2 的兜底）、`read_carrot_votes()`（虽然常驻循环不再调它，
但注释要写清"备而不用"）。**删完必须**：`py_compile` + `audit_save0.py`（能抓"删了但别处还在引用"）。

## 第 2 步：抽出 `layout.py`（纯数据 + 纯函数，零跨机状态 ⇒ 风险最低）

搬过去：
- 布局常数：`HALF / PUMPKIN_SIZE / PUMPKIN_SQUARES / PUMPKIN_OX / PUMPKIN_OY / SUN_ROWS /
  WOOD_ROWS / HAY_ROWS / CARROT_START / CARROT_END / BUF_ROWS`
- 区域判定：`in_wood_zone / in_hay_zone / in_carrot_zone / in_pumpkin_zone / in_sunflower_zone /
  in_buffer_zone / needs_soil / sun_row_x0`
- 它们是四个子系统的**单一事实来源**（改布局只改一处），而且**没有任何跨机状态** ✓

**注意**：若第 0 步判定"跨模块不可用"，则 `layout.py` 里的函数**不能被副机调用**（`work_carrot` 会调
`in_carrot_zone`）⇒ 那时只能把常数抽出去、判定函数留在主控文件里（或让主控预计算好区间再传参，
这也正是现在 `work_carrot(sweep, cy0, cy1)` 已经在做的事 —— 传参模式的天然好处）。

## 第 3 步（仅当第 0 步通过）：按工人拆

```
main.py          主控：main8 / report / try_upgrade / companion_survey / 入口分派
w_carrot.py      loop_carrot + work_carrot + tend_carrot_tile + plant_host
w_pumpkin.py     loop_pumpkin_smart + work_pumpkin_smart + replant_square + 状态表
w_sun.py         loop_sunflower + work_sunflower + 花瓣诊断
w_cactus.py      cactus_push / cactus_worker / 排序（v2 + v1 兜底）
maze_gold.py     已经是独立的 ✓（v32）
```

## 铁律（这一整轮踩出来的，别省）

1. 改脚本**只用 `edit`/`write` 或 Python**（显式 UTF-8 + `newline="\n"`）；**绝不用 PowerShell 往返**
   （两次事故：吞掉 13 行、把 `while True:` 删掉）。
2. 改前**重读文件**（游戏每跑完一次会回写 `.py`）。
3. 一次改完立刻三连验证：`py_compile` + `audit_save0.py` + **布局改动必跑方阵间距自检**
   （两两比对，要求 x 或 y 至少隔 7；BUILD 26 就是漏了这个才让两块连成 12×6 矩形）。
4. 每个文件都带自己的版本标记（`BUILD` / `v32` 之类），启动时打印 —— 游戏会缓存编辑器缓冲区，
   没有版本号就无法确认跑的是哪一版。
5. 删代码 / 拆模块**分次提交**，每次都能跑、能回退；不要在一次里既删路径又换结构。
