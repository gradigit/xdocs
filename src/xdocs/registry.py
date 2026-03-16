from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import XDocsError

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DocSource:
    # Planned kinds: sitemap|openapi|postman|asyncapi|nav_index|other
    kind: str
    url: str
    scope: str | None = None  # optional path/url prefix constraint
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class InventoryPolicy:
    # inventory: sitemap-based enumeration (default)
    # link_follow: deterministic link extraction from seed pages (fallback for docs without sitemaps)
    mode: str = "inventory"  # inventory|link_follow
    max_pages: int | None = None
    render_mode: str | None = None  # http|playwright|auto (None => use CLI default)
    scope_prefixes: list[str] = field(default_factory=list)  # optional explicit URL prefixes
    # Cross-section dedupe ownership controls.
    # If unset, sync defaults this to "<exchange_id>" for exchange-local dedupe.
    scope_group: str | None = None
    # Lower value = higher priority ownership.
    scope_priority: int = 100


@dataclass(frozen=True, slots=True)
class RenderOptions:
    scroll_full_page: bool = False
    expand_accordions: bool = False


@dataclass(frozen=True, slots=True)
class ExchangeSection:
    section_id: str
    base_urls: list[str]
    seed_urls: list[str]
    doc_sources: list[DocSource] = field(default_factory=list)
    inventory_policy: InventoryPolicy = field(default_factory=InventoryPolicy)
    render_options: RenderOptions = field(default_factory=RenderOptions)


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
        raise XDocsError(code="ENOREG", message="Unknown exchange_id in registry.", details={"exchange_id": exchange_id})

    def get_section(self, exchange_id: str, section_id: str) -> ExchangeSection:
        ex = self.get_exchange(exchange_id)
        for sec in ex.sections:
            if sec.section_id == section_id:
                return sec
        raise XDocsError(
            code="ENOREG",
            message="Unknown section_id for exchange in registry.",
            details={"exchange_id": exchange_id, "section_id": section_id},
        )


def load_registry(registry_path: Path) -> Registry:
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "exchanges" not in data:
        raise XDocsError(code="EBADREG", message="Invalid exchanges.yaml (missing exchanges).", details={"path": str(registry_path)})

    exchanges_raw = data["exchanges"]
    if not isinstance(exchanges_raw, list):
        raise XDocsError(code="EBADREG", message="Invalid exchanges.yaml (exchanges must be list).", details={"path": str(registry_path)})

    exchanges: list[Exchange] = []
    for ex in exchanges_raw:
        if not isinstance(ex, dict):
            continue
        sections: list[ExchangeSection] = []
        for sec in ex.get("sections", []) or []:
            if not isinstance(sec, dict):
                continue

            # Optional doc sources (sitemaps/specs) for better exhaustiveness.
            doc_sources: list[DocSource] = []
            for ds in sec.get("doc_sources", []) or []:
                if not isinstance(ds, dict):
                    continue
                url = str(ds.get("url", "")).strip()
                kind = str(ds.get("kind", "")).strip()
                if not url or not kind:
                    continue
                doc_sources.append(
                    DocSource(
                        kind=kind,
                        url=url,
                        scope=str(ds.get("scope")).strip() if ds.get("scope") else None,
                        notes=str(ds.get("notes")).strip() if ds.get("notes") else None,
                    )
                )

            pol_raw = sec.get("inventory_policy") or {}
            if not isinstance(pol_raw, dict):
                pol_raw = {}
            inv_policy = InventoryPolicy(
                mode=str(pol_raw.get("mode") or "inventory"),
                max_pages=int(pol_raw["max_pages"]) if pol_raw.get("max_pages") is not None else None,
                render_mode=str(pol_raw["render_mode"]).strip() if pol_raw.get("render_mode") else None,
                scope_prefixes=[str(x) for x in (pol_raw.get("scope_prefixes") or []) if x],
                scope_group=str(pol_raw["scope_group"]).strip() if pol_raw.get("scope_group") else None,
                scope_priority=int(pol_raw.get("scope_priority") or 100),
            )

            # Warn if scope_prefixes is at section level (should be inside inventory_policy).
            if sec.get("scope_prefixes") and not pol_raw.get("scope_prefixes"):
                _log.warning(
                    "%s/%s: scope_prefixes found at section level, not inside inventory_policy — ignored. "
                    "Move it into inventory_policy to take effect.",
                    ex.get("exchange_id", "?"), sec.get("section_id", "?"),
                )

            ro_raw = sec.get("render_options") or {}
            if not isinstance(ro_raw, dict):
                ro_raw = {}
            render_opts = RenderOptions(
                scroll_full_page=bool(ro_raw.get("scroll_full_page", False)),
                expand_accordions=bool(ro_raw.get("expand_accordions", False)),
            )

            sections.append(
                ExchangeSection(
                    section_id=str(sec.get("section_id", "")),
                    base_urls=list(sec.get("base_urls", []) or []),
                    seed_urls=list(sec.get("seed_urls", []) or []),
                    doc_sources=doc_sources,
                    inventory_policy=inv_policy,
                    render_options=render_opts,
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
