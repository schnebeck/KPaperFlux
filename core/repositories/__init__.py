"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/repositories/__init__.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Package initializer for core repositories. Exports PhysicalRepository
                and LogicalRepository for centralized persistence management.
------------------------------------------------------------------------------
"""

from .physical_repo import PhysicalRepository
from .logical_repo import LogicalRepository
