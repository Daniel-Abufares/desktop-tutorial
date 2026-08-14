"""שכבת רינדור HTML משותפת לדשבורד החודשי ולדוח השנתי.

כל פלט הוא קובץ HTML עצמאי — בלי CDN, בלי פונטים חיצוניים, בלי שרת.
נפתח ישירות בדפדפן (RTL), ותומך במצב כהה לפי העדפת המערכת.
"""

from __future__ import annotations

import html

# פלטה מאומתת: הצבע נושא גודל (magnitude), לכן גוון אחד בסקלה בהירה→כהה.
# הצבעים לסטטוס שמורים לחריגות בלבד ותמיד מלווים באייקון + תווית.
CSS = """
:root {
  color-scheme: light;
  --surface:      #fcfcfb;
  --plane:        #f9f9f7;
  --ink:          #0b0b0b;
  --ink-2:        #52514e;
  --muted:        #898781;
  --grid:         #e1e0d9;
  --axis:         #c3c2b7;
  --bar:          #2a78d6;
  --bar-soft:     #9ec5f4;
  --series-1:     #2a78d6;
  --series-2:     #eb6834;
  --income:       #1baf7a;
  --good:         #0ca30c;
  --warning:      #fab219;
  --critical:     #d03b3b;
  --ring:         rgba(11,11,11,0.10);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface:  #1a1a19;
    --plane:    #0d0d0d;
    --ink:      #ffffff;
    --ink-2:    #c3c2b7;
    --muted:    #898781;
    --grid:     #2c2c2a;
    --axis:     #383835;
    --bar:      #3987e5;
    --bar-soft: #1c5cab;
    --series-1: #3987e5;
    --series-2: #d95926;
    --income:   #199e70;
    --ring:     rgba(255,255,255,0.10);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 32px 20px 64px;
  background: var(--plane);
  color: var(--ink);
  font-family: system-ui, -apple-system, "Segoe UI", "Noto Sans Hebrew", sans-serif;
  font-size: 15px;
  line-height: 1.5;
  direction: rtl;
}
.wrap { max-width: 980px; margin: 0 auto; }
h1 { font-size: 26px; margin: 0 0 4px; letter-spacing: -0.01em; }
h2 { font-size: 17px; margin: 0 0 16px; font-weight: 600; }
.sub { color: var(--ink-2); margin: 0 0 28px; font-size: 14px; }
.card {
  background: var(--surface);
  border: 1px solid var(--ring);
  border-radius: 12px;
  padding: 20px 22px;
  margin-bottom: 20px;
}
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 22px; }
.tile { background: var(--surface); border: 1px solid var(--ring); border-radius: 12px; padding: 16px 18px; }
.tile .label { color: var(--ink-2); font-size: 13px; margin-bottom: 6px; }
.tile .value { font-size: 27px; font-weight: 650; letter-spacing: -0.02em; }
.tile .note { color: var(--muted); font-size: 12px; margin-top: 4px; }
.pos { color: var(--good); }
.neg { color: var(--critical); }

.rows { display: flex; flex-direction: column; gap: 2px; }
.row { display: grid; grid-template-columns: 150px 1fr 108px; align-items: center; gap: 12px; padding: 3px 0; }
.row .name { color: var(--ink-2); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.track { background: var(--grid); border-radius: 4px; height: 15px; position: relative; overflow: hidden; }
.fill { height: 100%; background: var(--bar); border-radius: 4px; min-width: 2px; }
.fill.income { background: var(--income); }
.row .val { text-align: left; font-size: 13px; font-variant-numeric: tabular-nums; color: var(--ink); }
.row:hover .name, .row:hover .val { color: var(--ink); font-weight: 600; }

table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: right; color: var(--muted); font-weight: 600; padding: 7px 8px; border-bottom: 1px solid var(--axis); font-size: 12px; }
td { padding: 7px 8px; border-bottom: 1px solid var(--grid); font-variant-numeric: tabular-nums; }
td.num { text-align: left; }
tr:hover td { background: var(--plane); }
.flag { display: inline-flex; align-items: center; gap: 5px; font-weight: 600; }
.flag.up { color: var(--critical); }
.flag.down { color: var(--good); }
.empty { color: var(--muted); font-size: 14px; }

/* מגמה חודשית: שתי סדרות על ציר אחד (₪), מקרא + תוויות ישירות */
.legend { display: flex; gap: 18px; margin-bottom: 14px; font-size: 13px; color: var(--ink-2); }
.legend span { display: inline-flex; align-items: center; gap: 7px; }
.swatch { width: 11px; height: 11px; border-radius: 3px; }
.s1 { background: var(--series-1); }
.s2 { background: var(--series-2); }
.trend { display: flex; flex-direction: column; gap: 10px; }
.trend .m { display: grid; grid-template-columns: 68px 1fr; align-items: center; gap: 12px; }
.trend .mn { color: var(--ink-2); font-size: 12px; font-variant-numeric: tabular-nums; }
.pair { display: flex; flex-direction: column; gap: 2px; }
.pair .b { display: flex; align-items: center; gap: 8px; }
.pair .seg { height: 12px; border-radius: 4px; min-width: 2px; }
.pair .lab { font-size: 11px; color: var(--ink-2); font-variant-numeric: tabular-nums; white-space: nowrap; }
.trend .m:hover .lab { color: var(--ink); font-weight: 600; }
footer { color: var(--muted); font-size: 12px; text-align: center; margin-top: 34px; }
"""


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""))


def money(amount: float) -> str:
    return f"{amount:,.0f} ₪"


def page(title: str, body: str) -> str:
    return (
        '<!doctype html>\n<html lang="he" dir="rtl">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n<style>{CSS}</style>\n</head>\n"
        f'<body>\n<div class="wrap">\n{body}\n'
        "<footer>נוצר אוטומטית — מעקב פיננסי Claude Code</footer>\n"
        "</div>\n</body>\n</html>\n"
    )


def tiles(items: list[tuple[str, str, str, str]]) -> str:
    """items: (label, value, css_class, note)"""
    cells = "".join(
        f'<div class="tile"><div class="label">{esc(label)}</div>'
        f'<div class="value {cls}">{esc(value)}</div>'
        + (f'<div class="note">{esc(note)}</div>' if note else "")
        + "</div>"
        for label, value, cls, note in items
    )
    return f'<div class="tiles">{cells}</div>'


def bars(rows: list[tuple[str, float]], income: bool = False) -> str:
    """תרשים עמודות אופקי, סדרה אחת (גודל) — לכן בלי מקרא, עם תווית ישירה לכל עמודה."""
    if not rows:
        return '<p class="empty">אין נתונים להצגה.</p>'
    peak = max(abs(v) for _, v in rows) or 1.0
    cls = " income" if income else ""
    out = []
    for name, value in rows:
        pct = abs(value) / peak * 100
        out.append(
            f'<div class="row" title="{esc(name)}: {money(abs(value))}">'
            f'<div class="name">{esc(name)}</div>'
            f'<div class="track"><div class="fill{cls}" style="width:{pct:.2f}%"></div></div>'
            f'<div class="val">{money(abs(value))}</div></div>'
        )
    return '<div class="rows">' + "".join(out) + "</div>"


def trend(months: list[tuple[str, float, float]]) -> str:
    """מגמה חודשית: הכנסות מול הוצאות, שתי סדרות על ציר ₪ אחד (לעולם לא שני צירים)."""
    if not months:
        return '<p class="empty">אין נתונים להצגה.</p>'
    peak = max(max(inc, exp) for _, inc, exp in months) or 1.0
    out = [
        '<div class="legend">'
        '<span><i class="swatch s1"></i>הכנסות</span>'
        '<span><i class="swatch s2"></i>הוצאות</span>'
        "</div>",
        '<div class="trend">',
    ]
    for label, income_v, expense_v in months:
        out.append(
            f'<div class="m"><div class="mn">{esc(label)}</div><div class="pair">'
            f'<div class="b"><div class="seg s1" style="width:{income_v / peak * 100:.2f}%"></div>'
            f'<div class="lab">{money(income_v)}</div></div>'
            f'<div class="b"><div class="seg s2" style="width:{expense_v / peak * 100:.2f}%"></div>'
            f'<div class="lab">{money(expense_v)}</div></div>'
            "</div></div>"
        )
    out.append("</div>")
    return "".join(out)


def table(headers: list[str], rows: list[list[str]], numeric_from: int = 1) -> str:
    if not rows:
        return '<p class="empty">אין נתונים להצגה.</p>'
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = ""
    for row in rows:
        cells = "".join(
            f'<td class="{"num" if i >= numeric_from else ""}">{cell}</td>'
            for i, cell in enumerate(row)
        )
        body += f"<tr>{cells}</tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def card(title: str, content: str) -> str:
    return f'<section class="card"><h2>{esc(title)}</h2>{content}</section>'
