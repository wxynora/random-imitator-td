# 植物大战丧尸随机版

A pure-Python text tower-defense game for AI players. The public integration surface is one function:

```python
from random_imitator_td import cmd

print(cmd("new_game level=1 seed=demo"))
print(cmd("cards 模仿者 模仿者 模仿者 模仿者 向日葵 窝瓜"))
print(cmd("种 模仿者 3-4; 种 向日葵 2-3"))
```

The first step of a new run is card-slot editing. The game will not start resolving the board until the player configures cards.

```text
提示: 模仿者越多，随机味越足。
```

每 5 次玩家决策会先正常执行并保存；下一次本该继续推进的游戏结果会换成防沉迷暂停，不推进新动作、不结算输赢，暂停只消费一次，之后可继续玩。
无参数启动、`打开`、`继续`、`look` 都会优先读取当前存档；只有显式 `new_game` 才会重开。
如果上一局胜利，下一次 `打开` / `继续` 会准备下一关并重新选卡；失败或主动结束会回到 lv1 新局准备。玩家用 `note ...` 写下的复盘会跨局保留。

## CLI

```bash
python3 -m random_imitator_td help
python3 -m random_imitator_td new_game level=1 seed=demo
python3 -m random_imitator_td 'cards 模仿者 模仿者 模仿者 模仿者 向日葵 窝瓜'
python3 -m random_imitator_td '种 模仿者 3-4; 种 向日葵 2-3'
```

## Single-Game Adapter

The package can be used as a single game directory:

- `random_imitator_td/manifest.json`: game metadata.
- `random_imitator_td/engine.py`: exposes `cmd(text) -> str`.
- `random_imitator_td/game/`: core rules and simulation.
- `random_imitator_td/data/`: plants, zombies, and reveal pools.

No lobby framework is required. External runners can import `random_imitator_td.engine.cmd`.

## Commands

```text
help
status
look / 打开 / 继续
new_game level=1 seed=demo
cards 模仿者 模仿者 模仿者 模仿者 向日葵 窝瓜
种 模仿者 3-4; 种 向日葵 2-3
铲 3-4
等待
等待 200
结束本局
note 第一局自己的复盘
recap
```

## Save File

By default, the game writes `random_imitator_td_save.json` in the current working directory. Override it with:

```bash
RANDOM_IMITATOR_TD_SAVE=/tmp/random_imitator_td_save.json python3 -m random_imitator_td look
```

The save file is JSON and stores board state, event log, card slots, round history, player notes, and RNG snapshots.

## Tests

```bash
python3 -m unittest discover -s tests
```
