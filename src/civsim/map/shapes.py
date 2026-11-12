"""Shapes for drawing maps by hand, in tile coordinates.

A shape answers whether a point lies inside it. Tiles are tested at their centres
(x + 0.5, y + 0.5). Angles are compass bearings in degrees: 0 is north (up the map, towards
y = 0), 90 is east, measured clockwise.
"""

import math
from dataclasses import dataclass


class Shape:
    def contains(self, x: float, y: float) -> bool:
        raise NotImplementedError

    def __or__(self, other: "Shape") -> "Shape":
        return Union((self, other))

    def __sub__(self, other: "Shape") -> "Shape":
        return Minus(self, other)

    def __and__(self, other: "Shape") -> "Shape":
        return Both(self, other)


def bearing(cx: float, cy: float, x: float, y: float) -> float:
    """Compass bearing of (x, y) seen from (cx, cy), in [0, 360)."""
    return math.degrees(math.atan2(x - cx, cy - y)) % 360


def towards(cx: float, cy: float, angle: float, distance: float) -> tuple[float, float]:
    """The point `distance` away from (cx, cy) on a compass bearing."""
    a = math.radians(angle)
    return cx + distance * math.sin(a), cy - distance * math.cos(a)


@dataclass(frozen=True)
class Circle(Shape):
    cx: float
    cy: float
    r: float

    def contains(self, x, y):
        return (x - self.cx) ** 2 + (y - self.cy) ** 2 <= self.r ** 2


@dataclass(frozen=True)
class Ellipse(Shape):
    cx: float
    cy: float
    rx: float
    ry: float

    def contains(self, x, y):
        return ((x - self.cx) / self.rx) ** 2 + ((y - self.cy) / self.ry) ** 2 <= 1.0


@dataclass(frozen=True)
class Rect(Shape):
    x0: float
    y0: float
    x1: float
    y1: float

    def contains(self, x, y):
        return self.x0 <= x < self.x1 and self.y0 <= y < self.y1


@dataclass(frozen=True)
class Polygon(Shape):
    points: tuple[tuple[float, float], ...]

    def contains(self, x, y):
        inside = False
        pts = self.points
        j = len(pts) - 1
        for i in range(len(pts)):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
        return inside


@dataclass(frozen=True)
class Sector(Shape):
    """Part of a ring: between radii r0 and r1, from bearing a0 clockwise to a1."""
    cx: float
    cy: float
    r0: float
    r1: float
    a0: float
    a1: float

    def contains(self, x, y):
        d2 = (x - self.cx) ** 2 + (y - self.cy) ** 2
        if not self.r0 ** 2 <= d2 <= self.r1 ** 2:
            return False
        span = (self.a1 - self.a0) % 360 or 360
        return (bearing(self.cx, self.cy, x, y) - self.a0) % 360 < span


@dataclass(frozen=True)
class Band(Shape):
    """Every point within width / 2 of a line through the points."""
    points: tuple[tuple[float, float], ...]
    width: float

    def contains(self, x, y):
        return distance_to_line(self.points, x, y) <= self.width / 2


@dataclass(frozen=True)
class Union(Shape):
    parts: tuple[Shape, ...]

    def contains(self, x, y):
        return any(p.contains(x, y) for p in self.parts)


@dataclass(frozen=True)
class Minus(Shape):
    keep: Shape
    cut: Shape

    def contains(self, x, y):
        return self.keep.contains(x, y) and not self.cut.contains(x, y)


@dataclass(frozen=True)
class Both(Shape):
    a: Shape
    b: Shape

    def contains(self, x, y):
        return self.a.contains(x, y) and self.b.contains(x, y)


def union(*parts: Shape) -> Shape:
    return Union(tuple(parts))


def distance_to_line(points, x: float, y: float) -> float:
    best = float("inf")
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length2))
        px, py = ax + t * dx, ay + t * dy
        best = min(best, math.hypot(x - px, y - py))
    return best
