"""Lightweight deterministic validation for translation quality."""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Pattern for formula placeholders like <b0></b0>
PLACEHOLDER_RE = re.compile(r"</?b\d+>")
# Pattern for numbers (integers, decimals, percentages)
NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?%?\b")
# Pattern for figure/table references like "Figure 3-2", "Table 1"
FIGURE_TABLE_RE = re.compile(r"(?:Figure|Table|Fig\.?)\s*\d+(?:[.-]\d+)?", re.IGNORECASE)


@dataclass
class ValidationResult:
    """Result of validating one translated segment."""
    segment_id: int
    is_valid: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.is_valid = False


def validate_translation(
    segment_id: int,
    source: str,
    translation: str,
    *,
    min_length_ratio: float = 0.3,
    max_length_ratio: float = 3.0,
) -> ValidationResult:
    """Run deterministic checks on a single translated segment."""
    result = ValidationResult(segment_id=segment_id)

    # 1. Empty translation
    if not translation or not translation.strip():
        result.add_error("Translation is empty")
        return result

    # 2. Placeholder integrity
    src_placeholders = PLACEHOLDER_RE.findall(source)
    dst_placeholders = PLACEHOLDER_RE.findall(translation)
    if src_placeholders != dst_placeholders:
        result.add_error(
            f"Placeholder mismatch: source has {src_placeholders}, "
            f"translation has {dst_placeholders}"
        )

    # 3. Length ratio check
    src_len = len(source.strip())
    dst_len = len(translation.strip())
    if src_len > 0:
        ratio = dst_len / src_len
        if ratio < min_length_ratio:
            result.add_warning(
                f"Translation unusually short: {dst_len}/{src_len} chars "
                f"(ratio={ratio:.2f}, min={min_length_ratio})"
            )
        elif ratio > max_length_ratio:
            result.add_warning(
                f"Translation unusually long: {dst_len}/{src_len} chars "
                f"(ratio={ratio:.2f}, max={max_length_ratio})"
            )

    # 4. Number preservation
    src_numbers = set(NUMBER_RE.findall(source))
    dst_numbers = set(NUMBER_RE.findall(translation))
    missing_numbers = src_numbers - dst_numbers
    if missing_numbers:
        result.add_warning(
            f"Numbers missing from translation: {sorted(missing_numbers)}"
        )

    # 5. Figure/table reference preservation
    src_refs = set(FIGURE_TABLE_RE.findall(source))
    if src_refs:
        # Check that the numbers at least appear in translation
        for ref in src_refs:
            nums = re.findall(r"\d+(?:[.-]\d+)?", ref)
            for num in nums:
                if num not in translation:
                    result.add_warning(
                        f"Figure/table reference number '{num}' from '{ref}' "
                        f"not found in translation"
                    )

    # 6. Hallucination detection (translation contains significantly more content)
    if dst_len > src_len * 2.5 and src_len > 20:
        # Check if translation has substantial new content
        result.add_warning(
            f"Possible hallucination: translation is {ratio:.1f}x longer than source"
        )

    return result


def validate_batch(
    segments: list[tuple[int, str, str]],
    **kwargs,
) -> list[ValidationResult]:
    """Validate a batch of (segment_id, source, translation) tuples."""
    results = []
    for seg_id, source, translation in segments:
        result = validate_translation(seg_id, source, translation, **kwargs)
        if result.warnings or result.errors:
            logger.info(
                "Segment %d validation: %d warnings, %d errors",
                seg_id, len(result.warnings), len(result.errors),
            )
        results.append(result)
    return results
