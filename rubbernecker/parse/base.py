# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

from typing import Generator, cast, Type
from avro.schema import Schema
import sys
import importlib
import pkgutil
import inspect
from abc import ABC, abstractmethod


class Parser(ABC):
    @abstractmethod
    def parse(self, record: object) -> Generator[object | None, None, None]: ...

    @abstractmethod
    def schema(self) -> Schema: ...


def list_parsers() -> list[Type[Parser]]:
    if not __package__:
        raise ValueError("Module name is not set. Cannot list parsers.")
    # Load all the modules to ensure that parser classes are registered
    module = importlib.import_module(__package__)
    if isinstance(module, str):
        module = importlib.import_module(module)
    results = {}
    for _, name, _ in pkgutil.walk_packages(module.__path__, module.__name__ + "."):
        try:
            results[name] = importlib.import_module(name)
        except Exception:
            pass  # Ignore modules that can't be imported
    # Find all classes that implement the Parser protocol
    classes: list[Type[Parser]] = []
    for mod in sys.modules.values():
        if mod and getattr(mod, "__name__", "").startswith(module.__name__):
            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if (
                    isinstance(obj, type)
                    and obj.__module__.startswith(module.__name__)
                    and issubclass(obj, Parser)
                    and obj is not Parser
                ):
                    classes.append(cast(Type[Parser], obj))
    return classes
