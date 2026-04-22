#!/usr/bin/env python3
"""Backfill amount_jpy / exchange_rate / sale profit in JPY."""

from __future__ import annotations

import argparse
import shutil
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from core.database.connection import get_session
from core.models import Transaction, TransactionType
from core.utils.currency import RateNotFoundError, get_exchange_rate
from sqlalchemy.orm import Session


def backfill_transactions(
    sess: Session,
    *,
    dry_run: bool,
    since: date | None,
    batch_size: int,
) -> dict:
    query = sess.query(Transaction).filter(Transaction.amount_jpy.is_(None))
    if since:
        query = query.filter(Transaction.date >= datetime.combine(since, datetime.min.time()))

    processed = 0
    updated = 0
    skipped = 0
    errors = 0

    rows = query.order_by(Transaction.id).all()
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        for txn in batch:
            processed += 1
            if not txn.date:
                skipped += 1
                continue
            try:
                rate_used, _actual = get_exchange_rate(
                    sess, txn.currency or "USD", "JPY", txn.date.date()
                )
            except RateNotFoundError:
                skipped += 1
                continue
            except Exception:
                errors += 1
                continue

            amount_jpy = Decimal(str(txn.amount)) * rate_used
            if not dry_run:
                txn.amount_jpy = float(amount_jpy)
                txn.exchange_rate = float(rate_used)
                if txn.type == TransactionType.SALE:
                    total_cost_jpy = Decimal(str(txn.total_cost)) if txn.total_cost is not None else Decimal("0")
                    profit_jpy = amount_jpy - total_cost_jpy
                    txn.profit = float(profit_jpy)
                    txn.margin = float(profit_jpy / amount_jpy) if amount_jpy != 0 else None
                updated += 1
            else:
                updated += 1
        if not dry_run:
            sess.commit()
    return {"processed": processed, "updated": updated, "skipped": skipped, "errors": errors}


def backup_db(db_path: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = Path("backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    dst = backup_dir / f"backfill-{ts}.db"
    shutil.copy2(db_path, dst)
    return dst


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--since", type=str, default=None)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--db", type=str, default="ebay.db")
    args = parser.parse_args()

    since = date.fromisoformat(args.since) if args.since else None
    dry_run = not args.apply
    if args.apply:
        backup = backup_db(args.db)
        print(f"Backing up {args.db} -> {backup}")
    sess = get_session()
    try:
        result = backfill_transactions(sess, dry_run=dry_run, since=since, batch_size=args.batch_size)
    finally:
        sess.close()
    if dry_run:
        print(f"[DRY RUN] Would update {result['updated']} transactions, skip {result['skipped']}, errors: {result['errors']}")
        print("Run with --apply to execute.")
    else:
        print(f"Backfill complete: processed: {result['processed']}, updated: {result['updated']}, skipped: {result['skipped']}, errors: {result['errors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
