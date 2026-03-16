from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup

from .markdown import extract_block_metadata

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExtractionQuality:
    html_table_count: int
    md_table_count: int
    html_code_block_count: int
    md_code_block_count: int
    html_heading_count: int
    md_heading_count: int
    md_word_count: int
    tables_lost: int
    code_blocks_lost: int
    quality_score: float
    warnings: list[str] = field(default_factory=list)


def verify_extraction(html: str, md: str) -> ExtractionQuality:
    """Cross-check HTML structural elements against markdown output."""
    # HTML-side counting
    soup = BeautifulSoup(html, "html.parser")

    html_table_count = len(soup.find_all("table"))

    # Count <pre> tags as code block indicators.
    # <code> inside <pre> is part of the same block, so only count <pre>.
    html_code_block_count = len(soup.find_all("pre"))

    html_heading_count = len(
        soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    )

    # MD-side counting via extract_block_metadata
    block_meta = extract_block_metadata(md)
    md_table_count = len(block_meta["table_blocks"])
    md_code_block_count = len(block_meta["code_blocks"])
    md_heading_count = len(block_meta["headings"])

    md_word_count = len(md.split())

    # Losses
    tables_lost = max(html_table_count - md_table_count, 0)
    code_blocks_lost = max(html_code_block_count - md_code_block_count, 0)

    # Quality score (pinned formula)
    # When both counts are 0, nothing existed to lose → perfect ratio (1.0).
    table_ratio = 1.0 if html_table_count == 0 else min(md_table_count / html_table_count, 1.0)
    code_ratio = 1.0 if html_code_block_count == 0 else min(md_code_block_count / html_code_block_count, 1.0)
    heading_ratio = 1.0 if html_heading_count == 0 else min(md_heading_count / html_heading_count, 1.0)
    word_ratio = 1.0 if md_word_count >= 40 else md_word_count / 40.0

    quality_score = (
        0.35 * table_ratio
        + 0.30 * code_ratio
        + 0.15 * heading_ratio
        + 0.20 * word_ratio
    )

    # Warnings
    warnings: list[str] = []
    if tables_lost > 0:
        warnings.append(f"{tables_lost} tables lost in extraction")
    if code_blocks_lost > 0:
        warnings.append(f"{code_blocks_lost} code blocks lost in extraction")
    if md_word_count == 0 and html_heading_count > 0:
        warnings.append("Markdown is empty despite HTML having content")
    if quality_score < 0.40:
        warnings.append(f"Low extraction quality: {quality_score:.2f}")

    return ExtractionQuality(
        html_table_count=html_table_count,
        md_table_count=md_table_count,
        html_code_block_count=html_code_block_count,
        md_code_block_count=md_code_block_count,
        html_heading_count=html_heading_count,
        md_heading_count=md_heading_count,
        md_word_count=md_word_count,
        tables_lost=tables_lost,
        code_blocks_lost=code_blocks_lost,
        quality_score=quality_score,
        warnings=warnings,
    )
