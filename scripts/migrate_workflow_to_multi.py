"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           scripts/migrate_workflow_to_multi.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    One-shot migration: converts all documents that still carry the
                legacy ``semantic_data.workflow`` (singular) key to the current
                ``semantic_data.workflows`` (plural, keyed by rule_id) structure.

                Run once against the live database, then delete this script.

Usage:
    python scripts/migrate_workflow_to_multi.py --db /path/to/kpaperflux.db

                Use --dry-run to preview changes without writing to the DB.
------------------------------------------------------------------------------
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


def _migrate(db_path: str, dry_run: bool) -> None:
    if not Path(db_path).exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT uuid, semantic_data FROM virtual_documents "
        "WHERE json_extract(semantic_data, '$.workflow') IS NOT NULL"
    )
    rows = cursor.fetchall()
    print(f"Found {len(rows)} document(s) with legacy 'workflow' structure.")

    migrated = 0
    skipped = 0
    for row in rows:
        uuid = row["uuid"]
        try:
            sd: dict[str, Any] = json.loads(row["semantic_data"])
        except (json.JSONDecodeError, TypeError):
            print(f"  SKIP {uuid}: cannot parse semantic_data JSON")
            skipped += 1
            continue

        old_wf: dict[str, Any] | None = sd.get("workflow")
        if not isinstance(old_wf, dict):
            skipped += 1
            continue

        rule_id: str = old_wf.get("rule_id", "")
        if not rule_id:
            print(f"  SKIP {uuid}: legacy 'workflow' has no rule_id")
            skipped += 1
            continue

        # Build plural workflows dict, preserving all fields of the old entry
        workflows: dict[str, Any] = sd.get("workflows", {})
        if rule_id in workflows:
            print(f"  SKIP {uuid}: rule '{rule_id}' already present in 'workflows'")
            skipped += 1
            continue

        workflows[rule_id] = old_wf
        sd["workflows"] = workflows
        del sd["workflow"]

        if dry_run:
            print(f"  DRY-RUN {uuid}: would migrate rule '{rule_id}' "
                  f"(current_step={old_wf.get('current_step', '?')})")
        else:
            cursor.execute(
                "UPDATE virtual_documents SET semantic_data = ? WHERE uuid = ?",
                (json.dumps(sd, ensure_ascii=False), uuid),
            )
            print(f"  OK {uuid}: migrated rule '{rule_id}' "
                  f"(current_step={old_wf.get('current_step', '?')})")
        migrated += 1

    if not dry_run:
        conn.commit()
    conn.close()

    print(f"\nDone. migrated={migrated}, skipped={skipped}"
          + (" (dry-run, no changes written)" if dry_run else ""))
    if not dry_run and migrated:
        print("Now delete this script — it is no longer needed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate KPaperFlux DB from singular 'workflow' to plural 'workflows'."
    )
    parser.add_argument("--db", required=True, help="Path to kpaperflux.db")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would change without modifying the database"
    )
    args = parser.parse_args()
    _migrate(args.db, args.dry_run)


if __name__ == "__main__":
    main()
