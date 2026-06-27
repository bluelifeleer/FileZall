from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class PerformanceResult[T]:
    name: str
    elapsed_ms: float
    value: T


@dataclass(frozen=True)
class PerformanceBudgetCheck:
    name: str
    passed: bool
    elapsed_ms: float
    max_elapsed_ms: float
    message: str


@dataclass(frozen=True)
class PerformanceBudget:
    name: str
    max_elapsed_ms: float

    def check(self, result: PerformanceResult[object]) -> PerformanceBudgetCheck:
        passed = result.elapsed_ms <= self.max_elapsed_ms
        message = (
            f"{result.name} completed within {self.max_elapsed_ms:.2f} ms"
            if passed
            else (
                f"{result.name} took {result.elapsed_ms:.2f} ms "
                f"and exceeded {self.max_elapsed_ms:.2f} ms"
            )
        )
        return PerformanceBudgetCheck(
            name=self.name,
            passed=passed,
            elapsed_ms=result.elapsed_ms,
            max_elapsed_ms=self.max_elapsed_ms,
            message=message,
        )


def measure_operation(name: str, operation: Callable[[], T]) -> PerformanceResult[T]:
    started = perf_counter()
    value = operation()
    elapsed_ms = (perf_counter() - started) * 1000
    return PerformanceResult(name=name, elapsed_ms=elapsed_ms, value=value)
