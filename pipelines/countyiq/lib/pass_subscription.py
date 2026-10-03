"""Run the same pass validators with a private, serialized Codex CLI login."""

from __future__ import annotations

import fcntl
import os
import threading
from contextlib import contextmanager
from pathlib import Path

from countyiq.lib.intelligence_integrity import content_hash
from countyiq.lib.pass_llm_config import (
    PassCallLimitReached,
    PassHarnessUnavailable,
    PassSubscriptionPaused,
    resolve_pass_model,
)
from countyiq.lib.subscription_backfill import (
    SubscriptionAuthor,
    SubscriptionUnavailable,
)


def _positive_setting(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as error:
        raise PassHarnessUnavailable(f"{name} must be a positive integer") from error
    if value < 1:
        raise PassHarnessUnavailable(f"{name} must be a positive integer")
    return value


class SubscriptionPassRunner:
    """Serialize account access and cap calls independently of dollar budgets."""

    def __init__(self, pass_number: int):
        self.pass_number = pass_number
        state = Path(
            os.environ.get(
                "COUNTYIQ_SUBSCRIPTION_STATE_DIR",
                "/opt/countyiq/intelligence/subscription",
            )
        )
        self.directory = state / f"pass{pass_number}"
        self.directory.mkdir(parents=True, exist_ok=True)
        home = os.environ.get("CODEX_HOME", "").strip()
        if not home:
            raise PassHarnessUnavailable(
                "Set a private persistent CODEX_HOME for Dagster"
            )
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.max_calls = _positive_setting(
            f"COUNTYIQ_PASS{pass_number}_CODEX_MAX_CALLS", 100
        )
        self.timeout = _positive_setting("COUNTYIQ_CODEX_TIMEOUT_SECONDS", 600)
        self.calls = 0
        self.mutex = threading.Lock()
        self.local = threading.local()

    @contextmanager
    def account_lock(self):
        # Dagster serializes runs. This also covers threaded passes and the
        # operator login helper so session refresh has one writer at a time.
        with self.mutex, (self.home / ".countyiq-auth.lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def author(self, model_path):
        prefix = "codex/subscription:"
        if not model_path.startswith(prefix):
            raise PassSubscriptionPaused(
                "Subscription execution cannot call an API model"
            )
        return SubscriptionAuthor(
            self.directory, model=model_path.removeprefix(prefix), timeout=self.timeout
        )

    def check_login(self):
        try:
            with self.account_lock():
                self.author(resolve_pass_model(self.pass_number)).check_login()
        except (SubscriptionUnavailable, OSError) as error:
            raise PassSubscriptionPaused(
                "Codex subscription login is unavailable; run codex login on this PC"
            ) from error

    def start_item(self):
        self.local.receipts = []

    def provenance(self):
        return {
            "provider": "codex_subscription",
            "billing": "chatgpt_subscription",
            "api_calls": 0,
            "author_model": resolve_pass_model(self.pass_number),
            "artifacts": list(getattr(self.local, "receipts", [])),
        }

    def __call__(self, config, prompt, **kwargs):
        if kwargs.get("pdf_bytes"):
            raise PassSubscriptionPaused(
                "Prepare PDF text before subscription authoring"
            )
        # Independent verification votes must not silently reuse one cached vote.
        if self.pass_number in (1, 2) and kwargs.get("archive_key"):
            prompt += "\nIndependent review identifier: " + str(kwargs["archive_key"])
        author = self.author(config.model_path)
        fingerprint = content_hash(author.request(config, prompt))
        try:
            with self.account_lock():
                if not (self.directory / f"{fingerprint}.json").exists():
                    if self.calls >= self.max_calls:
                        raise PassCallLimitReached("Codex per-run call limit reached")
                    self.calls += 1
                result = author(config, prompt)
        except (SubscriptionUnavailable, OSError) as error:
            raise PassSubscriptionPaused(
                "Codex subscription stopped; inspect the private execution receipt"
            ) from error
        receipts = getattr(self.local, "receipts", [])
        receipts.extend(author.receipts)
        self.local.receipts = receipts
        result.metadata.update(
            served_model=config.model_path,
            provenance=author.provenance(),
        )
        return result


def start_subscription_item(invoke):
    if isinstance(invoke, SubscriptionPassRunner):
        invoke.start_item()


def subscription_provenance(invoke):
    return invoke.provenance() if isinstance(invoke, SubscriptionPassRunner) else None
