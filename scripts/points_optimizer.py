#!/usr/bin/env python3
"""אופטימיזציית הטבות/נקודות: איתור קטגוריות ששולמו בכרטיס בלי הטבה,
כשכרטיס אחר של המשתמש כן מציע הטבה טובה יותר באותה קטגוריה.

    python3 scripts/points_optimizer.py [--month YYYY-MM]

אם config/card_benefits.yaml ריק — הסקריפט יוצא בשקט (קוד 0, בלי פלט).

אזהרה: זו לא המלצה פיננסית מדויקת. סוגי הטבות שונים (נקודות מול מיילים
מול קאשבק) לא תמיד ניתנים להשוואה מספרית ישירה — זה כיוון לבדיקה ידנית.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from common import load_benefits, load_ledger, month_key
from render import money

MIN_GAIN = 5.0  # מתחת לזה לא שווה להזכיר


def rate_for(account_config: dict, category: str) -> tuple[float, str]:
    """אחוז ההטבה של חשבון בקטגוריה, ותיאור מילולי."""
    for benefit in account_config.get("benefits") or []:
        if str(benefit.get("category", "")).strip() == category:
            rate = float(benefit.get("rate", 0) or 0)
            return rate, str(benefit.get("note") or f"{rate:g}%")
    default = float(account_config.get("default_rate", 0) or 0)
    return default, f"בסיסי {default:g}%"


def main() -> int:
    parser = argparse.ArgumentParser(description="אופטימיזציית הטבות צבירה")
    parser.add_argument("--month", help="YYYY-MM (ברירת מחדל: החודש האחרון ביומן)")
    args = parser.parse_args()

    benefits = load_benefits()
    if not benefits:
        return 0  # לא הוגדרו הטבות — דילוג שקט, כפי שמוגדר ב-CLAUDE.md

    ledger = load_ledger()
    if ledger.empty:
        return 0

    ledger["amount"] = pd.to_numeric(ledger["amount"], errors="coerce").fillna(0.0)
    ledger["month"] = month_key(ledger["date"])
    ledger = ledger[ledger["month"].notna()]

    months = sorted(ledger["month"].unique())
    if not months:
        return 0
    month = args.month or months[-1]

    spend = ledger[(ledger["month"] == month) & (ledger["amount"] < 0)]
    if spend.empty:
        print(f"אין הוצאות בחודש {month}.")
        return 0

    grouped = spend.groupby(["category", "account"])["amount"].sum().abs().reset_index()

    suggestions = []
    for _, row in grouped.iterrows():
        category, account, amount = row["category"], row["account"], float(row["amount"])
        if account not in benefits:
            continue
        used_rate, used_note = rate_for(benefits[account], category)

        best_account, best_rate, best_note = account, used_rate, used_note
        for candidate, config in benefits.items():
            if candidate == account:
                continue
            rate, note = rate_for(config, category)
            if rate > best_rate:
                best_account, best_rate, best_note = candidate, rate, note

        if best_account == account:
            continue
        gain = amount * (best_rate - used_rate) / 100
        if gain < MIN_GAIN:
            continue
        suggestions.append(
            {
                "category": category,
                "amount": amount,
                "used": account,
                "used_note": used_note,
                "better": best_account,
                "better_note": best_note,
                "gain": gain,
            }
        )

    if not suggestions:
        print(f"[{month}] לא נמצאו הזדמנויות אופטימיזציה משמעותיות.")
        return 0

    suggestions.sort(key=lambda s: s["gain"], reverse=True)
    total = sum(s["gain"] for s in suggestions)

    print(f"[{month}] הצעות אופטימיזציית הטבות (כיוון לבדיקה ידנית, לא המלצה פיננסית):")
    for item in suggestions:
        display = (benefits[item["better"]].get("display_name") or item["better"])
        print(
            f"  • {item['category']}: {money(item['amount'])} דרך {item['used']} "
            f"({item['used_note']}) — ב-{display} ({item['better_note']}) "
            f"היה מניב ~{money(item['gain'])} יותר"
        )
    print(f"  סה\"כ פוטנציאל משוער החודש: ~{money(total)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
