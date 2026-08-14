"""עזרים משותפים לכל סקריפטי הפרויקט."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
INBOX_DIR = ROOT / "inbox"
LEDGER = DATA_DIR / "transactions.csv"

SCHEMA = [
    "date",
    "source",
    "account",
    "description",
    "amount",
    "currency",
    "category",
    "raw_hash",
]

UNCLASSIFIED = "לא מסווג"
FALLBACK_CATEGORY = "אחר"
INCOME_CATEGORY = "הכנסה"

# מעל הסכום הזה, תנועה שלא זוהתה נשארת "לא מסווג" כדי ש-Claude Code ישאל עליה.
ASK_THRESHOLD = 300.0


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_parsers() -> dict:
    return load_yaml(CONFIG_DIR / "parsers.yaml")


def load_categories() -> dict:
    raw = load_yaml(CONFIG_DIR / "categories.yaml")
    return {name: [str(k) for k in (kws or [])] for name, kws in raw.items()}


def load_benefits() -> dict:
    return (load_yaml(CONFIG_DIR / "card_benefits.yaml") or {}).get("accounts") or {}


# --- פענוח סכומים ---------------------------------------------------------

_MONEY_STRIP = re.compile(r"[^\d,.\-()]")


def parse_money(value) -> float:
    """הופך '1,234.50 ₪' / '(45.00)' / '‏-12.3' למספר. ריק -> 0.0"""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return 0.0 if pd.isna(value) else float(value)

    text = str(value).strip()
    if not text or text in {"-", "--"}:
        return 0.0

    # תווי כיווניות RTL שמגיעים מאקספורטים ישראליים
    text = text.replace("‏", "").replace("‎", "").replace(" ", " ")
    negative = "(" in text and ")" in text

    text = _MONEY_STRIP.sub("", text).replace("(", "").replace(")", "")
    if not text or text == "-":
        return 0.0

    # 1,234.50 -> 1234.50   |   1.234,50 -> 1234.50
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        decimals = len(text.split(",")[-1])
        text = text.replace(",", "." if decimals == 2 else "")

    try:
        amount = float(text)
    except ValueError:
        return 0.0
    return -amount if negative else amount


def parse_date(value, date_format: str | None):
    if date_format:
        parsed = pd.to_datetime(value, format=date_format, errors="coerce")
    else:
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return parsed


# --- סיווג ----------------------------------------------------------------


def categorize(description: str, amount: float, categories: dict) -> str:
    """התאמת substring לא תלוית רישיות. מחזיר קטגוריה או UNCLASSIFIED/אחר."""
    text = (description or "").strip().lower()

    best_category, best_len = None, 0
    for name, keywords in categories.items():
        for keyword in keywords:
            k = keyword.strip().lower()
            # מילת מפתח ארוכה יותר = התאמה ספציפית יותר, מנצחת
            if k and k in text and len(k) > best_len:
                best_category, best_len = name, len(k)

    if best_category:
        return best_category
    if amount > 0:
        return INCOME_CATEGORY
    return UNCLASSIFIED if abs(amount) > ASK_THRESHOLD else FALLBACK_CATEGORY


def row_hash(date: str, description: str, amount: float, source: str) -> str:
    key = f"{date}|{(description or '').strip()}|{amount:.2f}|{source}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


# --- היומן המרכזי ---------------------------------------------------------


def load_ledger() -> pd.DataFrame:
    if not LEDGER.exists():
        return pd.DataFrame(columns=SCHEMA)
    df = pd.read_csv(LEDGER, dtype={"raw_hash": str})
    for column in SCHEMA:
        if column not in df.columns:
            df[column] = None
    return df[SCHEMA]


def save_ledger(df: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = df.sort_values(["date", "source", "description"], kind="stable")
    df[SCHEMA].to_csv(LEDGER, index=False, encoding="utf-8")


def month_key(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m")


def fmt_ils(amount: float) -> str:
    return f"{amount:,.0f} ₪"
