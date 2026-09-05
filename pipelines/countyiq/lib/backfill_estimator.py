"""Read-only estimator for CountyIQ's paid intelligence backfill.

The estimator deliberately imports the production selector queries and prompt
builders. It never imports or calls the OpenRouter harness and all database
access is SELECT-only. Candidate counts are exact on a first backfill; when
prior pass hashes exist, the report exposes a safe range because production
may skip unchanged contexts after gathering them.
"""

from __future__ import annotations

import hashlib
import math
import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from countyiq.assets.enrichment.brief_generation import (
    PARCELS_NEEDING_BRIEFS_QUERY,
    resolve_brief_rank_limit,
)
from countyiq.assets.enrichment.entity_verification import (
    MAX_CANDIDATE_NAMES_PER_CONTEXT,
    MAX_DYNAMIC_PROMPT_CHARACTERS,
)
from countyiq.assets.enrichment.proceeding_extraction import (
    _MAX_RAW_TEXT_CHARS,
    _MIN_RAW_TEXT_CHARS,
    PENDING_PROCEEDINGS_QUERY,
    _is_pdf_document,
    has_landuse_vocabulary,
)
from countyiq.assets.enrichment.signal_validation_batched import (
    PARCELS_NEEDING_VALIDATION_QUERY,
)
from countyiq.lib.county_config import get_county_config
from countyiq.lib.intelligence_common import (
    fetch_prior_pass_hashes,
    fetch_reusable_pass_hashes,
)
from countyiq.lib.intelligence_integrity import content_hash, inference_input_hash
from countyiq.lib.pass0_templates import (
    EXTRACTION_USER_TEMPLATE,
    PASS0_SYSTEM_PROMPT,
)
from countyiq.lib.pass0_templates import (
    PROMPT_VERSION as PASS0_PROMPT_VERSION,
)
from countyiq.lib.pass1_entity_verification import (
    CANDIDATE_CLUSTERS_QUERY,
    ENTITY_CANDIDATE_PAIRS_READY_QUERY,
    ENTITY_VERIFICATION_SYSTEM_PROMPT,
    build_entity_cluster_prompt,
    gather_cluster_records,
    select_pass1_clusters,
    stable_cluster_key,
)
from countyiq.lib.pass2_batched_validation import (
    BATCHED_VALIDATION_SYSTEM_PROMPT,
    build_batched_signal_prompt,
    gather_parcel_batch_context,
)
from countyiq.lib.pass3_brief_generation import (
    BRIEF_GENERATION_SYSTEM_PROMPT,
    build_brief_generation_prompt,
    gather_brief_context,
)
from countyiq.lib.pass3_owner_briefs import (
    OWNER_PORTFOLIO_QUERY,
    OWNER_ROLLUP_SYSTEM_PROMPT,
    OWNERS_NEEDING_BRIEFS_QUERY,
    PORTFOLIO_EVIDENCE_QUERY,
    build_owner_rollup_prompt,
)
from countyiq.lib.pass_llm_config import (
    estimate_reserved_call_cost,
    resolve_pass_enabled,
    resolve_pass_model,
)

_TOKENS_PER_CHARACTER = Decimal("0.25")
_PASS1_ADAPTIVE_CALLS_PER_CLUSTER = Decimal(23) / Decimal(11)
_PDF_FALLBACK_INPUT_TOKENS = 8_000

DATA_PROFILE_QUERY = """
    SELECT
        (SELECT COUNT(*) FROM staging.parcels WHERE valid_to IS NULL) AS parcels,
        (SELECT COUNT(*) FROM staging.public_proceedings WHERE valid_to IS NULL) AS proceedings,
        (SELECT COUNT(*) FROM staging.corporate_entities WHERE valid_to IS NULL) AS corporate_entities,
        (SELECT COUNT(*) FROM public.development_signals) AS development_signals,
        (SELECT COUNT(*) FROM public.evidence) AS validated_evidence,
        (SELECT COUNT(*) FROM public.owners) AS owners,
        (SELECT COUNT(*) FROM meta.intelligence_passes) AS prior_pass_records,
        COALESCE((
            SELECT c.relispopulated
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'entity_candidate_pairs'
        ), FALSE) AS candidate_view_populated
"""


@dataclass(frozen=True)
class PriceProfile:
    model: str
    prompt_per_million: Decimal
    completion_per_million: Decimal
    cache_read_per_million: Decimal | None
    basis: str


# Luna is the production default. The GLM entry uses the actual Parasail rate
# returned by the 2026-08-30 CountyIQ probe, not OpenRouter's lower headline
# listing, so challenger estimates do not silently understate observed spend.
KNOWN_PRICE_PROFILES: dict[str, PriceProfile] = {
    "openai/gpt-5.6-luna": PriceProfile(
        model="openai/gpt-5.6-luna",
        prompt_per_million=Decimal("0.20"),
        completion_per_million=Decimal("1.20"),
        cache_read_per_million=Decimal("0.02"),
        basis="OpenRouter model price rechecked 2026-08-30",
    ),
    "z-ai/glm-5.3-flash": PriceProfile(
        model="z-ai/glm-5.3-flash",
        prompt_per_million=Decimal("0.15"),
        completion_per_million=Decimal("0.50"),
        cache_read_per_million=None,
        basis="CountyIQ Parasail receipt observed 2026-08-30",
    ),
}


@dataclass(frozen=True)
class PassAssumptions:
    output_tokens_per_call: int
    max_output_tokens_per_call: int


PASS_ASSUMPTIONS: dict[str, PassAssumptions] = {
    "pass0": PassAssumptions(900, 4_096),
    "pass1": PassAssumptions(1_200, 8_192),
    "pass2": PassAssumptions(750, 4_096),
    "pass3": PassAssumptions(1_000, 2_048),
    "pass3b": PassAssumptions(1_400, 2_048),
}


@dataclass
class PassEstimate:
    key: str
    label: str
    enabled_in_environment: bool
    model: str | None
    unit_name: str
    units_min: int
    units_max: int
    planning_calls_min: int
    planning_calls_max: int
    retry_ceiling_calls: int
    sampled_units: int
    average_input_tokens: int
    runtime_max_input_tokens_per_call: int
    runtime_reservation_calls: int
    assumed_output_tokens_per_call: int
    max_output_tokens_per_call: int
    planning_cost_min: float | None
    planning_cost_max: float | None
    retry_ceiling_cost: float | None
    details: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def approximate_tokens(text: str) -> int:
    """Return a conservative tokenizer-free estimate for English/JSON text."""

    if not text:
        return 0
    return math.ceil(Decimal(len(text)) * _TOKENS_PER_CHARACTER)


def runtime_prompt_tokens(text: str) -> int:
    """Match the runtime ledger's conservative one-token-per-three-characters rule."""

    return math.ceil(len(text) / 3) if text else 0


def build_name_clusters(pairs: Iterable[Any]) -> list[list[str]]:
    """Build the same connected name components used by production Pass 1."""

    parent: dict[str, str] = {}

    def find(name: str) -> str:
        if name not in parent:
            parent[name] = name
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[left_root] = right_root

    for row in pairs:
        left = _row_value(row, "name_a", 0)
        right = _row_value(row, "name_b", 1)
        if left and right:
            union(str(left), str(right))

    groups: dict[str, list[str]] = {}
    for name in parent:
        groups.setdefault(find(name), []).append(name)
    return [sorted(group) for group in groups.values()]


def estimate_backfill(database, *, sample_size: int = 50) -> dict[str, Any]:
    """Build a production-shaped, read-only backfill estimate."""

    sample_size = max(0, sample_size)
    data_profile = _data_profile(database)
    estimates = [
        _estimate_pass0(database, sample_size),
        _estimate_pass1(database, sample_size),
        _estimate_pass2(database, sample_size),
        _estimate_pass3(database, sample_size),
        _estimate_pass3b(database, sample_size),
    ]

    costs_known = all(item.planning_cost_max is not None for item in estimates)
    retry_costs_known = all(
        item.retry_ceiling_cost is not None for item in estimates
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "read_only": True,
        "sample_size_per_pass": sample_size,
        "data_profile": data_profile,
        "passes": [asdict(item) for item in estimates],
        "totals": {
            "planning_calls_min": sum(item.planning_calls_min for item in estimates),
            "planning_calls_max": sum(item.planning_calls_max for item in estimates),
            "retry_ceiling_calls": sum(item.retry_ceiling_calls for item in estimates),
            "planning_cost_min": (
                round(sum(item.planning_cost_min or 0 for item in estimates), 6)
                if costs_known else None
            ),
            "planning_cost_max": (
                round(sum(item.planning_cost_max or 0 for item in estimates), 6)
                if costs_known else None
            ),
            "retry_ceiling_cost": (
                round(sum(item.retry_ceiling_cost or 0 for item in estimates), 6)
                if retry_costs_known else None
            ),
        },
        "excluded": [
            {
                "key": "pass4",
                "reason": (
                    "Pass 4 remains outside the alpha backfill and cost total; "
                    "it is disabled by default and has no required alpha surface."
                ),
                "enabled_in_environment": resolve_pass_enabled(4),
            }
        ],
        "method": {
            "candidate_counts": (
                "Production selector queries. Ranges appear when prior pass hashes "
                "mean the production asset may skip unchanged contexts."
            ),
            "runtime_gates": (
                "Reported as environment status but never used to zero the "
                "hypothetical plan; the estimator is intended to run before enablement."
            ),
            "data_profile": (
                "Exact current row counts for the live selector inputs. Empty source "
                "tables are called out because they make a zero candidate estimate provisional."
            ),
            "input_tokens": (
                "Planning costs use a stable sample at one token per four "
                "characters. The retry ceiling separately mirrors runtime at "
                "one token per three characters and uses the configured "
                "50,000-token PDF ceiling."
            ),
            "output_tokens": (
                "Visible planning assumptions, not measured truth. Retry ceilings use "
                "each pass's configured maximum output tokens."
            ),
            "costs": (
                "Planning values are no-cache provider estimates. The retry "
                "ceiling uses the runtime reservation shape: configured price "
                "ceilings when present, retry output growth, and the 10% buffer."
            ),
        },
    }


def _data_profile(database) -> dict[str, Any]:
    rows = database.execute(DATA_PROFILE_QUERY) or []
    names = (
        "parcels",
        "proceedings",
        "corporate_entities",
        "development_signals",
        "validated_evidence",
        "owners",
        "prior_pass_records",
        "candidate_view_populated",
    )
    if not rows:
        raise RuntimeError("Unable to read the backfill input data profile")
    values = {
        name: _row_value(rows[0], name, index)
        for index, name in enumerate(names)
    }
    counts = {
        name: int(values[name] or 0)
        for name in names
        if name != "candidate_view_populated"
    }
    warnings = []
    if counts["parcels"] == 0:
        warnings.append("No current parcels: Pass 1-3 candidate counts are not representative.")
    if counts["proceedings"] == 0:
        warnings.append("No current proceedings: Pass 0 volume is not representative.")
    if counts["corporate_entities"] == 0:
        warnings.append(
            "No PA DOS corporate rows: Pass 1 excludes shared-office corporate candidates."
        )
    if counts["development_signals"] == 0:
        warnings.append("No deterministic development signals: Pass 2-3 volume is provisional.")
    if counts["owners"] == 0:
        warnings.append("No resolved owners: Pass 3b volume is provisional.")
    if not bool(values["candidate_view_populated"]):
        warnings.append("Pass 1 candidate materialized view is not populated.")
    return {
        "counts": counts,
        "candidate_view_populated": bool(values["candidate_view_populated"]),
        "warnings": warnings,
    }


def _estimate_pass0(database, sample_size: int) -> PassEstimate:
    county = get_county_config()
    rows = list(database.execute(PENDING_PROCEEDINGS_QUERY) or [])
    prior_rows = database.execute(
        """
        SELECT DISTINCT ON (subject_key) subject_key, input_hash
        FROM meta.intelligence_inference_history
        WHERE pass_number = 0
          AND output_kind = 'proceeding_extraction'
          AND disposition = 'accepted'
        ORDER BY subject_key, inference_id DESC
        """
    ) or []
    prior_hashes = {
        str(_row_value(row, "subject_key", 0)): str(_row_value(row, "input_hash", 1))
        for row in prior_rows
    }
    eligible: list[Any] = []
    skipped_unchanged = 0
    raw_text_count = 0
    pdf_fallback_count = 0
    unsupported_count = 0
    deterministic_prefilter_skips = 0
    eligible_dates: list[date] = []
    for row in rows:
        raw_text = _row_value(row, "raw_text", 5) or ""
        document_url = str(_row_value(row, "document_url", 4) or "")
        call_eligible = False
        if isinstance(raw_text, str) and len(raw_text.strip()) >= _MIN_RAW_TEXT_CHARS:
            if has_landuse_vocabulary(raw_text[:_MAX_RAW_TEXT_CHARS]):
                raw_text_count += 1
                eligible.append(row)
                call_eligible = True
            else:
                deterministic_prefilter_skips += 1
        elif _is_pdf_document(document_url):
            pdf_fallback_count += 1
            eligible.append(row)
            call_eligible = True
        else:
            unsupported_count += 1
        if call_eligible:
            document_content_hash = _row_value(row, "content_hash", 6)
            source_version = (
                content_hash({
                    "document_content_hash": document_content_hash,
                    "raw_text_hash": content_hash(raw_text[:_MAX_RAW_TEXT_CHARS]),
                })
                if isinstance(raw_text, str)
                and len(raw_text.strip()) >= _MIN_RAW_TEXT_CHARS
                else document_content_hash
            )
            if source_version:
                source_hash = content_hash({
                    "proceeding_id": _row_value(row, "id", 0),
                    "body_name": _row_value(row, "body_name", 1),
                    "meeting_date": _row_value(row, "meeting_date", 2),
                    "proceeding_type": _row_value(row, "proceeding_type", 3),
                    "document_url": document_url,
                    "source_version": source_version,
                })
                input_hash = inference_input_hash(
                    source_hash,
                    requested_model=resolve_pass_model(0) or "",
                    prompt_version=PASS0_PROMPT_VERSION,
                )
                subject_key = f"proceeding:{_row_value(row, 'id', 0)}"
                if prior_hashes.get(subject_key) == input_hash:
                    eligible.pop()
                    skipped_unchanged += 1
                    call_eligible = False
        if call_eligible:
            meeting_date = _row_value(row, "meeting_date", 2)
            if isinstance(meeting_date, datetime):
                eligible_dates.append(meeting_date.date())
            elif isinstance(meeting_date, date):
                eligible_dates.append(meeting_date)

    sample = _stable_sample(eligible, sample_size, lambda row: _row_value(row, "id", 0))
    token_samples = []
    runtime_token_samples = []
    for row in sample:
        meeting_date = _row_value(row, "meeting_date", 2)
        prompt = EXTRACTION_USER_TEMPLATE.format(
            body_name=_row_value(row, "body_name", 1),
            county_name=county.name,
            state=county.state,
            proceeding_type=_row_value(row, "proceeding_type", 3),
            date_clause=f" dated {meeting_date}" if meeting_date else "",
        )
        raw_text = _row_value(row, "raw_text", 5) or ""
        if isinstance(raw_text, str) and len(raw_text.strip()) >= _MIN_RAW_TEXT_CHARS:
            prompt += "\n\nDOCUMENT TEXT:\n" + raw_text[:_MAX_RAW_TEXT_CHARS]
            rendered_prompt = PASS0_SYSTEM_PROMPT + prompt
            token_samples.append(approximate_tokens(rendered_prompt))
            runtime_token_samples.append(runtime_prompt_tokens(rendered_prompt))
        else:
            rendered_prompt = PASS0_SYSTEM_PROMPT + prompt
            token_samples.append(
                approximate_tokens(rendered_prompt)
                + _PDF_FALLBACK_INPUT_TOKENS
            )
            runtime_token_samples.append(
                runtime_prompt_tokens(rendered_prompt)
                + max(_positive_int_env("COUNTYIQ_PASS0_PDF_TOKEN_CEILING", 50_000), 1)
            )

    units = len(eligible)
    today = datetime.now(UTC).date()
    dated_future_over_90 = sum((value - today).days > 90 for value in eligible_dates)
    recent_365 = sum(-90 <= (today - value).days <= 365 for value in eligible_dates)
    recent_730 = sum(-90 <= (today - value).days <= 730 for value in eligible_dates)
    estimate = _make_estimate(
        key="pass0",
        label="Pass 0 proceeding extraction",
        pass_number=0,
        unit_name="proceedings",
        units_min=units,
        units_max=units,
        planning_calls_min=units,
        planning_calls_max=units,
        retry_ceiling_calls=units * 2,
        token_samples=token_samples,
        runtime_token_samples=runtime_token_samples,
        details={
            "eligible_source_rows": len(rows),
            "skipped_unchanged": skipped_unchanged,
            "raw_text_inputs": raw_text_count,
            "pdf_fallback_inputs": pdf_fallback_count,
            "unsupported_without_text": unsupported_count,
            "deterministic_prefilter_skips": deterministic_prefilter_skips,
            "eligible_dated_last_365_days": recent_365,
            "eligible_dated_last_730_days": recent_730,
            "eligible_future_over_90_days": dated_future_over_90,
            "eligible_older_or_undated": units - recent_730 - dated_future_over_90,
        },
        notes=[
            "One base call per changed eligible document; one provider retry is the ceiling.",
            "The selector scans all reachable history, then skips exact source/model/prompt hashes already accepted.",
            "Raw-text documents without land-use vocabulary are deterministic zero-cost skips.",
            "PDF fallback rows remain conservatively priced because their text is extracted only at runtime.",
            "Dates more than 90 days in the future are reported separately as likely source/parser anomalies.",
        ],
    )
    profile = KNOWN_PRICE_PROFILES.get(estimate.model or "")
    scenario_365_calls = recent_365
    scenario_730_calls = recent_730
    estimate.details.update({
        "last_365_days_planning_calls": scenario_365_calls,
        "last_365_days_planning_cost": _cost(
            profile,
            scenario_365_calls,
            estimate.average_input_tokens,
            estimate.assumed_output_tokens_per_call,
        ),
        "last_730_days_planning_calls": scenario_730_calls,
        "last_730_days_planning_cost": _cost(
            profile,
            scenario_730_calls,
            estimate.average_input_tokens,
            estimate.assumed_output_tokens_per_call,
        ),
    })
    return estimate


def _estimate_pass1(database, sample_size: int) -> PassEstimate:
    ready_rows = database.execute(ENTITY_CANDIDATE_PAIRS_READY_QUERY) or []
    if not ready_rows or not bool(_row_value(ready_rows[0], "relispopulated", 0)):
        raise RuntimeError(
            "public.entity_candidate_pairs is not populated; run "
            "deterministic_enrichment_refresh before estimating paid Pass 1 work"
        )
    pairs = list(database.execute(CANDIDATE_CLUSTERS_QUERY) or [])
    clusters, person_only_skipped = select_pass1_clusters(build_name_clusters(pairs))
    deferred_name_count = sum(len(cluster) > MAX_CANDIDATE_NAMES_PER_CONTEXT for cluster in clusters)
    clusters = [cluster for cluster in clusters if len(cluster) <= MAX_CANDIDATE_NAMES_PER_CONTEXT]
    prior_hashes = fetch_reusable_pass_hashes(database, pass_number=1)
    units_max = len(clusters)

    sample = _stable_sample(clusters, sample_size, stable_cluster_key)
    token_samples = []
    runtime_token_samples = []
    deferred_sample_keys = set()
    for cluster in sample:
        with database.dict_cursor() as cursor:
            records = gather_cluster_records(cursor, cluster)
        prompt = build_entity_cluster_prompt(records)
        if len(prompt) > MAX_DYNAMIC_PROMPT_CHARACTERS:
            deferred_sample_keys.add(stable_cluster_key(cluster))
            continue
        rendered_prompt = ENTITY_VERIFICATION_SYSTEM_PROMPT + prompt
        token_samples.append(approximate_tokens(rendered_prompt))
        runtime_token_samples.append(runtime_prompt_tokens(rendered_prompt))

    # Unsampled contexts may also exceed the runtime character bound. Report
    # a conservative range instead of counting them as definitely callable.
    units_max -= len(deferred_sample_keys)
    units_min = sum(
        stable_cluster_key(cluster) not in prior_hashes
        and stable_cluster_key(cluster) not in deferred_sample_keys
        for cluster in sample
    )

    trials = max(1, int(os.environ.get("COUNTYIQ_PASS1_TRIALS", "3")))
    adaptive = os.environ.get(
        "COUNTYIQ_PASS1_ADAPTIVE_VOTING", "true"
    ).strip().lower() in {"1", "true", "yes", "on"}
    if trials == 1:
        calls_min = units_min
        calls_max = units_max
    elif adaptive and trials == 3:
        calls_min = math.ceil(Decimal(units_min) * _PASS1_ADAPTIVE_CALLS_PER_CLUSTER)
        calls_max = math.ceil(Decimal(units_max) * _PASS1_ADAPTIVE_CALLS_PER_CLUSTER)
    else:
        calls_min = units_min * trials
        calls_max = units_max * trials

    retry_ceiling = units_max * trials * 2
    escalation_enabled = bool(os.environ.get("COUNTYIQ_PASS1_ESCALATION_MODEL", "").strip())
    if escalation_enabled:
        retry_ceiling += units_max * 2

    return _make_estimate(
        key="pass1",
        label="Pass 1 entity verification",
        pass_number=1,
        unit_name="candidate clusters",
        units_min=units_min,
        units_max=units_max,
        planning_calls_min=calls_min,
        planning_calls_max=calls_max,
        retry_ceiling_calls=retry_ceiling,
        token_samples=token_samples,
        runtime_token_samples=runtime_token_samples,
        details={
            "candidate_pairs": len(pairs),
            "clusters_deferred_name_limit": deferred_name_count,
            "sampled_clusters_deferred_character_limit": len(deferred_sample_keys),
            "unsampled_contexts": len(clusters) - len(sample),
            "max_candidate_names": MAX_CANDIDATE_NAMES_PER_CONTEXT,
            "max_dynamic_prompt_characters": MAX_DYNAMIC_PROMPT_CHARACTERS,
            "person_only_clusters_skipped": person_only_skipped,
            "prior_completed_hashes": len(prior_hashes),
            "trials": trials,
            "adaptive_voting": adaptive,
            "escalation_enabled": escalation_enabled,
        },
        notes=[
            "Adaptive N=3 planning uses the observed 23 calls for 11 archived clusters.",
            "units_min counts new sampled clusters within the context bounds; units_max also includes unsampled and changed existing clusters. Unsampled character-limit deferrals and deterministic resolutions may reduce paid calls.",
        ],
    )


def _estimate_pass2(database, sample_size: int) -> PassEstimate:
    rows = list(database.execute(PARCELS_NEEDING_VALIDATION_QUERY) or [])
    pidns = [str(_row_value(row, "pidn", 0)) for row in rows]
    prior_hashes = fetch_reusable_pass_hashes(database, pass_number=2)
    units_min = sum(pidn not in prior_hashes for pidn in pidns) if prior_hashes else len(pidns)
    units_max = len(pidns)
    trials = max(1, int(os.environ.get("COUNTYIQ_PASS2_TRIALS", "1")))

    sample = _stable_sample(pidns, sample_size, lambda pidn: pidn)
    token_samples = []
    runtime_token_samples = []
    for pidn in sample:
        with database.dict_cursor() as cursor:
            context = gather_parcel_batch_context(cursor, pidn)
        rendered_prompt = (
            BATCHED_VALIDATION_SYSTEM_PROMPT + build_batched_signal_prompt(context)
        )
        token_samples.append(approximate_tokens(rendered_prompt))
        runtime_token_samples.append(runtime_prompt_tokens(rendered_prompt))

    return _make_estimate(
        key="pass2",
        label="Pass 2 signal validation",
        pass_number=2,
        unit_name="eligible parcels",
        units_min=units_min,
        units_max=units_max,
        planning_calls_min=units_min * trials,
        planning_calls_max=units_max * trials,
        retry_ceiling_calls=units_max * (trials * 2 + 2),
        token_samples=token_samples,
        runtime_token_samples=runtime_token_samples,
        details={
            "prior_completed_hashes": len(prior_hashes),
            "trials": trials,
            "selection_gate": "at least two interpretive signals",
        },
        notes=[
            "Retry ceiling includes one provider retry per trial and one missing-signal recovery call with its retry.",
        ],
    )


def _estimate_pass3(database, sample_size: int) -> PassEstimate:
    rows = list(
        database.execute(
            PARCELS_NEEDING_BRIEFS_QUERY,
            {"rank_limit": resolve_brief_rank_limit()},
        )
        or []
    )
    pidns = [str(_row_value(row, "pidn", 0)) for row in rows]
    prior_hashes = fetch_prior_pass_hashes(database, pass_number=3)
    units_min = sum(pidn not in prior_hashes for pidn in pidns) if prior_hashes else len(pidns)
    units_max = len(pidns)

    sample = _stable_sample(pidns, sample_size, lambda pidn: pidn)
    token_samples = []
    runtime_token_samples = []
    for pidn in sample:
        with database.dict_cursor() as cursor:
            context = gather_brief_context(cursor, pidn)
        rendered_prompt = (
            BRIEF_GENERATION_SYSTEM_PROMPT + build_brief_generation_prompt(context)
        )
        token_samples.append(approximate_tokens(rendered_prompt))
        runtime_token_samples.append(runtime_prompt_tokens(rendered_prompt))

    return _make_estimate(
        key="pass3",
        label="Pass 3 parcel briefs",
        pass_number=3,
        unit_name="eligible parcel briefs",
        units_min=units_min,
        units_max=units_max,
        planning_calls_min=units_min,
        planning_calls_max=units_max,
        retry_ceiling_calls=units_max * 2,
        token_samples=token_samples,
        runtime_token_samples=runtime_token_samples,
        details={"prior_completed_hashes": len(prior_hashes)},
        notes=["Only parcels with medium/high validated evidence are selected."],
    )


def _estimate_pass3b(database, sample_size: int) -> PassEstimate:
    rows = list(database.execute(OWNERS_NEEDING_BRIEFS_QUERY) or [])
    owners = [
        {
            "owner_id": _row_value(row, "owner_id", 0),
            "canonical_name": _row_value(row, "canonical_name", 1),
        }
        for row in rows
    ]
    sample = _stable_sample(owners, sample_size, lambda owner: owner["owner_id"])
    token_samples = []
    runtime_token_samples = []
    for owner_ref in sample:
        owner_rows = database.execute(
            OWNER_PORTFOLIO_QUERY, {"owner_id": owner_ref["owner_id"]}
        ) or []
        if not owner_rows:
            continue
        owner_row = owner_rows[0]
        owner = {
            "owner_id": _row_value(owner_row, "owner_id", 0),
            "canonical_name": _row_value(owner_row, "canonical_name", 1),
            "entity_type": _row_value(owner_row, "entity_type", 2),
            "pidns": _row_value(owner_row, "pidns", 3) or [],
            "n_parcels": _row_value(owner_row, "n_parcels", 4) or 0,
        }
        evidence_rows = database.execute(
            PORTFOLIO_EVIDENCE_QUERY, {"pidns": owner["pidns"]}
        ) or []
        evidence = [
            {
                "pidn": _row_value(row, "pidn", 0),
                "signal_key": _row_value(row, "signal_key", 1),
                "validation_status": _row_value(row, "validation_status", 2),
                "adjusted_significance": _row_value(row, "adjusted_significance", 3),
                "validation_reasoning": _row_value(row, "validation_reasoning", 4),
                "validated_at": _row_value(row, "validated_at", 5),
                "confidence": _row_value(row, "confidence", 6),
                "municipality": _row_value(row, "municipality", 7),
            }
            for row in evidence_rows
        ]
        rendered_prompt = (
            OWNER_ROLLUP_SYSTEM_PROMPT + build_owner_rollup_prompt(owner, evidence)
        )
        token_samples.append(approximate_tokens(rendered_prompt))
        runtime_token_samples.append(runtime_prompt_tokens(rendered_prompt))

    units = len(owners)
    return _make_estimate(
        key="pass3b",
        label="Pass 3b owner briefs",
        pass_number=3,
        unit_name="eligible owner briefs",
        units_min=units,
        units_max=units,
        planning_calls_min=units,
        planning_calls_max=units,
        retry_ceiling_calls=units * 2,
        token_samples=token_samples,
        runtime_token_samples=runtime_token_samples,
        details={"minimum_signaled_parcels": 3},
        notes=["The selector already excludes current owner briefs."],
    )


def _make_estimate(
    *,
    key: str,
    label: str,
    pass_number: int,
    unit_name: str,
    units_min: int,
    units_max: int,
    planning_calls_min: int,
    planning_calls_max: int,
    retry_ceiling_calls: int,
    token_samples: Sequence[int],
    runtime_token_samples: Sequence[int],
    details: dict[str, Any],
    notes: list[str],
) -> PassEstimate:
    assumptions = PASS_ASSUMPTIONS[key]
    average_input = (
        math.ceil(sum(token_samples) / len(token_samples)) if token_samples else 0
    )
    runtime_max_input = max(runtime_token_samples, default=0)
    runtime_reservation_calls = math.ceil(retry_ceiling_calls / 2)
    enabled_in_environment = resolve_pass_enabled(pass_number)
    model = resolve_pass_model(pass_number)
    profile = KNOWN_PRICE_PROFILES.get(model or "")
    if not enabled_in_environment:
        notes = [
            *notes,
            (
                "Disabled by the current runtime configuration; this estimate still "
                "models the hypothetical backfill so it can be reviewed before enablement."
            ),
        ]
    if profile is None:
        notes = [
            *notes,
            f"No checked price profile for {model or 'unconfigured model'}; cost is omitted.",
        ]

    provider_retry_ceiling_cost = _cost(
        profile,
        retry_ceiling_calls,
        average_input,
        assumptions.max_output_tokens_per_call,
    )
    retry_ceiling_cost, runtime_price_basis = _runtime_reservation_cost(
        profile,
        runtime_reservation_calls,
        runtime_max_input,
        assumptions.max_output_tokens_per_call,
    )

    return PassEstimate(
        key=key,
        label=label,
        enabled_in_environment=enabled_in_environment,
        model=model,
        unit_name=unit_name,
        units_min=units_min,
        units_max=units_max,
        planning_calls_min=planning_calls_min,
        planning_calls_max=planning_calls_max,
        retry_ceiling_calls=retry_ceiling_calls,
        sampled_units=len(token_samples),
        average_input_tokens=average_input,
        runtime_max_input_tokens_per_call=runtime_max_input,
        runtime_reservation_calls=runtime_reservation_calls,
        assumed_output_tokens_per_call=assumptions.output_tokens_per_call,
        max_output_tokens_per_call=assumptions.max_output_tokens_per_call,
        planning_cost_min=_cost(
            profile,
            planning_calls_min,
            average_input,
            assumptions.output_tokens_per_call,
        ),
        planning_cost_max=_cost(
            profile,
            planning_calls_max,
            average_input,
            assumptions.output_tokens_per_call,
        ),
        retry_ceiling_cost=retry_ceiling_cost,
        details={
            **details,
            "price_basis": profile.basis if profile else None,
            "provider_retry_ceiling_cost": provider_retry_ceiling_cost,
            "runtime_reservation_price_basis": runtime_price_basis,
        },
        notes=notes,
    )


def _cost(
    profile: PriceProfile | None,
    calls: int,
    input_tokens_per_call: int,
    output_tokens_per_call: int,
) -> float | None:
    if profile is None:
        return None
    prompt_cost = (
        Decimal(calls)
        * Decimal(input_tokens_per_call)
        * profile.prompt_per_million
        / Decimal(1_000_000)
    )
    completion_cost = (
        Decimal(calls)
        * Decimal(output_tokens_per_call)
        * profile.completion_per_million
        / Decimal(1_000_000)
    )
    return round(float(prompt_cost + completion_cost), 6)


def _runtime_reservation_cost(
    profile: PriceProfile | None,
    calls: int,
    input_tokens_per_call: int,
    max_output_tokens_per_call: int,
) -> tuple[float | None, str | None]:
    """Return the same conservative ceiling the runtime would reserve."""

    if profile is None:
        return None, None
    if calls == 0:
        return 0.0, "no calls"
    if input_tokens_per_call <= 0:
        return None, "unavailable without a sampled production prompt"

    prompt_ceiling = _positive_float_env(
        "COUNTYIQ_MAX_PRICE_PROMPT",
        float(profile.prompt_per_million),
    )
    completion_ceiling = _positive_float_env(
        "COUNTYIQ_MAX_PRICE_COMPLETION",
        float(profile.completion_per_million),
    )
    configured = (
        os.environ.get("COUNTYIQ_MAX_PRICE_PROMPT", "").strip()
        and os.environ.get("COUNTYIQ_MAX_PRICE_COMPLETION", "").strip()
    )
    per_call = estimate_reserved_call_cost(
        prompt_tokens=input_tokens_per_call,
        max_tokens=max_output_tokens_per_call,
        max_price_prompt=prompt_ceiling,
        max_price_completion=completion_ceiling,
        retries=1,
    )
    basis = (
        "configured runtime price ceilings"
        if configured
        else "checked provider prices (set runtime ceilings before enablement)"
    )
    return round(per_call * calls, 6), basis


def _positive_float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value:
        try:
            parsed = float(value)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return default


def _positive_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value:
        try:
            parsed = int(value)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return default


def _stable_sample(
    values: Sequence[Any],
    sample_size: int,
    key: Callable[[Any], Any],
) -> list[Any]:
    if sample_size <= 0 or not values:
        return []
    if len(values) <= sample_size:
        return list(values)
    return sorted(
        values,
        key=lambda item: hashlib.sha256(str(key(item)).encode("utf-8")).digest(),
    )[:sample_size]


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[index]
    except (IndexError, KeyError, TypeError):
        return None
