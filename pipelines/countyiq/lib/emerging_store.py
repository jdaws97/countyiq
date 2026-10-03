"""Version analyses and explicit review actions; never publish model drafts implicitly."""

from countyiq.lib.emerging_intelligence import PROMPT_VERSION, validate_analysis
from countyiq.lib.emerging_packets import verify_packet
from countyiq.lib.intelligence_integrity import content_hash, record_inference_decision


def retain_analysis(
    database, packet: dict, analysis: dict, *, author: str, provenance=None
):
    with database.read_snapshot() as cur:
        verify_packet(cur, packet)
    analysis = validate_analysis(analysis, packet)
    # A changed company, project explanation or recommended action matters even
    # when the status enum stays the same. Preserve the complete reviewed claim
    # set; conservative wording-change quarantines are preferable to silent flips.
    semantic = sorted(analysis["hypotheses"], key=lambda item: item["family"])
    return record_inference_decision(
        database,
        subject_key=packet["source"]["seed_bundle"],
        pass_number=4,
        output_kind=(
            "emerging_analysis"
            if packet["temporal_mode"] == "current"
            else "emerging_replay"
        ),
        decision_key="emerging_analysis",
        source_hash=content_hash(
            {
                "source": packet["source"],
                "cutoff": packet["as_of"]
                if packet["temporal_mode"] != "current"
                else None,
            }
        ),
        input_hash=content_hash(packet),
        requested_model=author,
        prompt_version=PROMPT_VERSION,
        payload={
            "contract_version": 1,
            "packet": packet,
            "analysis": analysis,
            "provenance": provenance,
        },
        semantic_decision=semantic,
        evidence_refs=[item["record_key"] for item in packet["sources"]],
        provider=provenance.get("provider") if provenance else None,
    )


def review_analysis(
    database, inference_id: int, *, action: str, reviewer: str, rationale: str
):
    if (
        action not in {"publish", "withdraw"}
        or not reviewer.strip()
        or len(rationale.strip()) < 12
    ):
        raise ValueError("A review needs an action, reviewer and substantive rationale")
    with database.transaction(dict_rows=True) as cur:
        cur.execute(
            "SELECT * FROM meta.intelligence_inference_history WHERE inference_id = %s",
            (inference_id,),
        )
        row = cur.fetchone()
        if not row or row["output_kind"] != "emerging_analysis":
            raise ValueError(
                "Only current emerging analyses can be reviewed for publication"
            )
        if action == "publish":
            if row["disposition"] != "accepted":
                raise ValueError("A quarantined analysis cannot be published")
            payload = row["payload"]
            verify_packet(cur, payload["packet"])
            validate_analysis(payload["analysis"], payload["packet"])
            cur.execute(
                """SELECT max(inference_id) AS latest FROM meta.intelligence_inference_history
                WHERE subject_key=%s AND output_kind='emerging_analysis' AND disposition='accepted'""",
                (row["subject_key"],),
            )
            if cur.fetchone()["latest"] != inference_id:
                raise ValueError("Review the newest accepted analysis for this scope")
        cur.execute(
            """INSERT INTO meta.emerging_intelligence_publications
            (inference_id, action, reviewer, rationale) VALUES (%s,%s,%s,%s)
            RETURNING publication_id""",
            (inference_id, action, reviewer.strip(), rationale.strip()),
        )
        return cur.fetchone()["publication_id"]
