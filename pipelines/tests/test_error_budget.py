"""Unit tests for the shared error-budget gate."""

import logging

import pytest

from countyiq.lib.error_budget import check_error_budget

log = logging.getLogger("test")


def test_all_failures_raises():
    with pytest.raises(RuntimeError, match="error budget exceeded"):
        check_error_budget(log, label="pass2", errors=100, total=100)


def test_majority_failures_raises():
    with pytest.raises(RuntimeError):
        check_error_budget(log, label="pass2", errors=40, total=100)


def test_minor_failures_pass():
    check_error_budget(log, label="pass2", errors=5, total=100)


def test_zero_errors_pass():
    check_error_budget(log, label="pass2", errors=0, total=100)


def test_tiny_runs_never_raise():
    # 2/3 failed but total < min_total — a tiny run shouldn't hard-fail.
    check_error_budget(log, label="pass2", errors=2, total=3)


def test_zero_total_never_raises():
    check_error_budget(log, label="pass2", errors=0, total=0)


def test_env_override(monkeypatch):
    monkeypatch.setenv("COUNTYIQ_ERROR_BUDGET", "0.9")
    check_error_budget(log, label="pass2", errors=80, total=100)
    monkeypatch.setenv("COUNTYIQ_ERROR_BUDGET", "0.05")
    with pytest.raises(RuntimeError):
        check_error_budget(log, label="pass2", errors=10, total=100)
