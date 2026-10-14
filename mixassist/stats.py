"""AI Mix Assist: small statistics helpers in plain Python (a mix and the library reference are a few hundred vectors)."""

from __future__ import annotations

import math
from typing import Dict, List, Sequence


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0

def stdev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    centre = mean(values)
    return math.sqrt(sum((value - centre) ** 2 for value in values) / (len(values) - 1))

def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) < 3:
        return float("nan")
    mx, my = mean(xs), mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)

def correlation_matrix(vectors: List[Dict[str, float]], keys: Sequence[str]) -> List[List[float]]:
    columns = {key: [vector[key] for vector in vectors] for key in keys}
    return [[pearson(columns[a], columns[b]) if a != b else 1.0 for b in keys] for a in keys]

def median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2

def robust_spread(values: Sequence[float], floor: float) -> float:
    """1.4826 x median absolute deviation (a standard deviation that ignores outliers), at least `floor`."""
    centre = median(values)
    return max(floor, 1.4826 * median([abs(value - centre) for value in values]))

def invert(matrix: List[List[float]]) -> List[List[float]]:
    """Inverse of a small square matrix (Gauss-Jordan with partial pivoting)."""
    size = len(matrix)
    work = [list(row) + [1.0 if i == j else 0.0 for j in range(size)] for i, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(work[row][column]))
        if abs(work[pivot][column]) < 1e-12:
            raise ValueError("matrix is singular")
        work[column], work[pivot] = work[pivot], work[column]
        factor = work[column][column]
        work[column] = [value / factor for value in work[column]]
        for row in range(size):
            if row != column and work[row][column]:
                scale = work[row][column]
                work[row] = [value - scale * pivot_value for value, pivot_value in zip(work[row], work[column])]
    return [row[size:] for row in work]
