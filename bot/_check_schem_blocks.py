import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from simulator.buildings import CATALOG

blocks = ["silicon-smelter", "power-node", "item-source", "bridge-conveyor",
          "sorter", "junction", "overflow-gate", "router", "item-void", "battery"]
for name in blocks:
    b = CATALOG.get(name)
    if b is None:
        print(f"{name}: KHÔNG CÓ trong CATALOG")
    else:
        print(f"{name}: kind={b.kind}, category={b.category}")
