# 植物大战丧尸随机版

纯 Python、纯文字的植物大战丧尸随机塔防，入口是一个单函数：

```python
from random_imitator_td import cmd

print(cmd("new_game level=1 seed=demo"))
print(cmd("cards 模仿者 模仿者 模仿者 模仿者 向日葵 窝瓜"))
print(cmd("种 模仿者 3-4; 种 向日葵 2-3"))
print(cmd("等待"))
```

也可以直接命令行运行：

```bash
python3 -m random_imitator_td help
python3 -m random_imitator_td new_game level=1 seed=demo
python3 -m random_imitator_td '种 模仿者 3-4; 种 向日葵 2-3'
```

新局第一步是编辑卡槽，配置好 `cards ...` 后才进入棋盘结算。

```text
提示: 模仿者越多，随机味越足。
```

每 5 次玩家决策会先正常执行并保存；下一次本该继续推进的游戏结果会换成防沉迷暂停，不推进新动作、不结算输赢，暂停只消费一次，之后可继续玩。
无参数启动、`打开`、`继续`、`look` 都会优先读取当前存档；只有显式 `new_game` 才会重开。
如果上一局已经胜利、失败或主动结束，下一次 `打开` / `继续` 会直接覆盖为 lv1 新局准备；玩家用 `note ...` 写下的复盘会跨局保留。

## 单游戏接入

这个目录可以作为类似 `games/<name>/` 的单游戏模块使用：

- `manifest.json`：游戏元数据。
- `engine.py`：暴露 `cmd(text) -> str`。
- `game/`：核心规则、结算、观察、随机池。
- `data/`：植物、僵尸、开奖池数据。

不需要大厅层；外部框架只要 import `random_imitator_td.engine.cmd` 或复制本目录并调用 `engine.cmd(text)`。

## 命令

```text
help
status
look / 打开 / 继续
new_game level=1 seed=demo
cards 模仿者 模仿者 模仿者 模仿者 向日葵 窝瓜
种 模仿者 3-4; 种 向日葵 2-3
铲 3-4
等待
结束本局
note 第一局自己的复盘
```

## 存档

默认存档为当前目录下的 `random_imitator_td_save.json`。可以用环境变量改位置：

```bash
RANDOM_IMITATOR_TD_SAVE=/tmp/random_imitator_td_save.json python3 -m random_imitator_td look
```

存档是 JSON，包含棋盘状态、事件日志、玩家复盘、回合历史和随机流快照。
