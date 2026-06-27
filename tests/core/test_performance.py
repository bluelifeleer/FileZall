from filezall_core.performance import PerformanceBudget, measure_operation


def test_measure_operation_returns_result_and_elapsed_time() -> None:
    result = measure_operation("fast operation", lambda: "ok")

    assert result.name == "fast operation"
    assert result.value == "ok"
    assert result.elapsed_ms >= 0


def test_performance_budget_reports_pass_and_fail_without_raising() -> None:
    passing = PerformanceBudget(name="fast operation", max_elapsed_ms=100)
    failing = PerformanceBudget(name="fast operation", max_elapsed_ms=0)
    result = measure_operation("fast operation", lambda: "ok")

    pass_check = passing.check(result)
    fail_check = failing.check(result)

    assert pass_check.passed is True
    assert pass_check.message == "fast operation completed within 100.00 ms"
    assert fail_check.passed is False
    assert "exceeded 0.00 ms" in fail_check.message
