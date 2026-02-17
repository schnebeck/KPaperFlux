"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_logger.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Unit tests for the centralized logging system.
------------------------------------------------------------------------------
"""

import logging
import os
import pytest
from pathlib import Path
from core.logger import setup_logging, get_logger, set_component_level

def test_logger_singleton_root():
    """Verify that get_logger returns a child of the kpaperflux root."""
    logger = get_logger("core")
    assert logger.name == "kpaperflux.core"
    assert isinstance(logger, logging.Logger)

def test_logging_to_file(tmp_path):
    """Verify that logs are correctly written to a file."""
    log_file = tmp_path / "app.log"
    setup_logging(level="DEBUG", log_file=str(log_file))
    
    logger = get_logger("test")
    test_msg = "Logging to file test message"
    logger.debug(test_msg)
    
    # Flush logging handlers
    for handler in logging.getLogger("kpaperflux").handlers:
        handler.flush()
        
    assert log_file.exists()
    content = log_file.read_text()
    assert test_msg in content

def test_component_level_overrides(tmp_path):
    """Verify that specific components can have different log levels."""
    log_file = tmp_path / "component.log"
    setup_logging(level="INFO", log_file=str(log_file))
    
    ai_logger = get_logger("ai")
    db_logger = get_logger("db")
    
    # Set AI to DEBUG independently
    set_component_level("ai", "DEBUG")
    
    ai_msg = "AI DEBUG MESSAGE"
    db_msg = "DB DEBUG MESSAGE"
    
    ai_logger.debug(ai_msg)
    db_logger.debug(db_msg)
    
    # Flush
    for handler in logging.getLogger("kpaperflux").handlers:
        handler.flush()
        
    content = log_file.read_text()
    assert ai_msg in content
    assert db_msg not in content # DB should still be at INFO level (default)

def test_quiet_default_mode(tmp_path):
    """Verify that the system is quiet at Default level."""
    log_file = tmp_path / "quiet.log"
    setup_logging(level="WARNING", log_file=str(log_file))
    
    logger = get_logger("core")
    logger.info("THIS SHOULD NOT APPEAR")
    
    # Flush
    for handler in logging.getLogger("kpaperflux").handlers:
        handler.flush()
        
    content = log_file.read_text()
    assert "THIS SHOULD NOT APPEAR" not in content
