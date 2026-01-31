"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/models/__init__.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Package initializer for core data models. Exports PhysicalFile,
                VirtualDocument, and related entities for easy access.
------------------------------------------------------------------------------
"""

from .physical import PhysicalFile
from .virtual import VirtualDocument, SourceReference, VirtualPage
from .canonical_entity import CanonicalEntity
