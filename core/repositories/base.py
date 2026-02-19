"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/repositories/base.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Base class for repository implementations. Provides shared 
                access to the central database manager and connection handle.
------------------------------------------------------------------------------
"""

import sqlite3
from typing import Optional

from core.database import DatabaseManager


class BaseRepository:
    """
    Abstract-style base repository providing shared database access.
    """

    def __init__(self, db_manager: DatabaseManager) -> None:
        """
        Initializes the repository with a database manager.

        Args:
            db_manager: The central database management instance.
        """
        self.db: DatabaseManager = db_manager

    @property
    def conn(self) -> sqlite3.Connection:
        """Dynamically retrieves the current connection handle from the DB manager."""
        return self.db.connection
