"""The REST adapter.

The REST API exposes the whole catalogue:

===========================  ==========================================
``GET  /health``             Is the framework up?
``GET  /operations``         The catalogue, with the filters.
``GET  /operations/{name}``  One operation, with its schemas.
``POST /operations/{name}``  Run an operation; the body is the request.
``GET  /categories``         The capability categories.
``GET  /risk``               The risk profile.
===========================  ==========================================

FastAPI is an optional extra.  It is imported lazily, so this module can
be imported -- and the adapter can be *listed* -- without it.
"""

from __future__ import annotations

from typing import Any

from netforge.adapters.base import Adapter, AdapterError
from netforge.core.context import ExecutionContext
from netforge.core.exceptions import DependencyMissingError, NetForgeError
from netforge.core.logging import get_logger
from netforge.models.capability import CapabilityCategory
from netforge.registry.registry import OperationRegistry

__all__ = ["RestAdapter", "build_app", "serve_rest"]

_logger = get_logger("adapters.rest")

REST_EXTRA = "rest"


def _load_fastapi():
    try:
        import fastapi
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise DependencyMissingError(
            "fastapi",
            extra=REST_EXTRA,
            feature="the REST adapter",
        ) from exc
    import fastapi

    return fastapi


def _load_uvicorn():
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise DependencyMissingError(
            "uvicorn",
            extra=REST_EXTRA,
            feature="serving the REST adapter",
        ) from exc
    import uvicorn

    return uvicorn


class RestAdapter(Adapter):
    """The REST adapter."""

    name = "rest"
    description = "A REST API over the whole operation catalogue."

    def __init__(self, registry: OperationRegistry | None = None) -> None:
        self.registry = registry if registry is not None else OperationRegistry()

    def available(self) -> bool:
        """Return ``True`` when FastAPI is installed."""
        try:
            _load_fastapi()
        except DependencyMissingError:
            return False
        return True

    def unavailable_reason(self) -> str | None:
        """Return why the adapter is not available."""
        try:
            _load_fastapi()
        except DependencyMissingError as exc:
            return str(exc)
        return None

    def describe(self) -> dict[str, Any]:
        """Return a description of the adapter."""
        return {
            "name": self.name,
            "description": self.description,
            "available": self.available(),
            "operations": len(self.registry),
            "reason": self.unavailable_reason(),
        }


def build_app(registry: OperationRegistry | None = None, *, max_risk: int = 4) -> Any:
    """Build the FastAPI application of the REST adapter."""
    fastapi = _load_fastapi()
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse

    registry = registry if registry is not None else OperationRegistry()
    context = ExecutionContext(max_risk=_risk_from_int(max_risk))

    app = FastAPI(
        title="NetForge",
        version="0.1.0",
        description="A modular network operations and security toolkit.",
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Report that the framework is up."""
        return {"status": "ok", "operations": len(registry)}

    @app.get("/operations")
    async def list_operations(
        category: str | None = None,
        risk: int | None = None,
        tag: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Return the catalogue."""
        descriptors = registry.list(category=category, max_risk=risk, tag=tag, query=query)
        return {
            "count": len(descriptors),
            "operations": [descriptor.model_dump(mode="json") for descriptor in descriptors],
        }

    @app.get("/operations/{name}")
    async def describe_operation(name: str) -> dict[str, Any]:
        """Return one operation."""
        try:
            descriptor = registry.get(name)
        except NetForgeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return descriptor.model_dump(mode="json")

    @app.post("/operations/{name}")
    async def run_operation(name: str, payload: dict[str, Any] | None = None) -> Any:
        """Run an operation."""
        try:
            operation = registry.create(name)
        except NetForgeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        try:
            response = await operation.run_request(payload or {}, context)
        except NetForgeError as exc:
            return JSONResponse(
                status_code=400,
                content={"error": type(exc).__name__, "detail": str(exc)},
            )
        return response.model_dump(mode="json")

    @app.get("/categories")
    async def categories() -> dict[str, Any]:
        """Return the capability categories."""
        return {
            "categories": {
                category.value: {
                    "label": CapabilityCategory(category).label,
                    "description": CapabilityCategory(category).description,
                    "operations": names,
                }
                for category, names in registry.categories().items()
            }
        }

    @app.get("/risk")
    async def risk() -> dict[str, Any]:
        """Return the risk profile."""
        return {"profile": registry.risk_profile(), "ceiling": int(context.max_risk)}

    return app


def _risk_from_int(value: int):
    from netforge.models.risk import RiskLevel

    try:
        return RiskLevel(value)
    except ValueError:
        return RiskLevel.SYSTEM_MODIFICATION


def serve_rest(
    registry: OperationRegistry | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> int:
    """Serve the REST API and block until it is interrupted."""
    uvicorn = _load_uvicorn()
    app = build_app(registry)
    uvicorn.run(app, host=host, port=port)
    return 0
