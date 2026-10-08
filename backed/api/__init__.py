"""API 路由包：聚合各版本路由并挂载到应用。"""

from fastapi import FastAPI

from config import settings
from .hub import hub_router

__all__ = ["hub_router", "register_routers", "get_router_info"]


def register_routers(app: FastAPI) -> None:
    """将平台发布路由挂载到配置指定的 API 前缀（默认 /api/hub）。"""
    prefix = getattr(settings, "api_prefix", "/api/hub")
    app.include_router(hub_router, prefix=prefix)


def get_router_info() -> dict:
    """当前 API 路由概览（调试接口 /api/info 用）。"""
    routes = []
    for route in hub_router.routes:
        routes.append(
            {
                "path": getattr(route, "path", ""),
                "methods": sorted(getattr(route, "methods", None) or []),
                "name": getattr(route, "name", ""),
            }
        )
    return {
        "prefix": getattr(settings, "api_prefix", "/api/hub"),
        "routes": routes,
    }
