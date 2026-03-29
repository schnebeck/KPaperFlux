"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/unit/test_saved_layouts.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Code
Description:    Unit tests for the DB-backed saved_layouts feature
                (DatabaseManager.save_layout, list_layouts, load_layout,
                delete_layout).
------------------------------------------------------------------------------
"""

import pytest
from core.database import DatabaseManager


@pytest.fixture
def db() -> DatabaseManager:
    """In-memory DatabaseManager for isolated tests."""
    return DatabaseManager(":memory:")


SAMPLE_REPORTS = [
    {
        "id": "default_monthly",
        "name": "Monthly Invoices",
        "group_by": "doc_date:month",
        "visualizations": ["bar_chart", "table"],
        "components": [],
        "filter_query": {},
        "description": "",
    }
]


def test_save_and_list_layout(db: DatabaseManager) -> None:
    """Saving a layout makes it appear in list_layouts."""
    assert db.list_layouts() == []

    layout_id = db.save_layout("My Test Layout", SAMPLE_REPORTS)

    assert isinstance(layout_id, str) and layout_id
    layouts = db.list_layouts()
    assert len(layouts) == 1
    assert layouts[0]["name"] == "My Test Layout"
    assert layouts[0]["id"] == layout_id
    assert layouts[0]["created_at"] is not None
    assert layouts[0]["last_used_at"] is None


def test_load_layout_updates_last_used(db: DatabaseManager) -> None:
    """Loading a layout sets last_used_at in the DB."""
    layout_id = db.save_layout("Layout A", SAMPLE_REPORTS)

    before = db.list_layouts()[0]["last_used_at"]
    assert before is None

    reports = db.load_layout(layout_id)
    assert reports is not None
    assert len(reports) == 1
    assert reports[0]["name"] == "Monthly Invoices"

    after = db.list_layouts()[0]["last_used_at"]
    assert after is not None  # last_used_at was updated


def test_delete_layout(db: DatabaseManager) -> None:
    """Deleting a layout removes it from the DB."""
    layout_id = db.save_layout("To Delete", SAMPLE_REPORTS)
    assert len(db.list_layouts()) == 1

    db.delete_layout(layout_id)

    assert db.list_layouts() == []


def test_load_nonexistent_layout_returns_none(db: DatabaseManager) -> None:
    """Loading a non-existent layout ID returns None."""
    result = db.load_layout("00000000-0000-0000-0000-000000000000")
    assert result is None


def test_list_layouts_ordered_by_last_used(db: DatabaseManager) -> None:
    """list_layouts places never-used layouts (NULL last_used_at) after used ones."""
    id_a = db.save_layout("Layout A", SAMPLE_REPORTS)
    id_b = db.save_layout("Layout B", SAMPLE_REPORTS)

    # Load A so it has a last_used_at; B remains NULL
    db.load_layout(id_a)

    layouts = db.list_layouts()
    ids_in_order = [lay["id"] for lay in layouts]

    # A was used, B was never used — A must appear before B (NULLS LAST ordering)
    assert ids_in_order.index(id_a) < ids_in_order.index(id_b)
