"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_cancellation_token.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    Unit tests for CancellationToken and its integration with
                PipelineProcessor.terminate_activity().
------------------------------------------------------------------------------
"""

import os
from concurrent.futures import CancelledError

import pytest

from core.pipeline import CancellationToken, PipelineProcessor
from core.database import DatabaseManager


# ── CancellationToken unit tests ───────────────────────────────────────────

def test_token_starts_not_cancelled() -> None:
    """A freshly created token must not be cancelled."""
    token = CancellationToken()
    assert token.is_cancelled is False


def test_cancel_sets_is_cancelled() -> None:
    """Calling cancel() must flip is_cancelled to True."""
    token = CancellationToken()
    token.cancel()
    assert token.is_cancelled is True


def test_check_raises_on_cancelled() -> None:
    """check() must raise CancelledError when the token is cancelled."""
    token = CancellationToken()
    token.cancel()
    with pytest.raises(CancelledError):
        token.check()


def test_check_does_not_raise_when_not_cancelled() -> None:
    """check() must be a no-op when the token has not been cancelled."""
    token = CancellationToken()
    # Must not raise
    token.check()


def test_reset_clears_cancellation() -> None:
    """reset() must allow reuse of a previously cancelled token."""
    token = CancellationToken()
    token.cancel()
    assert token.is_cancelled is True

    token.reset()
    assert token.is_cancelled is False

    # check() must not raise after reset
    token.check()


# ── PipelineProcessor integration test ────────────────────────────────────

def test_terminate_activity_cancels_token(tmp_path) -> None:
    """terminate_activity() must set the pipeline's cancellation token."""
    db_path = str(tmp_path / "test_cancel.db")
    vault_path = str(tmp_path / "vault")
    os.makedirs(vault_path)

    db_manager = DatabaseManager(db_path)
    db_manager.init_db()

    pipeline = PipelineProcessor(base_path=vault_path, db=db_manager)

    # Token starts clear
    assert pipeline._token.is_cancelled is False

    pipeline.terminate_activity()

    assert pipeline._token.is_cancelled is True


def test_reset_cancellation_clears_token(tmp_path) -> None:
    """reset_cancellation() must clear the token so the next run is clean."""
    db_path = str(tmp_path / "test_reset.db")
    vault_path = str(tmp_path / "vault")
    os.makedirs(vault_path)

    db_manager = DatabaseManager(db_path)
    db_manager.init_db()

    pipeline = PipelineProcessor(base_path=vault_path, db=db_manager)

    pipeline.terminate_activity()
    assert pipeline._token.is_cancelled is True

    pipeline.reset_cancellation()
    assert pipeline._token.is_cancelled is False
