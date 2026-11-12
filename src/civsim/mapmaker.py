"""Builds, checks and draws the hand-drawn maps.

    .venv/bin/python -m civsim.mapmaker check [map ...]     # build and list what breaks the drawing
    .venv/bin/python -m civsim.mapmaker bake [map ...]      # build, check, and save into civsim/data/maps
    .venv/bin/python -m civsim.mapmaker preview DIR [map ...]   # PNG pictures of the saved maps

With no map named, every drawn map.
"""

import argparse
import sys
from pathlib import Path

from .map.blueprint import build, check
from .map.designs import DESIGNS, blueprint
from .map.preview import png
from .map.saved import load_map, map_path, save


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="civsim.mapmaker")
    parser.add_argument("action", choices=["check", "bake", "preview"])
    parser.add_argument("rest", nargs="*")
    args = parser.parse_args(argv)
    rest = list(args.rest)
    out = Path(rest.pop(0)) if args.action == "preview" else None
    ids = rest or DESIGNS
    failed = False
    for map_id in ids:
        if args.action == "preview":
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{map_id}.png").write_bytes(png(load_map(map_id)))
            print(f"{map_id}: {out / (map_id + '.png')}")
            continue
        bp = blueprint(map_id)
        world = build(bp)
        problems = check(world, bp)
        land = sum(1 for t in range(len(world.biomes)) if not world.is_water(t))
        print(f"{map_id}: {bp.width}x{bp.height}, {land} land tiles, {len(world.regions)} regions, "
              f"{len(world.mines)} mines, {len(problems)} problems")
        for problem in problems:
            print(f"  - {problem}")
        failed |= bool(problems)
        if args.action == "bake" and not problems:
            save(world, map_path(map_id))
            print(f"  saved {map_path(map_id)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
