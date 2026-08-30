from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from fastapi import APIRouter
from fastapi.params import Depends as DependsParam

def route(
    path: str,
    *,
    methods: list[str],
    middlewares: Sequence[DependsParam] | None = None,
    **kwargs: Any,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """为类视图方法声明路由元数据。

    Args:
        path: 路由相对路径。
        methods: HTTP 方法列表。
        middlewares: 路由级中间件列表，按 FastAPI 依赖项方式声明。
        **kwargs: 透传给 `APIRouter.add_api_route` 的其他配置。

    Returns:
        Callable[[Callable[..., Any]], Callable[..., Any]]: 装饰后的原始方法。
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        """将路由元数据挂载到方法对象上。"""
        route_kwargs = dict(kwargs)
        if middlewares is not None:
            dependencies = list(route_kwargs.get("dependencies") or [])
            dependencies.extend(middlewares)
            route_kwargs["dependencies"] = dependencies
    
        setattr(
            func,
            "__route_config__",
            {
                "path": path,
                "methods": methods,
                **route_kwargs,
            },
        )
        return func

    return decorator


class BaseView:
    """类视图基类。"""

    router_prefix = ""
    router_tags: list[str] = []

    def __init__(self) -> None:
        """初始化类视图对应的路由器并自动注册已声明路由。"""
        self.router = APIRouter(prefix=self.router_prefix, tags=self.router_tags)
        self._register_routes()

    def __call__(self) -> APIRouter:
        """在视图实例被调用时返回内部路由器。

        Returns:
            APIRouter: 当前视图实例维护的路由器对象。
        """
        return self.router

    @classmethod
    def _iter_route_methods(cls) -> list[tuple[str, dict[str, Any]]]:
        """按定义顺序收集当前类上的路由方法。

        Returns:
            list[tuple[str, dict[str, Any]]]: 方法名与路由配置列表。
        """
        routes: list[tuple[str, dict[str, Any]]] = []
        for current_cls in reversed(cls.mro()):
            if not issubclass(current_cls, BaseView) or current_cls is BaseView:
                continue
            for name, value in current_cls.__dict__.items():
                config = getattr(value, "__route_config__", None)
                if config is not None:
                    routes.append((name, config))
        return routes

    def _register_routes(self) -> None:
        """将已声明的类方法自动注册到 `APIRouter`。"""
        for method_name, config in self._iter_route_methods():
            endpoint = getattr(self, method_name)
            route_kwargs = {key: value for key, value in config.items() if key != "path"}
            self.router.add_api_route(config["path"], endpoint, **route_kwargs)

    