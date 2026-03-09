from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cex_api_docs.coverage import endpoint_coverage
from cex_api_docs.endpoints import get_endpoint, search_endpoints
from cex_api_docs.openapi_import import (
    _resolve_ref,
    _resolve_refs,
    import_openapi,
)
from cex_api_docs.store import init_store
from tests.http_server import serve_directory


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestImportOpenApi(unittest.TestCase):
    def test_import_openapi_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            site.mkdir(parents=True, exist_ok=True)

            (site / "openapi.yaml").write_text(
                "\n".join(
                    [
                        "openapi: 3.0.0",
                        "info:",
                        "  title: Test API",
                        "  version: 1.0.0",
                        "servers:",
                        "  - url: https://api.test.example",
                        "paths:",
                        "  /api/v1/time:",
                        "    get:",
                        "      summary: Get server time",
                        "      responses:",
                        "        '200':",
                        "          description: OK",
                        "  /api/v1/ping:",
                        "    get:",
                        "      summary: Ping",
                        "      responses:",
                        "        '200':",
                        "          description: OK",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            docs_dir = Path(tmp) / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            with serve_directory(site) as base_url:
                spec_url = f"{base_url}/openapi.yaml"
                r = import_openapi(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange="binance",
                    section="spot",
                    url=spec_url,
                    base_url=None,
                    api_version=None,
                    timeout_s=5.0,
                    max_bytes=5_000_000,
                    max_redirects=3,
                    retries=0,
                    continue_on_error=False,
                )

            self.assertEqual(r["counts"]["ok"], 2)
            self.assertEqual(r["counts"]["errors"], 0)

            matches = search_endpoints(docs_dir=str(docs_dir), query="/api/v1/time", exchange="binance", section="spot", limit=10)
            self.assertTrue(any(m["path"] == "/api/v1/time" for m in matches))

            cov = endpoint_coverage(docs_dir=str(docs_dir), exchange="binance", section="spot", limit_samples=2)
            self.assertEqual(cov["totals"]["endpoints"], 2)


# ---------------------------------------------------------------------------
# _resolve_ref / _resolve_refs unit tests
# ---------------------------------------------------------------------------


class TestResolveRef(unittest.TestCase):
    """Unit tests for _resolve_ref (single pointer resolution)."""

    def test_resolve_parameter_ref(self) -> None:
        root = {
            "components": {
                "parameters": {
                    "symbol": {
                        "name": "symbol",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                }
            }
        }
        result = _resolve_ref("#/components/parameters/symbol", root)
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "symbol")
        self.assertEqual(result["in"], "query")
        self.assertTrue(result["required"])
        self.assertEqual(result["schema"], {"type": "string"})

    def test_resolve_schema_ref(self) -> None:
        root = {
            "components": {
                "schemas": {
                    "OrderRequest": {
                        "type": "object",
                        "properties": {
                            "price": {"type": "number"},
                            "quantity": {"type": "number"},
                        },
                        "required": ["price", "quantity"],
                    }
                }
            }
        }
        result = _resolve_ref("#/components/schemas/OrderRequest", root)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "object")
        self.assertIn("price", result["properties"])

    def test_resolve_response_ref(self) -> None:
        root = {
            "components": {
                "responses": {
                    "NotFound": {
                        "description": "Resource not found",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "properties": {"error": {"type": "string"}}}
                            }
                        },
                    }
                }
            }
        }
        result = _resolve_ref("#/components/responses/NotFound", root)
        self.assertIsNotNone(result)
        self.assertEqual(result["description"], "Resource not found")

    def test_external_ref_returns_none(self) -> None:
        root = {"components": {}}
        result = _resolve_ref("other-file.yaml#/components/schemas/Foo", root)
        self.assertIsNone(result)

    def test_missing_ref_returns_none(self) -> None:
        root = {"components": {"schemas": {}}}
        result = _resolve_ref("#/components/schemas/NonExistent", root)
        self.assertIsNone(result)

    def test_non_dict_ref_target_returns_none(self) -> None:
        root = {"components": {"schemas": {"JustAString": "not-a-dict"}}}
        result = _resolve_ref("#/components/schemas/JustAString", root)
        self.assertIsNone(result)

    def test_ref_to_nested_path(self) -> None:
        root = {
            "components": {
                "schemas": {
                    "deep": {
                        "nested": {"value": 42}
                    }
                }
            }
        }
        result = _resolve_ref("#/components/schemas/deep", root)
        self.assertIsNotNone(result)
        self.assertEqual(result["nested"]["value"], 42)

    def test_ref_outside_components(self) -> None:
        """Refs can point anywhere in the document, not just components."""
        root = {
            "info": {"title": "My API"},
            "components": {},
        }
        result = _resolve_ref("#/info", root)
        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "My API")


class TestResolveRefs(unittest.TestCase):
    """Unit tests for _resolve_refs (recursive resolution)."""

    def _make_spec_root(self) -> dict:
        return {
            "components": {
                "parameters": {
                    "symbol": {
                        "name": "symbol",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "enum": ["BTCUSDT", "ETHUSDT"]},
                    },
                    "limit": {
                        "name": "limit",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer", "minimum": 1, "maximum": 1000},
                    },
                },
                "schemas": {
                    "OrderRequest": {
                        "type": "object",
                        "properties": {
                            "price": {"type": "number"},
                            "quantity": {"type": "number"},
                            "symbol": {"$ref": "#/components/schemas/SymbolEnum"},
                        },
                        "required": ["price", "quantity", "symbol"],
                    },
                    "SymbolEnum": {
                        "type": "string",
                        "enum": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
                    },
                    "SuccessResponse": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "integer"},
                            "data": {"type": "object"},
                        },
                    },
                },
                "responses": {
                    "OkResponse": {
                        "description": "Success",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/SuccessResponse"}
                            }
                        },
                    }
                },
            }
        }

    def test_parameter_refs_in_list(self) -> None:
        """$ref items in a parameters array are resolved."""
        root = self._make_spec_root()
        obj = {
            "parameters": [
                {"$ref": "#/components/parameters/symbol"},
                {"$ref": "#/components/parameters/limit"},
            ]
        }
        result = _resolve_refs(obj, root)
        self.assertEqual(len(result["parameters"]), 2)
        self.assertEqual(result["parameters"][0]["name"], "symbol")
        self.assertTrue(result["parameters"][0]["required"])
        self.assertEqual(result["parameters"][0]["schema"]["enum"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(result["parameters"][1]["name"], "limit")
        self.assertFalse(result["parameters"][1]["required"])
        self.assertEqual(result["parameters"][1]["schema"]["minimum"], 1)

    def test_mixed_inline_and_ref_parameters(self) -> None:
        """Inline parameters are preserved alongside resolved $ref parameters."""
        root = self._make_spec_root()
        obj = {
            "parameters": [
                {"$ref": "#/components/parameters/symbol"},
                {"name": "side", "in": "query", "required": True, "schema": {"type": "string"}},
            ]
        }
        result = _resolve_refs(obj, root)
        self.assertEqual(len(result["parameters"]), 2)
        # First is resolved from $ref
        self.assertEqual(result["parameters"][0]["name"], "symbol")
        self.assertIn("enum", result["parameters"][0]["schema"])
        # Second is inline — unchanged
        self.assertEqual(result["parameters"][1]["name"], "side")
        self.assertTrue(result["parameters"][1]["required"])

    def test_nested_schema_refs(self) -> None:
        """$refs inside a resolved schema are also resolved (nested resolution)."""
        root = self._make_spec_root()
        obj = {
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/OrderRequest"}
                    }
                }
            }
        }
        result = _resolve_refs(obj, root)
        schema = result["requestBody"]["content"]["application/json"]["schema"]
        self.assertEqual(schema["type"], "object")
        # The nested $ref in OrderRequest.properties.symbol should also be resolved
        symbol_prop = schema["properties"]["symbol"]
        self.assertNotIn("$ref", symbol_prop)
        self.assertEqual(symbol_prop["type"], "string")
        self.assertEqual(symbol_prop["enum"], ["BTCUSDT", "ETHUSDT", "BNBUSDT"])

    def test_response_ref(self) -> None:
        """Top-level response $refs are resolved."""
        root = self._make_spec_root()
        obj = {
            "responses": {
                "200": {"$ref": "#/components/responses/OkResponse"}
            }
        }
        result = _resolve_refs(obj, root)
        resp_200 = result["responses"]["200"]
        self.assertEqual(resp_200["description"], "Success")
        # The nested schema $ref inside the response should also be resolved
        resp_schema = resp_200["content"]["application/json"]["schema"]
        self.assertEqual(resp_schema["type"], "object")
        self.assertIn("code", resp_schema["properties"])

    def test_external_ref_left_unresolved(self) -> None:
        """External $refs are kept as-is."""
        root = {"components": {}}
        obj = {"schema": {"$ref": "other-file.yaml#/components/schemas/Foo"}}
        result = _resolve_refs(obj, root)
        self.assertEqual(result["schema"]["$ref"], "other-file.yaml#/components/schemas/Foo")

    def test_missing_ref_left_unresolved(self) -> None:
        """$refs pointing to non-existent targets are kept as-is."""
        root = {"components": {"schemas": {}}}
        obj = {"schema": {"$ref": "#/components/schemas/DoesNotExist"}}
        result = _resolve_refs(obj, root)
        self.assertEqual(result["schema"]["$ref"], "#/components/schemas/DoesNotExist")

    def test_circular_ref_depth_limit(self) -> None:
        """Circular $refs stop at the depth limit instead of infinite looping."""
        root = {
            "components": {
                "schemas": {
                    "TreeNode": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "string"},
                            "children": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/TreeNode"},
                            },
                        },
                    }
                }
            }
        }
        obj = {"$ref": "#/components/schemas/TreeNode"}
        # Should complete without hanging; depth limit prevents infinite recursion.
        result = _resolve_refs(obj, root)
        self.assertEqual(result["type"], "object")
        self.assertIn("children", result["properties"])
        # At some depth, the $ref will stop being resolved and remain as-is.
        node = result
        for _ in range(25):
            items = node.get("properties", {}).get("children", {}).get("items", {})
            if "$ref" in items:
                # Hit the depth limit — $ref is preserved as-is
                self.assertEqual(items["$ref"], "#/components/schemas/TreeNode")
                break
            node = items
        else:
            self.fail("Expected depth-limited $ref to remain unresolved at some depth")

    def test_scalar_values_unchanged(self) -> None:
        """Non-dict, non-list values pass through unchanged."""
        root = {"components": {}}
        self.assertEqual(_resolve_refs("hello", root), "hello")
        self.assertEqual(_resolve_refs(42, root), 42)
        self.assertIsNone(_resolve_refs(None, root))
        self.assertTrue(_resolve_refs(True, root))

    def test_empty_components_no_error(self) -> None:
        """When components is empty, $refs are left unresolved without errors."""
        root = {"components": {}}
        obj = {
            "parameters": [
                {"$ref": "#/components/parameters/symbol"}
            ]
        }
        result = _resolve_refs(obj, root)
        self.assertEqual(result["parameters"][0]["$ref"], "#/components/parameters/symbol")

    def test_ref_with_extra_keys_not_resolved(self) -> None:
        """A dict with $ref plus other keys is not treated as a pure $ref."""
        root = {
            "components": {
                "schemas": {
                    "Base": {"type": "string"}
                }
            }
        }
        obj = {"$ref": "#/components/schemas/Base", "description": "overridden"}
        result = _resolve_refs(obj, root)
        # Should NOT resolve because $ref is not the only key
        self.assertIn("$ref", result)
        self.assertEqual(result["description"], "overridden")


# ---------------------------------------------------------------------------
# Integration: import a spec with $refs and verify schemas are resolved
# ---------------------------------------------------------------------------


class TestImportOpenApiWithRefs(unittest.TestCase):
    """Integration test: import a spec containing $ref parameters and verify resolution."""

    def _make_spec_yaml(self) -> str:
        """Build a YAML spec with $ref parameters, requestBody schema, and response refs."""
        return "\n".join([
            "openapi: '3.0.0'",
            "info:",
            "  title: Ref Test API",
            "  version: '1.0.0'",
            "servers:",
            "  - url: https://api.reftest.example",
            "components:",
            "  parameters:",
            "    SymbolParam:",
            "      name: symbol",
            "      in: query",
            "      required: true",
            "      schema:",
            "        type: string",
            "        enum:",
            "          - BTCUSDT",
            "          - ETHUSDT",
            "    LimitParam:",
            "      name: limit",
            "      in: query",
            "      required: false",
            "      schema:",
            "        type: integer",
            "        minimum: 1",
            "        maximum: 1000",
            "  schemas:",
            "    OrderBody:",
            "      type: object",
            "      properties:",
            "        price:",
            "          type: number",
            "        quantity:",
            "          type: number",
            "      required:",
            "        - price",
            "        - quantity",
            "    SuccessResp:",
            "      type: object",
            "      properties:",
            "        code:",
            "          type: integer",
            "        msg:",
            "          type: string",
            "  responses:",
            "    StandardOK:",
            "      description: Standard success",
            "      content:",
            "        application/json:",
            "          schema:",
            "            $ref: '#/components/schemas/SuccessResp'",
            "paths:",
            "  /api/v1/ticker:",
            "    get:",
            "      summary: Get ticker price",
            "      parameters:",
            "        - $ref: '#/components/parameters/SymbolParam'",
            "        - $ref: '#/components/parameters/LimitParam'",
            "      responses:",
            "        '200':",
            "          $ref: '#/components/responses/StandardOK'",
            "  /api/v1/order:",
            "    post:",
            "      summary: Place order",
            "      parameters:",
            "        - $ref: '#/components/parameters/SymbolParam'",
            "        - name: side",
            "          in: query",
            "          required: true",
            "          schema:",
            "            type: string",
            "      requestBody:",
            "        content:",
            "          application/json:",
            "            schema:",
            "              $ref: '#/components/schemas/OrderBody'",
            "      responses:",
            "        '200':",
            "          description: Order placed",
            "",
        ])

    def test_refs_resolved_in_stored_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            site.mkdir(parents=True, exist_ok=True)
            (site / "openapi.yaml").write_text(self._make_spec_yaml(), encoding="utf-8")

            docs_dir = Path(tmp) / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            with serve_directory(site) as base_url:
                spec_url = f"{base_url}/openapi.yaml"
                r = import_openapi(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange="testex",
                    section="v1",
                    url=spec_url,
                    base_url=None,
                    api_version=None,
                    timeout_s=5.0,
                    max_bytes=5_000_000,
                    max_redirects=3,
                    retries=0,
                    continue_on_error=False,
                )

            self.assertEqual(r["counts"]["ok"], 2)
            self.assertEqual(r["counts"]["errors"], 0)

            # Find the ticker endpoint
            matches = search_endpoints(docs_dir=str(docs_dir), query="ticker", exchange="testex", section="v1", limit=10)
            ticker_eps = [m for m in matches if m["path"] == "/api/v1/ticker"]
            self.assertTrue(len(ticker_eps) > 0, "Expected to find /api/v1/ticker endpoint")
            ticker_id = ticker_eps[0]["endpoint_id"]

            ep = get_endpoint(docs_dir=str(docs_dir), endpoint_id=ticker_id)
            req = ep["request_schema"]
            self.assertIsNotNone(req, "request_schema should be set")

            # Parameters should be resolved, not $ref pointers
            params = req["parameters"]
            self.assertEqual(len(params), 2)
            # First param: symbol (was $ref to SymbolParam)
            self.assertEqual(params[0]["name"], "symbol")
            self.assertTrue(params[0]["required"])
            self.assertEqual(params[0]["schema"]["type"], "string")
            self.assertEqual(params[0]["schema"]["enum"], ["BTCUSDT", "ETHUSDT"])
            # Second param: limit (was $ref to LimitParam)
            self.assertEqual(params[1]["name"], "limit")
            self.assertFalse(params[1]["required"])
            self.assertEqual(params[1]["schema"]["minimum"], 1)

            # Response should be resolved (was $ref to StandardOK -> nested $ref to SuccessResp)
            resp = ep["response_schema"]
            self.assertIsNotNone(resp)
            resp_200 = resp["responses"]["200"]
            self.assertEqual(resp_200["description"], "Standard success")
            resp_schema = resp_200["content"]["application/json"]["schema"]
            self.assertEqual(resp_schema["type"], "object")
            self.assertIn("code", resp_schema["properties"])

            # Find the order endpoint
            order_matches = search_endpoints(docs_dir=str(docs_dir), query="order", exchange="testex", section="v1", limit=10)
            order_eps = [m for m in order_matches if m["path"] == "/api/v1/order"]
            self.assertTrue(len(order_eps) > 0, "Expected to find /api/v1/order endpoint")
            order_id = order_eps[0]["endpoint_id"]

            ep2 = get_endpoint(docs_dir=str(docs_dir), endpoint_id=order_id)
            req2 = ep2["request_schema"]
            self.assertIsNotNone(req2)

            # Mixed inline + $ref parameters
            params2 = req2["parameters"]
            self.assertEqual(len(params2), 2)
            self.assertEqual(params2[0]["name"], "symbol")
            self.assertEqual(params2[1]["name"], "side")
            self.assertTrue(params2[1]["required"])

            # requestBody schema should be resolved (was $ref to OrderBody)
            body_schema = req2["requestBody"]["content"]["application/json"]["schema"]
            self.assertEqual(body_schema["type"], "object")
            self.assertIn("price", body_schema["properties"])
            self.assertIn("quantity", body_schema["properties"])
            self.assertEqual(body_schema["required"], ["price", "quantity"])


if __name__ == "__main__":
    unittest.main()

