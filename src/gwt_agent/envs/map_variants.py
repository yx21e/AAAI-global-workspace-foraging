from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple


FLOOR = 0
WALL = 1
DIFFICULTY2_FIVE = "difficulty2-five"
QIYUAN_DEFAULT = "qiyuan-default"
AUTO = "auto"

Position = Tuple[int, int]
Grid = List[List[int]]


@dataclass(frozen=True)
class MapVariant:
    preset: str
    variant_id: int
    name: str
    grid: Grid
    base_pos: Position
    resource_pos: Position

    @property
    def obstacle_count(self) -> int:
        return sum(
            1
            for y, row in enumerate(self.grid)
            for x, value in enumerate(row)
            if value == WALL and not _is_border(self.grid, x, y)
        )

    def metadata(self) -> dict:
        return {
            "preset": self.preset,
            "variant": self.variant_id,
            "name": self.name,
            "base_pos": list(self.base_pos),
            "resource_pos": list(self.resource_pos),
            "obstacle_count": self.obstacle_count,
            "grid_size": len(self.grid),
        }


DIFFICULTY2_ASCII_MAPS = [
    (
        "northwest-base-east-resource",
        [
            "###############",
            "#B....#.......#",
            "#.....#...#...#",
            "#.....#...#...#",
            "#..#..........#",
            "#...##........#",
            "#.........##..#",
            "#.....#.......#",
            "#.....#...#...#",
            "#.........#...#",
            "#..##.........#",
            "#......#......#",
            "#...#.....#R..#",
            "#....#........#",
            "###############",
        ],
    ),
    (
        "northeast-base-southwest-resource",
        [
            "###############",
            "#.........B...#",
            "#..#..........#",
            "#..#.....##...#",
            "#.......#.....#",
            "#....#.....#..#",
            "#....#..#.....#",
            "#..#....#.....#",
            "#..##.........#",
            "#...........#.#",
            "#.....#.....#.#",
            "#.....#..#....#",
            "#..R......##..#",
            "#.....#...#...#",
            "###############",
        ],
    ),
    (
        "southwest-base-northeast-resource",
        [
            "###############",
            "#.....#.....R.#",
            "#....##.......#",
            "#..#....#.....#",
            "#..#.....#....#",
            "#..#.....#....#",
            "#.......##....#",
            "#...#.........#",
            "#....#........#",
            "#....#....##..#",
            "#.........#...#",
            "#..##.....#...#",
            "#B.........#..#",
            "#.....#.......#",
            "###############",
        ],
    ),
    (
        "central-base-southeast-resource",
        [
            "###############",
            "#....#........#",
            "#..##.........#",
            "#.......#.....#",
            "#.......#..#..#",
            "#..#......#...#",
            "#..#....#.....#",
            "#......B#.....#",
            "#..#..........#",
            "#....##.......#",
            "#....#....#...#",
            "#...#..#..#...#",
            "#...#.#.....R.#",
            "#.......#.....#",
            "###############",
        ],
    ),
    (
        "southeast-base-northwest-resource",
        [
            "###############",
            "#..R..........#",
            "#......#...#..#",
            "#..#...#......#",
            "#..#....#.....#",
            "#.........##..#",
            "#.....#....#..#",
            "#.....#..#....#",
            "#........#....#",
            "#..##.........#",
            "#...#.........#",
            "#..#...#......#",
            "#......#...B..#",
            "#.............#",
            "###############",
        ],
    ),
]


def resolve_map_variant(
    *,
    preset: str = AUTO,
    difficulty: int = 1,
    variant: Optional[object] = AUTO,
    seed: Optional[int] = None,
) -> Optional[MapVariant]:
    resolved_preset = preset or AUTO
    if resolved_preset == AUTO:
        if difficulty != 2:
            return None
        resolved_preset = DIFFICULTY2_FIVE
    if resolved_preset == QIYUAN_DEFAULT:
        return None
    if resolved_preset != DIFFICULTY2_FIVE:
        raise ValueError(
            f"Unknown map preset {preset!r}. "
            f"Expected {AUTO!r}, {QIYUAN_DEFAULT!r}, or {DIFFICULTY2_FIVE!r}."
        )
    variants = difficulty2_variants()
    variant_id = resolve_variant_id(variant=variant, seed=seed, count=len(variants))
    return variants[variant_id]


def resolve_variant_id(*, variant: Optional[object], seed: Optional[int], count: int) -> int:
    if variant is None or str(variant).strip().lower() == AUTO:
        return int(seed or 0) % count
    try:
        variant_id = int(variant)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"map variant must be {AUTO!r} or an integer 0-{count - 1}") from exc
    if variant_id < 0 or variant_id >= count:
        raise ValueError(f"map variant must be between 0 and {count - 1}; got {variant_id}")
    return variant_id


def difficulty2_variants() -> List[MapVariant]:
    return [
        parse_ascii_variant(
            preset=DIFFICULTY2_FIVE,
            variant_id=variant_id,
            name=name,
            rows=rows,
        )
        for variant_id, (name, rows) in enumerate(DIFFICULTY2_ASCII_MAPS)
    ]


def apply_map_variant_to_env(env, variant: MapVariant) -> dict:
    env.grid_size = len(variant.grid)
    env.grid = [row[:] for row in variant.grid]
    env.base_pos = tuple(variant.base_pos)
    env.agent_pos = list(variant.base_pos)
    env.facing = "RIGHT"
    env.resource_pos = list(variant.resource_pos)
    env.carrying = False
    env.step_count = 0
    env.resources_collected = 0
    if hasattr(env, "_state"):
        return env._state()
    return {
        "agent_pos": tuple(env.agent_pos),
        "facing": env.facing,
        "resource_pos": tuple(env.resource_pos),
        "base_pos": env.base_pos,
        "carrying": env.carrying,
        "action_success": True,
        "step_count": env.step_count,
        "resources_collected": env.resources_collected,
    }


def parse_ascii_variant(
    *,
    preset: str,
    variant_id: int,
    name: str,
    rows: Iterable[str],
) -> MapVariant:
    clean_rows = [row.rstrip("\n") for row in rows]
    if not clean_rows:
        raise ValueError("map variant cannot be empty")
    width = len(clean_rows[0])
    if any(len(row) != width for row in clean_rows):
        raise ValueError(f"map variant {name!r} has inconsistent row widths")

    base_pos = None
    resource_pos = None
    grid: Grid = []
    for y, row in enumerate(clean_rows):
        grid_row = []
        for x, char in enumerate(row):
            if char == "#":
                grid_row.append(WALL)
            elif char == ".":
                grid_row.append(FLOOR)
            elif char == "B":
                if base_pos is not None:
                    raise ValueError(f"map variant {name!r} has more than one base")
                base_pos = (x, y)
                grid_row.append(FLOOR)
            elif char == "R":
                if resource_pos is not None:
                    raise ValueError(f"map variant {name!r} has more than one resource")
                resource_pos = (x, y)
                grid_row.append(FLOOR)
            else:
                raise ValueError(f"map variant {name!r} has unsupported tile {char!r}")
        grid.append(grid_row)

    if base_pos is None or resource_pos is None:
        raise ValueError(f"map variant {name!r} must include one B and one R")
    if not all_floor_reachable(grid, base_pos):
        raise ValueError(f"map variant {name!r} has unreachable floor cells")
    return MapVariant(
        preset=preset,
        variant_id=variant_id,
        name=name,
        grid=grid,
        base_pos=base_pos,
        resource_pos=resource_pos,
    )


def all_floor_reachable(grid: Grid, start: Position) -> bool:
    sx, sy = start
    if grid[sy][sx] == WALL:
        return False
    visited = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = x + dx, y + dy
            if ny < 0 or nx < 0 or ny >= len(grid) or nx >= len(grid[ny]):
                continue
            if grid[ny][nx] == WALL or (nx, ny) in visited:
                continue
            visited.add((nx, ny))
            queue.append((nx, ny))
    return all(
        (x, y) in visited
        for y, row in enumerate(grid)
        for x, value in enumerate(row)
        if value == FLOOR
    )


def _is_border(grid: Grid, x: int, y: int) -> bool:
    return y == 0 or x == 0 or y == len(grid) - 1 or x == len(grid[y]) - 1
