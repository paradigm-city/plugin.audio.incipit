"""AI Mix Assist: misfit of tracks against the seed, weighted by what makes the seed unusual, scaled by the mix's spread."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from mixassist.dimensions import ALL_KEYS, DIMENSIONS, ERA_KEY, label_for
from mixassist.stats import correlation_matrix, invert, median, robust_spread

# The smallest spread a mix can have per dimension: about the rating noise, so a very tight mix
# does not turn every small difference into an outlier.
SPREAD_FLOORS = {key: 1.0 for key in ALL_KEYS}
SPREAD_FLOORS[ERA_KEY] = 5.0

# Mix the library correlations with independence, so rare value combinations are not over-amplified.
CORRELATION_SHRINKAGE = 0.3


def mix_centre(vectors: List[Dict[str, float]], keys: Sequence[str] = ALL_KEYS) -> Dict[str, float]:
    return {key: median([vector[key] for vector in vectors]) for key in keys}


def blend(first: Dict[str, float], second: Dict[str, float], weight: float = 0.5) -> Dict[str, float]:
    return {key: (1 - weight) * first[key] + weight * second[key] for key in first}


def mix_spreads(vectors: List[Dict[str, float]], keys: Sequence[str] = ALL_KEYS) -> Dict[str, float]:
    return {key: robust_spread([vector[key] for vector in vectors], SPREAD_FLOORS.get(key, 1.0)) for key in keys}


def inverse_correlation(
    library_vectors: List[Dict[str, float]], keys: Sequence[str] = ALL_KEYS, shrinkage: float = CORRELATION_SHRINKAGE
) -> List[List[float]]:
    """Inverse of the shrunk library correlation matrix; the identity when there is too little data."""
    size = len(keys)
    identity = [[1.0 if i == j else 0.0 for j in range(size)] for i in range(size)]
    if len(library_vectors) < size * 5:
        return identity
    correlation = correlation_matrix(library_vectors, keys)
    shrunk = [
        [(1 - shrinkage) * (value if value == value else 0.0) + shrinkage * identity[i][j] for j, value in enumerate(row)]
        for i, row in enumerate(correlation)
    ]
    return invert(shrunk)


def misfit(
    vector: Dict[str, float],
    reference: Dict[str, float],
    spreads: Dict[str, float],
    inverse: Optional[List[List[float]]] = None,
    keys: Sequence[str] = ALL_KEYS,
) -> Tuple[float, Dict[str, float]]:
    """(misfit, deviation per dimension). The misfit is in units of the mix's spread, averaged over dimensions."""
    deviations = {key: (vector[key] - reference[key]) / spreads[key] for key in keys}
    z = [deviations[key] for key in keys]
    if inverse is None:
        squared = sum(value * value for value in z)
    else:
        squared = sum(z[i] * inverse[i][j] * z[j] for i in range(len(z)) for j in range(len(z)))
    return math.sqrt(max(squared, 0.0) / len(keys)), deviations


def seed_weights(seed: Dict[str, float], library: List[Dict[str, float]],
                 keys: Sequence[str] = ALL_KEYS) -> Dict[str, float]:
    """How unusual the seed is on each dimension (in library standard deviations), scaled to average 1.

    The dimensions on which the seed stands out carry the intent of the mix; the others count less.
    Without a library every dimension weighs 1.
    """
    if len(library) < 2:
        return {key: 1.0 for key in keys}
    raw = {}
    for key in keys:
        values = [vector[key] for vector in library]
        centre = sum(values) / len(values)
        spread = (sum((value - centre) ** 2 for value in values) / (len(values) - 1)) ** 0.5 or 1.0
        raw[key] = max(0.1, abs(seed[key] - centre) / spread)
    scale = sum(raw.values()) / len(raw)
    return {key: value / scale for key, value in raw.items()}


def weighted_spreads(spreads: Dict[str, float], weights: Dict[str, float]) -> Dict[str, float]:
    """Dividing a spread by a weight makes deviations on that dimension count proportionally more."""
    return {key: spreads[key] / max(weights.get(key, 1.0), 0.1) for key in spreads}


def reason(vector: Dict[str, float], reference: Dict[str, float], deviations: Dict[str, float], top: int = 2) -> str:
    """The largest deviations in words, e.g. 'temperature: glowing vs. cool; sounding year: 1979 vs. 2004'."""
    parts = []
    for key in sorted(deviations, key=lambda name: -abs(deviations[name]))[:top]:
        if abs(deviations[key]) < 1.0:
            break
        name = "sounding year" if key == ERA_KEY else next(d.key for d in DIMENSIONS if d.key == key)
        if key == ERA_KEY:
            parts.append(f"{name}: {vector[key]:.0f} vs. {reference[key]:.0f}")
        else:
            parts.append(f"{name}: {label_for(key, vector[key])} vs. {label_for(key, reference[key])}")
    return "; ".join(parts)
