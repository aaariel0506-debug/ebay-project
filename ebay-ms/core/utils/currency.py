"""Currency utilities backed only by DB exchange rates."""

from __future__ import annotations

import csv
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from core.models.exchange_rate import ExchangeRate
from sqlalchemy.orm import Session

_CCY_RE = re.compile(r"^[A-Z]{3}$")


class RateNotFoundError(Exception):
    """No usable exchange rate found for target date / pair."""


def get_exchange_rate(
    sess: Session,
    from_currency: str,
    to_currency: str,
    target_date: date,
    *,
    fallback_days: int = 7,
) -> tuple[Decimal, date]:
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    if from_currency == to_currency:
        return Decimal("1.0"), target_date

    exact = (
        sess.query(ExchangeRate)
        .filter(
            ExchangeRate.rate_date == target_date,
            ExchangeRate.from_currency == from_currency,
            ExchangeRate.to_currency == to_currency,
        )
        .first()
    )
    if exact:
        return Decimal(str(exact.rate)), exact.rate_date

    oldest = target_date - timedelta(days=fallback_days)
    fallback = (
        sess.query(ExchangeRate)
        .filter(
            ExchangeRate.rate_date < target_date,
            ExchangeRate.rate_date >= oldest,
            ExchangeRate.from_currency == from_currency,
            ExchangeRate.to_currency == to_currency,
        )
        .order_by(ExchangeRate.rate_date.desc())
        .first()
    )
    if fallback:
        return Decimal(str(fallback.rate)), fallback.rate_date

    raise RateNotFoundError(
        f"rate_not_found: {from_currency}->{to_currency} @ {target_date.isoformat()}"
    )


def convert(
    sess: Session,
    amount: Decimal,
    from_currency: str,
    to_currency: str,
    target_date: date,
    *,
    fallback_days: int = 7,
) -> tuple[Decimal, Decimal, date]:
    rate_used, actual_date_used = get_exchange_rate(
        sess,
        from_currency,
        to_currency,
        target_date,
        fallback_days=fallback_days,
    )
    return amount * rate_used, rate_used, actual_date_used


def import_rates_from_csv(
    sess: Session,
    csv_path: str,
    *,
    dry_run: bool = False,
) -> dict:
    rows_read = 0
    rows_valid = 0
    rows_invalid = 0
    created = 0
    updated = 0
    errors: list[dict] = []

    latest_by_key: dict[tuple[date, str, str], tuple[Decimal, int]] = {}
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=2):
            rows_read += 1
            try:
                rate_date = date.fromisoformat((row.get("rate_date") or "").strip())
            except Exception:
                rows_invalid += 1
                errors.append({"line": idx, "reason": f"Invalid date format: {row.get('rate_date')!r}"})
                continue
            raw_from_currency = (row.get("from_currency") or "").strip()
            raw_to_currency = (row.get("to_currency") or "").strip()
            if not _CCY_RE.match(raw_from_currency):
                rows_invalid += 1
                errors.append({"line": idx, "reason": f"Invalid currency code: {raw_from_currency!r}"})
                continue
            if not _CCY_RE.match(raw_to_currency):
                rows_invalid += 1
                errors.append({"line": idx, "reason": f"Invalid currency code: {raw_to_currency!r}"})
                continue
            from_currency = raw_from_currency
            to_currency = raw_to_currency
            try:
                rate = Decimal((row.get("rate") or "").strip())
            except (InvalidOperation, AttributeError):
                rows_invalid += 1
                errors.append({"line": idx, "reason": f"Invalid rate: {row.get('rate')!r}"})
                continue
            if rate <= 0:
                rows_invalid += 1
                errors.append({"line": idx, "reason": f"Invalid rate: {row.get('rate')!r}"})
                continue
            rows_valid += 1
            latest_by_key[(rate_date, from_currency, to_currency)] = (rate, idx)

    if dry_run:
        return {
            "rows_read": rows_read,
            "rows_valid": rows_valid,
            "rows_invalid": rows_invalid,
            "created": 0,
            "updated": 0,
            "errors": errors,
        }

    for (rate_date, from_currency, to_currency), (rate, _line) in latest_by_key.items():
        existing = (
            sess.query(ExchangeRate)
            .filter(
                ExchangeRate.rate_date == rate_date,
                ExchangeRate.from_currency == from_currency,
                ExchangeRate.to_currency == to_currency,
            )
            .first()
        )
        if existing:
            existing.rate = rate
            existing.source = "csv"
            updated += 1
        else:
            sess.add(
                ExchangeRate(
                    rate_date=rate_date,
                    from_currency=from_currency,
                    to_currency=to_currency,
                    rate=rate,
                    source="csv",
                )
            )
            created += 1
    sess.commit()
    return {
        "rows_read": rows_read,
        "rows_valid": rows_valid,
        "rows_invalid": rows_invalid,
        "created": created,
        "updated": updated,
        "errors": errors,
    }
