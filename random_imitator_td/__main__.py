from __future__ import annotations

import sys

from .engine import cmd


def main() -> None:
    if len(sys.argv) > 1:
        print(cmd(" ".join(sys.argv[1:])))
        return
    print(cmd(""))


if __name__ == "__main__":
    main()
