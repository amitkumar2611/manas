"""Uniform registry: agents, tools, providers, memories all register here.

Adding a component NEVER requires editing kernel code (open/closed principle).
"""
from typing import Any, Callable, TypeVar

from manas.kernel.errors import RegistryError

T = TypeVar("T")


class Registry:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._items: dict[str, Any] = {}

    def register(self, name: str) -> Callable[[T], T]:
        def deco(obj: T) -> T:
            if name in self._items:
                raise RegistryError(f"{self.kind} '{name}' already registered")
            self._items[name] = obj
            return obj
        return deco

    def get(self, name: str) -> Any:
        try:
            return self._items[name]
        except KeyError:
            raise RegistryError(
                f"unknown {self.kind} '{name}'; available: {sorted(self._items)}"
            ) from None

    def names(self) -> list[str]:
        return sorted(self._items)


agents = Registry("agent")
tools = Registry("tool")
providers = Registry("provider")
memories = Registry("memory")
