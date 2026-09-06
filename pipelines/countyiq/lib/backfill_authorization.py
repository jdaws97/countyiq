"""Durable, cross-run spend authorization for paid intelligence backfills.

The normal pass budget protects one Dagster invocation. A backfill can span
several invocations, so reservations are persisted before provider dispatch.
A crashed worker leaves its reservation charged until an operator reconciles
it, preventing an accidental restart from spending the same allowance again.
"""

from __future__ import annotations

import fcntl
import json
import math
import os
import tempfile
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

AUTHORIZATION_SCHEMA_VERSION = 1


class BackfillAuthorizationError(RuntimeError):
    """The durable authorization is missing, invalid, mismatched, or exhausted."""


_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.Lock] = {}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _money(value: object, label: str, *, positive: bool) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise BackfillAuthorizationError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed) or parsed < 0 or (positive and parsed == 0):
        qualifier = "positive" if positive else "non-negative"
        raise BackfillAuthorizationError(f"{label} must be {qualifier} and finite")
    return parsed


def _thread_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.Lock())


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    """Lock a stable sidecar inode across threads and worker processes."""

    lock_path = Path(f"{path}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _thread_lock(lock_path), lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _with_totals(payload: dict, path: Path) -> dict:
    reservations = payload.get("reservations") or {}
    reserved = sum(
        _money(item.get("amount_usd"), "reservation amount", positive=True)
        for item in reservations.values()
    )
    spent = _money(payload.get("spent_usd", 0), "spent_usd", positive=False)
    maximum = _money(payload.get("max_cost_usd"), "max_cost_usd", positive=True)
    return {
        **payload,
        "path": str(path),
        "reserved_usd": round(reserved, 12),
        "committed_usd": round(spent + reserved, 12),
        "remaining_usd": round(max(0.0, maximum - spent - reserved), 12),
    }


def create_backfill_authorization(
    path: Path,
    *,
    pass_number: int,
    model: str,
    max_cost_usd: float,
    max_price_prompt: float,
    max_price_completion: float,
) -> dict:
    """Create one authorization without overwriting an earlier ledger."""

    path = path.expanduser().resolve()
    if pass_number not in range(4):
        raise BackfillAuthorizationError("pass_number must be one of 0, 1, 2, or 3")
    if not model.strip():
        raise BackfillAuthorizationError("model is required")
    maximum = _money(max_cost_usd, "max_cost_usd", positive=True)
    prompt_price = _money(max_price_prompt, "max_price_prompt", positive=True)
    completion_price = _money(
        max_price_completion, "max_price_completion", positive=True
    )
    with _exclusive_lock(path):
        if path.exists():
            raise BackfillAuthorizationError(
                f"authorization already exists and will not be overwritten: {path}"
            )
        now = _utc_now()
        payload = {
            "schema_version": AUTHORIZATION_SCHEMA_VERSION,
            "authorization_id": str(uuid.uuid4()),
            "pass_number": pass_number,
            "model": model.strip(),
            "max_cost_usd": maximum,
            "max_price_prompt": prompt_price,
            "max_price_completion": completion_price,
            "spent_usd": 0.0,
            "reservations": {},
            "created_at": now,
            "updated_at": now,
        }
        _write_atomic(path, payload)
    return _with_totals(payload, path)


class BackfillAuthorization:
    """Validate and atomically debit one durable authorization file."""

    def __init__(
        self,
        path: Path,
        *,
        pass_number: int,
        model: str,
        max_cost_usd: float,
        max_price_prompt: float,
        max_price_completion: float,
    ) -> None:
        self.path = path.expanduser().resolve()
        self.expected = {
            "pass_number": pass_number,
            "model": model,
            "max_cost_usd": max_cost_usd,
            "max_price_prompt": max_price_prompt,
            "max_price_completion": max_price_completion,
        }

    def _read_validated(self) -> dict:
        if not self.path.is_file():
            raise BackfillAuthorizationError(
                f"backfill authorization file does not exist: {self.path}"
            )
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BackfillAuthorizationError(
                f"cannot read backfill authorization: {exc}"
            ) from exc
        if payload.get("schema_version") != AUTHORIZATION_SCHEMA_VERSION:
            raise BackfillAuthorizationError("unsupported authorization schema_version")
        for field in ("pass_number", "model"):
            if payload.get(field) != self.expected[field]:
                raise BackfillAuthorizationError(
                    f"authorization {field} does not match runtime "
                    f"({payload.get(field)!r} != {self.expected[field]!r})"
                )
        for field in (
            "max_cost_usd",
            "max_price_prompt",
            "max_price_completion",
        ):
            stored = _money(payload.get(field), field, positive=True)
            expected = _money(self.expected[field], field, positive=True)
            if not math.isclose(stored, expected, rel_tol=0, abs_tol=1e-12):
                raise BackfillAuthorizationError(
                    f"authorization {field} does not match runtime "
                    f"({stored} != {expected})"
                )
        _money(payload.get("spent_usd", 0), "spent_usd", positive=False)
        if not isinstance(payload.get("reservations"), dict):
            raise BackfillAuthorizationError(
                "authorization reservations must be an object"
            )
        _with_totals(payload, self.path)
        return payload

    def snapshot(self) -> dict:
        with _exclusive_lock(self.path):
            return _with_totals(self._read_validated(), self.path)

    def reserve(self, amount_usd: float) -> str:
        amount = _money(amount_usd, "reservation amount", positive=True)
        with _exclusive_lock(self.path):
            payload = self._read_validated()
            totals = _with_totals(payload, self.path)
            if totals["committed_usd"] + amount > payload["max_cost_usd"] + 1e-12:
                raise BackfillAuthorizationError(
                    "cumulative backfill authorization exhausted: "
                    f"committed=${totals['committed_usd']:.6f}, "
                    f"next_max=${amount:.6f}, limit=${payload['max_cost_usd']:.6f}"
                )
            reservation_id = str(uuid.uuid4())
            payload["reservations"][reservation_id] = {
                "amount_usd": amount,
                "created_at": _utc_now(),
            }
            payload["updated_at"] = _utc_now()
            _write_atomic(self.path, payload)
            return reservation_id

    def settle(self, reservation_id: str, actual_cost_usd: float) -> dict:
        actual = _money(actual_cost_usd, "actual_cost_usd", positive=False)
        return self._finish(reservation_id, charged_usd=actual)

    def forfeit(self, reservation_id: str) -> dict:
        """Charge the full reservation when provider cost cannot be verified."""

        return self._finish(reservation_id, charged_usd=None)

    def cancel(self, reservation_id: str) -> dict:
        """Release a reservation only when no provider call was dispatched."""

        return self._finish(reservation_id, charged_usd=0.0)

    def _finish(self, reservation_id: str, *, charged_usd: float | None) -> dict:
        with _exclusive_lock(self.path):
            payload = self._read_validated()
            reservation = payload["reservations"].pop(reservation_id, None)
            if reservation is None:
                raise BackfillAuthorizationError(
                    f"unknown or already settled reservation: {reservation_id}"
                )
            reserved = _money(
                reservation.get("amount_usd"), "reservation amount", positive=True
            )
            charge = reserved if charged_usd is None else charged_usd
            payload["spent_usd"] = round(
                _money(payload.get("spent_usd", 0), "spent_usd", positive=False)
                + charge,
                12,
            )
            payload["updated_at"] = _utc_now()
            _write_atomic(self.path, payload)
            return _with_totals(payload, self.path)
