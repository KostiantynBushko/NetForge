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

from collections.abc import Callable
from typing import Any

from netforge.adapters.base import Adapter, find_missing_dependencies
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


def _rest_requirements() -> tuple[tuple[str, Callable[[], Any]], ...]:
    """Return the packages the REST adapter needs, and the loader for each.

    The loaders are looked up when this is called rather than captured at
    import time, so that a test can replace one of them.
    """
    return (("fastapi", _load_fastapi), ("uvicorn", _load_uvicorn))


def _missing_dependencies() -> list[str]:
    """Return the names of the packages the REST adapter needs and lacks."""
    return find_missing_dependencies(_rest_requirements())


def _require_rest_dependencies(feature: str) -> None:
    """Raise unless every package the REST adapter needs is installed.

    Every missing package is named at once.  They come from the same extra,
    so a user who installs it should not have to run the command again to be
    told about the next one.
    """
    missing = _missing_dependencies()
    if missing:
        raise DependencyMissingError(missing, extra=REST_EXTRA, feature=feature)


class RestAdapter(Adapter):
    """The REST adapter."""

    name = "rest"
    description = "A REST API over the whole operation catalogue."

    def __init__(self, registry: OperationRegistry | None = None) -> None:
        self.registry = registry if registry is not None else OperationRegistry()

    def available(self) -> bool:
        """Return ``True`` when FastAPI and uvicorn are both installed.

        Both are needed to serve the API, so an adapter that could build
        the application but not serve it would be partial -- and a partial
        adapter is worse than none.
        """
        return not _missing_dependencies()

    def unavailable_reason(self) -> str | None:
        """Return why the adapter is not available."""
        missing = _missing_dependencies()
        if not missing:
            return None
        return str(
            DependencyMissingError(missing, extra=REST_EXTRA, feature="the REST adapter")
        )

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
    _load_fastapi()
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
    _require_rest_dependencies("serving the REST adapter")
    app = build_app(registry)
    uvicorn = _load_uvicorn()
    uvicorn.run(app, host=host, port=port)
    return 0
