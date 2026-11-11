"""Small random-choice helpers used across the generator. Synthetic data, fictional company."""

import zlib
from datetime import date, datetime, timedelta

import numpy as np


def pick(rng: np.random.Generator, options: list):
    """Pick one item from a list, all equally likely."""
    return options[int(rng.integers(len(options)))]


def weighted_pick(rng: np.random.Generator, weights: dict):
    """Pick one key from {key: weight}. Bigger weight = more likely."""
    keys = list(weights)
    probs = np.array([weights[k] for k in keys], dtype=float)
    return keys[int(rng.choice(len(keys), p=probs / probs.sum()))]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def at_time(day: date, rng: np.random.Generator, from_hour: int, to_hour: int) -> datetime:
    """A random moment on `day` between two hours (UTC)."""
    seconds = int(rng.integers(from_hour * 3600, to_hour * 3600))
    return datetime(day.year, day.month, day.day) + timedelta(seconds=seconds)


def stable_uniform(key: str, salt: str) -> float:
    """A number between 0 and 1 that is always the same for the same key.

    Used where a decision must not change between runs or between days,
    for example "is this contact one of the deliberately duplicated ones?".
    """
    return zlib.crc32(f"{salt}:{key}".encode()) / 2**32
