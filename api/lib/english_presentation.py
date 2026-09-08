"""English customer copy, kept separate from immutable original evidence."""

from copy import deepcopy


def english_explanation(explanation: dict | None) -> bool:
    return bool(explanation and explanation.get("presentation_language") == "en")


def presentation(source: dict, explanation: dict | None) -> tuple[str | None, bool]:
    if not english_explanation(explanation):
        return None, False
    matches = [
        item
        for item in explanation.get("source_presentations", [])
        if item.get("source_id") == source.get("id")
    ]
    if len(matches) != 1:
        return None, False
    item = matches[0]
    if item.get("language") == "en":
        return source.get("text"), False
    translated = item.get("english_text")
    return (
        (translated, True)
        if isinstance(translated, str) and translated.strip()
        else (None, False)
    )


def present_receipt(receipt: dict, source: dict, explanation: dict | None) -> None:
    """Locate the original first; translated text never supplies source offsets."""
    if "text" not in source:
        return
    text, translated = presentation(source, explanation)
    details = receipt.setdefault("details", {})
    passages = details.get("passages") or []
    receipt["label"] = " · ".join(
        str(value)
        for value in (
            details.get("body_name") or "Municipal record",
            details.get("meeting_date"),
        )
        if value
    )
    receipt["excerpt"] = text
    details["translated"] = translated
    if translated:
        # A translation cannot be split at offsets in the original language.
        # Retain only the first verified physical page as its starting location.
        first_page = next(
            (item.get("page") for item in passages if item.get("page")), None
        )
        details["passages"] = [{"text": text, "page": first_page}]
    elif text is None:
        details["passages"] = []


def present_record(
    record: dict | None, sources: list[dict], explanation: dict
) -> dict | None:
    result = deepcopy(record)
    if not result:
        return result
    by_id = {item["id"]: item for item in sources}
    for date in result.get("dates", []):
        source = by_id.get(date.get("source_id"), {})
        text, translated = presentation(source, explanation)
        if translated:
            # Keep the exact original quote in storage; the UI receives the full
            # translated supporting passage rather than an invented quote span.
            date["quote"] = text
            date["translated"] = True
        elif text is None:
            date["quote"] = None
    return result
