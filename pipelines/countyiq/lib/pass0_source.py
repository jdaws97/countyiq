"""Exact, hash-bound source units for the Pass 0 extractor."""

import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceUnit:
    number: int
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class SourceDocument:
    text: str
    sha256: str
    units: tuple[SourceUnit, ...]

    def model_input(self) -> str:
        lines = []
        for unit in self.units:
            display_text = unit.text.replace("\\", "\\\\")
            display_text = display_text.replace("\r", "\\r").replace("\n", "\\n")
            lines.append(f"{unit.number}\t{display_text}")
        return "\n".join(lines)

    def resolve(self, first: int, last: int, expected_sha256: str) -> SourceUnit:
        if expected_sha256 != self.sha256:
            raise ValueError("Source hash does not match")
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (first, last)
        ):
            raise ValueError("Unit numbers must be integers")
        if first > last or first < 1 or last > len(self.units):
            raise ValueError("Invalid unit range")
        first_unit = self.units[first - 1]
        last_unit = self.units[last - 1]
        return SourceUnit(
            first,
            first_unit.start,
            last_unit.end,
            self.text[first_unit.start : last_unit.end],
        )

    def resolve_ranges(
        self, ranges: list[tuple[int, int]], expected_sha256: str
    ) -> tuple[SourceUnit, ...]:
        if not isinstance(ranges, list) or not ranges:
            raise ValueError("At least one range is required")
        resolved = []
        for item in ranges:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("Ranges must be endpoint pairs")
            resolved.append(self.resolve(item[0], item[1], expected_sha256))
        ordered = sorted(resolved, key=lambda unit: unit.start)
        merged: list[SourceUnit] = []
        for unit in ordered:
            if merged and unit.start <= merged[-1].end:
                previous = merged[-1]
                end = max(previous.end, unit.end)
                merged[-1] = SourceUnit(
                    previous.number,
                    previous.start,
                    end,
                    self.text[previous.start : end],
                )
            else:
                merged.append(unit)
        return tuple(merged)

    def resolve_quote(
        self,
        quote: str,
        ranges: list[tuple[int, int]],
        expected_sha256: str,
        *,
        starts_on: int | None = None,
        ends_on: int | None = None,
    ) -> SourceUnit:
        """Find one literal excerpt within supplied ranges, preserving its offsets.

        Case, whitespace and straight/curly quotes may differ. Ambiguous matches,
        partial words and text spanning an unprovided gap are rejected rather
        than repaired or guessed.
        """
        if not isinstance(quote, str) or not quote.strip():
            raise ValueError("Excerpt must contain source text")
        start_unit = (
            self.resolve(starts_on, starts_on, expected_sha256)
            if starts_on is not None
            else None
        )
        end_unit = (
            self.resolve(ends_on, ends_on, expected_sha256)
            if ends_on is not None
            else None
        )
        matches = []
        for start, end in self._quote_offsets(
            quote, self.resolve_ranges(ranges, expected_sha256)
        ):
            if (
                start_unit is not None
                and not start_unit.start <= start < start_unit.end
            ):
                continue
            if end_unit is not None and not end_unit.start < end <= end_unit.end:
                continue
            matches.append((start, end))
            if len(matches) > 1:
                raise ValueError("Excerpt is ambiguous within its evidence")
        if not matches:
            raise ValueError("Excerpt is not literal within its evidence")
        start, end = matches[0]
        number = next(
            unit.number for unit in self.units if unit.start <= start < unit.end
        )
        return SourceUnit(number, start, end, self.text[start:end])

    def contains_quote(self, quote: str, spans: tuple[SourceUnit, ...]) -> bool:
        """Check literal membership without requiring a unique occurrence."""
        for span in spans:
            if not 0 <= span.start <= span.end <= len(self.text) or (
                span.text != self.text[span.start : span.end]
            ):
                raise ValueError("Evidence span does not match this source")
        return next(self._quote_offsets(quote, spans), None) is not None

    def _quote_offsets(
        self, quote: str, spans: tuple[SourceUnit, ...]
    ) -> Iterator[tuple[int, int]]:
        if not isinstance(quote, str) or not quote.strip():
            return
        quote = quote.strip()
        words = []
        for word in quote.split():
            characters = []
            for character in word:
                if character in "'‘’":
                    characters.append("['‘’]")
                elif character in '"“”':
                    characters.append('["“”]')
                else:
                    characters.append(re.escape(character))
            words.append("".join(characters))
        pattern = r"\s+".join(words)
        if quote[0].isalnum() or quote[0] == "_":
            pattern = r"(?<!\w)" + pattern
        if quote[-1].isalnum() or quote[-1] == "_":
            pattern += r"(?!\w)"
        expression = re.compile(pattern, re.IGNORECASE)
        for span in spans:
            position = 0
            while match := expression.search(span.text, position):
                start, end = span.start + match.start(), span.start + match.end()
                position = match.start() + 1
                if (
                    (quote[0].isalnum() or quote[0] == "_")
                    and start > 0
                    and (self.text[start - 1].isalnum() or self.text[start - 1] == "_")
                ):
                    continue
                if (
                    (quote[-1].isalnum() or quote[-1] == "_")
                    and end < len(self.text)
                    and (self.text[end].isalnum() or self.text[end] == "_")
                ):
                    continue
                yield start, end

    def resolve_excerpt(
        self,
        start_quote: str,
        end_quote: str,
        first: int,
        last: int,
        expected_sha256: str,
    ) -> SourceUnit:
        """Resolve exact anchors, correcting only unambiguous bounded endpoints.

        The named endpoint units disambiguate repeated wording. If a named unit
        is wrong, an anchor may move only when it occurs once in the entire
        source and is already wholly inside the cited range. Text and evidence
        bounds never expand during this correction.
        """
        window = self.resolve(first, last, expected_sha256)
        ranges = [(first, last)]

        def anchor(
            quote: str, *, starts_on: int | None = None, ends_on: int | None = None
        ) -> SourceUnit:
            try:
                return self.resolve_quote(
                    quote,
                    ranges,
                    expected_sha256,
                    starts_on=starts_on,
                    ends_on=ends_on,
                )
            except ValueError as original_error:
                try:
                    match = self.resolve_quote(
                        quote, [(1, len(self.units))], expected_sha256
                    )
                except ValueError:
                    raise original_error from None
                if match.start < window.start or match.end > window.end:
                    raise original_error from None
                return match

        start = anchor(start_quote, starts_on=first)
        end = anchor(end_quote, ends_on=last)
        if end.start < start.start or end.end < start.end:
            raise ValueError("Excerpt end anchor precedes its start anchor")
        return SourceUnit(
            start.number,
            start.start,
            end.end,
            self.text[start.start : end.end],
        )


def index_source(text: str, max_unit_chars: int = 500) -> SourceDocument:
    if not isinstance(text, str):
        raise TypeError("Source text must be a string")
    if (
        isinstance(max_unit_chars, bool)
        or not isinstance(max_unit_chars, int)
        or max_unit_chars < 2
    ):
        raise ValueError("max_unit_chars must be an integer of at least two")

    units = []
    offset = 0
    for physical_line in text.splitlines(keepends=True):
        line_end = offset + len(physical_line)
        while offset < line_end:
            end = min(offset + max_unit_chars, line_end)
            if end < line_end:
                boundary = max(
                    text.rfind(" ", offset + 1, end),
                    text.rfind("\t", offset + 1, end),
                )
                if boundary >= offset:
                    end = boundary + 1
            units.append(SourceUnit(len(units) + 1, offset, end, text[offset:end]))
            offset = end
    source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return SourceDocument(text, source_hash, tuple(units))
