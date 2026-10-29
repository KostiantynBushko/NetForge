"""The operation registry.

The registry is the catalogue of everything NetForge can do.  Adapters read
from it; nothing else is a source of truth.
"""

from __future__ import annotations

from netforge.registry.descriptor import OperationDescriptor
from netforge.registry.registry import OperationRegistry, descriptors_as_dicts

__all__ = ["OperationDescriptor", "OperationRegistry", "descriptors_as_dicts"]
