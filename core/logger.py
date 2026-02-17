"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/logger.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Centralized professional logging system for KPaperFlux.
                Supports console/file output, component-specific levels,
                and high-fidelity debugging for AI and Database.
------------------------------------------------------------------------------
"""

import logging
import sys
from pathlib import Path
from typing import Optional, Dict

# Root logger for the entire application
APP_LOGGER_NAME = "kpaperflux"

# Default format for log messages
DEFAULT_FORMAT = "%(asctime)s [%(levelname).4s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logging(
    level: str = "WARNING", 
    log_file: Optional[str] = None,
    component_levels: Optional[Dict[str, str]] = None
) -> None:
    """
    Sets up the global logging configuration.
    
    Args:
        level: The default logging level (DEBUG, INFO, WARNING, ERROR).
        log_file: Path to a file where logs should be saved.
        component_levels: Dict mapping component names (e.g. 'ai') to levels.
    """
    root = logging.getLogger(APP_LOGGER_NAME)
    
    # Remove existing handlers to avoid duplicates on re-setup
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        
    numeric_level = getattr(logging, level.upper(), logging.WARNING)
    root.setLevel(numeric_level)
    
    formatter = logging.Formatter(DEFAULT_FORMAT, datefmt=DATE_FORMAT)
    
    # 1. Console Handler (Stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)
    
    # 2. File Handler (Optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        
    # 3. Apply Component Overrides
    if component_levels:
        for component, cmp_level in component_levels.items():
            set_component_level(component, cmp_level)

def get_logger(name: str) -> logging.Logger:
    """
    Returns a logger instance for a specific component.
    Namespaced under 'kpaperflux.<name>'.
    """
    if name.startswith(APP_LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{APP_LOGGER_NAME}.{name}")

def set_component_level(component: str, level: str) -> None:
    """
    Dynamically changes the log level for a specific component.
    """
    logger = get_logger(component)
    numeric_level = getattr(logging, level.upper(), None)
    if numeric_level is not None:
        logger.setLevel(numeric_level)
        # Ensure the logger doesn't just inherit from root if we want it to be more verbose
        logger.propagate = True 

def log_ai_interaction(prompt: str, response: str, payload: Optional[dict] = None) -> None:
    """
    Specialized helper for high-fidelity AI debugging.
    Logged at DEBUG level on 'kpaperflux.ai.raw'.
    """
    logger = get_logger("ai.raw")
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("=== AI PROMPT START ===")
        logger.debug(prompt)
        logger.debug("=== AI RESPONSE START ===")
        logger.debug(response)
        if payload:
            import json
            logger.debug("=== AI PAYLOAD (EXTRACTED) ===")
            logger.debug(json.dumps(payload, indent=2))
        logger.debug("=== AI INTERACTION END ===")

def log_sql_query(query: str, params: Optional[tuple] = None, result_count: int = 0) -> None:
    """
    Specialized helper for database debugging.
    Logged at DEBUG level on 'kpaperflux.db.sql'.
    """
    logger = get_logger("db.sql")
    if logger.isEnabledFor(logging.DEBUG):
        msg = f"SQL: {query}"
        if params:
            msg += f" | PARAMS: {params}"
        msg += f" | RESULTS: {result_count}"
        logger.debug(msg)
