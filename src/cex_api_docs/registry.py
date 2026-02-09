from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import CexApiDocsError


@dataclass(frozen=True, slots=True)
class ExchangeSection:
    section_id: str
    base_urls: list[str]
    seed_urls: list[str]


@dataclass(frozen=True, slots=True)
class Exchange:
    exchange_id: str
    display_name: str
    allowed_domains: list[str]
    sections: list[ExchangeSection]


@dataclass(frozen=True, slots=True)
class Registry:
    exchanges: list[Exchange]

    def get_exchange(self, exchange_id: str) -> Exchange:
        for ex in self.exchanges:
            if ex.exchange_id == exchange_id:
                return ex
        raise CexApiDocsError(code="ENOREG", message="Unknown exchange_id in registry.", details={"exchange_id": exchange_id})

    def get_section(self, exchange_id: str, section_id: str) -> ExchangeSection:
        ex = self.get_exchange(exchange_id)
        for sec in ex.sections:
            if sec.section_id == section_id:
                return sec
        raise CexApiDocsError(
            code="ENOREG",
            message="Unknown section_id for exchange in registry.",
            details={"exchange_id": exchange_id, "section_id": section_id},
        )


def load_registry(registry_path: Path) -> Registry:
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "exchanges" not in data:
        raise CexApiDocsError(code="EBADREG", message="Invalid exchanges.yaml (missing exchanges).", details={"path": str(registry_path)})

    exchanges_raw = data["exchanges"]
    if not isinstance(exchanges_raw, list):
        raise CexApiDocsError(code="EBADREG", message="Invalid exchanges.yaml (exchanges must be list).", details={"path": str(registry_path)})

    exchanges: list[Exchange] = []
    for ex in exchanges_raw:
        if not isinstance(ex, dict):
            continue
        sections: list[ExchangeSection] = []
        for sec in ex.get("sections", []) or []:
            if not isinstance(sec, dict):
                continue
            sections.append(
                ExchangeSection(
                    section_id=str(sec.get("section_id", "")),
                    base_urls=list(sec.get("base_urls", []) or []),
                    seed_urls=list(sec.get("seed_urls", []) or []),
                )
            )
        exchanges.append(
            Exchange(
                exchange_id=str(ex.get("exchange_id", "")),
                display_name=str(ex.get("display_name", "")),
                allowed_domains=list(ex.get("allowed_domains", []) or []),
                sections=sections,
            )
        )

    return Registry(exchanges=exchanges)

