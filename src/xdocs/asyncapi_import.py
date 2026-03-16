from __future__ import annotations

from typing import Any

from .errors import XDocsError


def import_asyncapi(**_kwargs: Any) -> dict[str, Any]:
    # Stub for planned AsyncAPI support.
    raise XDocsError(
        code="ENOTIMPL",
        message="AsyncAPI import is not implemented yet. Use `ingest-page` + `save-endpoint` for now, or contribute an AsyncAPI importer.",
        details={"hint": "planned_command=import-asyncapi"},
    )
