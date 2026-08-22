"""שכבת רינדור HTML משותפת לדשבורד החודשי ולדוח השנתי.

כל פלט הוא קובץ HTML עצמאי — בלי CDN, בלי פונטים חיצוניים, בלי שרת.
נפתח ישירות בדפדפן (RTL), עם מצב כהה, ניווט בין חודשים, וטבלאות
שניתן לחפש ולמיין בהן.

הפלטה מאומתת מול בדיקות נגישות: הצבע נושא גודל (magnitude), ולכן
גוון אחד בסקלה. צבעי סטטוס שמורים לחריגות בלבד ותמיד מלווים
באייקון + תווית, לעולם לא בצבע לבד.
"""

from __future__ import annotations

import html
import re

_SORT_KEY = re.compile(r'data-sort="([^"]*)"')

CSS = """
:root {
  color-scheme: light;
  --surface:   #fcfcfb;
  --plane:     #f4f4f1;
  --raised:    #ffffff;
  --ink:       #0b0b0b;
  --ink-2:     #52514e;
  --muted:     #898781;
  --grid:      #e6e5df;
  --axis:      #c3c2b7;
  --series-1:  #2a78d6;
  --series-2:  #eb6834;
  --income:    #1baf7a;
  --good:      #0ca30c;
  --critical:  #d03b3b;
  --ring:      rgba(11,11,11,0.09);
  --shadow:    0 1px 2px rgba(11,11,11,0.04), 0 4px 16px rgba(11,11,11,0.05);
}
:root[data-theme="dark"], :root:not([data-theme="light"]) {
  --dark-surface: #1a1a19;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface:  #1a1a19;
    --plane:    #0d0d0d;
    --raised:   #212120;
    --ink:      #ffffff;
    --ink-2:    #c3c2b7;
    --muted:    #898781;
    --grid:     #2c2c2a;
    --axis:     #383835;
    --series-1: #3987e5;
    --series-2: #d95926;
    --income:   #199e70;
    --ring:     rgba(255,255,255,0.10);
    --shadow:   0 1px 2px rgba(0,0,0,0.4), 0 4px 16px rgba(0,0,0,0.3);
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface:  #1a1a19;
  --plane:    #0d0d0d;
  --raised:   #212120;
  --ink:      #ffffff;
  --ink-2:    #c3c2b7;
  --muted:    #898781;
  --grid:     #2c2c2a;
  --axis:     #383835;
  --series-1: #3987e5;
  --series-2: #d95926;
  --income:   #199e70;
  --ring:     rgba(255,255,255,0.10);
  --shadow:   0 1px 2px rgba(0,0,0,0.4), 0 4px 16px rgba(0,0,0,0.3);
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--plane);
  color: var(--ink);
  font-family: system-ui, -apple-system, "Segoe UI", "Noto Sans Hebrew", "Arial Hebrew", sans-serif;
  font-size: 15px;
  line-height: 1.55;
  direction: rtl;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1060px; margin: 0 auto; padding: 0 20px 72px; }

/* ---------- סרגל עליון ---------- */
.topbar {
  position: sticky; top: 0; z-index: 20;
  background: color-mix(in srgb, var(--plane) 88%, transparent);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--ring);
  margin-bottom: 28px;
}
.topbar .inner {
  max-width: 1060px; margin: 0 auto; padding: 11px 20px;
  display: flex; align-items: center; gap: 12px; flex-wrap: nowrap;
}
.brand { font-weight: 640; font-size: 14px; letter-spacing: -0.01em; white-space: nowrap; }
.brand .dot {
  display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  background: var(--series-1); margin-left: 7px; vertical-align: middle;
}
.spacer { flex: 1; }
/* הניווט גולל אופקית במקום לעטוף — אחרת הוא דוחף את כפתור התצוגה לשורה נפרדת */
.nav {
  display: flex; gap: 3px; align-items: center; flex-wrap: nowrap;
  overflow-x: auto; scrollbar-width: none; min-width: 0;
}
.nav::-webkit-scrollbar { display: none; }
.nav a {
  color: var(--ink-2); text-decoration: none; font-size: 12.5px; white-space: nowrap;
  padding: 4px 9px; border-radius: 7px; font-variant-numeric: tabular-nums;
  transition: background .12s, color .12s;
}
.nav a:hover { background: var(--grid); color: var(--ink); }
.nav a.on { background: var(--series-1); color: #fff; font-weight: 600; }
.nav .sep { width: 1px; height: 16px; background: var(--axis); margin: 0 5px; flex: none; }
.iconbtn {
  border: 1px solid var(--ring); background: var(--raised); color: var(--ink-2);
  width: 30px; height: 30px; border-radius: 8px; cursor: pointer; flex: none;
  font-size: 14px; line-height: 1; display: grid; place-items: center;
}
.iconbtn:hover { color: var(--ink); border-color: var(--axis); }

/* ---------- כותרת ---------- */
.head { margin: 4px 0 24px; }
h1 { font-size: 30px; margin: 0 0 5px; letter-spacing: -0.025em; font-weight: 680; }
.sub { color: var(--ink-2); margin: 0; font-size: 14px; }

/* ---------- אריחי מדדים ---------- */
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin-bottom: 22px; }
.tile {
  background: var(--raised); border: 1px solid var(--ring);
  border-radius: 14px; padding: 16px 18px; box-shadow: var(--shadow);
  position: relative; overflow: hidden;
}
.tile::before {
  content: ""; position: absolute; inset-inline-start: 0; top: 0; bottom: 0;
  width: 3px; background: var(--accent, transparent);
}
.tile .label { color: var(--ink-2); font-size: 12.5px; font-weight: 550; margin-bottom: 5px; }
.tile .value { font-size: 28px; font-weight: 660; letter-spacing: -0.03em; line-height: 1.15; }
.tile .note { color: var(--muted); font-size: 12px; margin-top: 5px; }
.pos { color: var(--good); }
.neg { color: var(--critical); }

/* ---------- כרטיס ---------- */
.card {
  background: var(--raised); border: 1px solid var(--ring);
  border-radius: 14px; padding: 20px 22px; margin-bottom: 18px;
  box-shadow: var(--shadow);
}
.card > header {
  display: flex; align-items: center; gap: 12px; margin-bottom: 16px;
}
h2 { font-size: 16px; margin: 0; font-weight: 620; letter-spacing: -0.01em; }
.toggle {
  border: 1px solid var(--ring); background: transparent; color: var(--ink-2);
  border-radius: 7px; padding: 3px 10px; font-size: 12px; cursor: pointer;
  font-family: inherit;
}
.toggle:hover { color: var(--ink); border-color: var(--axis); }
.hidden { display: none !important; }

/* ---------- עמודות אופקיות ---------- */
.rows { display: flex; flex-direction: column; gap: 2px; }
.row {
  display: grid; grid-template-columns: 158px 1fr 96px 52px;
  align-items: center; gap: 12px; padding: 4px 6px;
  border-radius: 7px; cursor: default;
}
.row:hover { background: var(--plane); }
.row .name {
  color: var(--ink-2); font-size: 13px; font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.row:hover .name { color: var(--ink); }
.track { background: var(--grid); border-radius: 4px; height: 14px; overflow: hidden; }
.fill {
  height: 100%; background: var(--series-1); border-radius: 4px; min-width: 2px;
  transition: filter .12s;
}
.fill.income { background: var(--income); }
.row:hover .fill { filter: brightness(1.08); }
.row .val { text-align: left; font-size: 13px; font-variant-numeric: tabular-nums; font-weight: 550; }
.row .pct { text-align: left; font-size: 11.5px; color: var(--muted); font-variant-numeric: tabular-nums; }

/* ---------- מגמה חודשית ---------- */
.legend { display: flex; gap: 18px; margin-bottom: 14px; font-size: 12.5px; color: var(--ink-2); }
.legend span { display: inline-flex; align-items: center; gap: 7px; }
.swatch { width: 11px; height: 11px; border-radius: 3px; }
.s1 { background: var(--series-1); }
.s2 { background: var(--series-2); }
.trend { display: flex; flex-direction: column; gap: 9px; }
.trend .m {
  display: grid; grid-template-columns: 66px 1fr; align-items: center; gap: 12px;
  padding: 3px 6px; border-radius: 7px;
}
.trend .m:hover { background: var(--plane); }
.trend .mn { color: var(--ink-2); font-size: 12px; font-variant-numeric: tabular-nums; }
.pair { display: flex; flex-direction: column; gap: 2px; }
.pair .b { display: flex; align-items: center; gap: 8px; }
.pair .seg { height: 11px; border-radius: 4px; min-width: 2px; }
.pair .lab { font-size: 11px; color: var(--ink-2); font-variant-numeric: tabular-nums; white-space: nowrap; }
.trend .m:hover .lab { color: var(--ink); font-weight: 600; }

/* ---------- טבלאות ---------- */
.tablewrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
  text-align: right; color: var(--muted); font-weight: 600;
  padding: 8px; border-bottom: 1px solid var(--axis); font-size: 11.5px;
  letter-spacing: .02em; white-space: nowrap;
}
th.sortable { cursor: pointer; user-select: none; }
th.sortable:hover { color: var(--ink); }
th .arw { opacity: .35; font-size: 9px; }
th.asc .arw, th.desc .arw { opacity: 1; color: var(--series-1); }
td { padding: 8px; border-bottom: 1px solid var(--grid); font-variant-numeric: tabular-nums; }
td.num { text-align: left; }
tbody tr:hover td { background: var(--plane); }
tbody tr:last-child td { border-bottom: none; }
.flag { display: inline-flex; align-items: center; gap: 5px; font-weight: 600; white-space: nowrap; }
.flag.up { color: var(--critical); }
.flag.down { color: var(--good); }
.chip {
  display: inline-block; padding: 1px 8px; border-radius: 20px;
  background: var(--grid); color: var(--ink-2); font-size: 11.5px; font-weight: 550;
}
.search {
  border: 1px solid var(--ring); background: var(--surface); color: var(--ink);
  border-radius: 8px; padding: 5px 11px; font-size: 12.5px; font-family: inherit;
  width: 190px; direction: rtl;
}
.search:focus { outline: 2px solid var(--series-1); outline-offset: -1px; border-color: transparent; }
.count { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.empty { color: var(--muted); font-size: 14px; padding: 6px 0; }
/* סכומים מבודדים ל-LTR: בלי זה סימן המינוס נדחף לצד הלא נכון בהקשר RTL
   ו-"‎-5,200 ₪" מוצג כ-"5,200- ₪". */
.mny { direction: ltr; unicode-bidi: isolate; display: inline-block; }
footer { color: var(--muted); font-size: 12px; text-align: center; margin-top: 36px; }
@media (max-width: 620px) {
  .row { grid-template-columns: 108px 1fr 82px; }
  .row .pct { display: none; }
  h1 { font-size: 24px; }
}
@media print {
  .topbar, .toggle, .search, .iconbtn { display: none !important; }
  .card { break-inside: avoid; box-shadow: none; }
}
"""

JS = """
(function () {
  var root = document.documentElement;
  var saved = null;
  try { saved = localStorage.getItem('fin-theme'); } catch (e) {}
  if (saved) root.setAttribute('data-theme', saved);

  var btn = document.getElementById('theme');
  if (btn) btn.addEventListener('click', function () {
    var dark = getComputedStyle(root).colorScheme === 'dark';
    var next = dark ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('fin-theme', next); } catch (e) {}
  });

  // מעבר בין תרשים לטבלה בכל כרטיס
  document.querySelectorAll('[data-toggle]').forEach(function (b) {
    b.addEventListener('click', function () {
      var card = b.closest('.card');
      var chart = card.querySelector('[data-view="chart"]');
      var tbl = card.querySelector('[data-view="table"]');
      var showTable = chart.classList.toggle('hidden');
      tbl.classList.toggle('hidden', !showTable);
      b.textContent = showTable ? 'תרשים' : 'טבלה';
    });
  });

  // חיפוש בטבלת התנועות
  document.querySelectorAll('[data-search]').forEach(function (input) {
    var table = document.getElementById(input.getAttribute('data-search'));
    var out = document.getElementById(input.getAttribute('data-count'));
    input.addEventListener('input', function () {
      var q = input.value.trim().toLowerCase();
      var shown = 0;
      table.querySelectorAll('tbody tr').forEach(function (tr) {
        var hit = !q || tr.textContent.toLowerCase().indexOf(q) !== -1;
        tr.classList.toggle('hidden', !hit);
        if (hit) shown++;
      });
      if (out) out.textContent = shown + ' תנועות';
    });
  });

  // מיון עמודות
  document.querySelectorAll('th.sortable').forEach(function (th) {
    th.addEventListener('click', function () {
      var table = th.closest('table');
      var idx = Array.prototype.indexOf.call(th.parentNode.children, th);
      var asc = !th.classList.contains('asc');
      table.querySelectorAll('th').forEach(function (o) { o.classList.remove('asc', 'desc'); });
      th.classList.add(asc ? 'asc' : 'desc');
      var body = table.querySelector('tbody');
      var rows = Array.prototype.slice.call(body.querySelectorAll('tr'));
      rows.sort(function (a, b) {
        var x = a.children[idx], y = b.children[idx];
        var xv = x.getAttribute('data-sort'), yv = y.getAttribute('data-sort');
        if (xv !== null && yv !== null) {
          var nx = parseFloat(xv), ny = parseFloat(yv);
          if (!isNaN(nx) && !isNaN(ny)) return asc ? nx - ny : ny - nx;
          return asc ? String(xv).localeCompare(String(yv), 'he')
                     : String(yv).localeCompare(String(xv), 'he');
        }
        return asc ? x.textContent.localeCompare(y.textContent, 'he')
                   : y.textContent.localeCompare(x.textContent, 'he');
      });
      rows.forEach(function (r) { body.appendChild(r); });
    });
  });
})();
"""


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""))


def money(amount: float) -> str:
    """טקסט רגיל — לשימוש ב-summary.md ובפלט הטרמינל."""
    return f"{amount:,.0f} ₪"


def money_html(amount: float, sort_key: bool = False) -> str:
    """סכום ל-HTML, מבודד ל-LTR כדי שסימן המינוס יישאר בצד הנכון."""
    attr = f' data-sort="{amount:.2f}"' if sort_key else ""
    return f'<span class="mny"{attr}>{money(amount)}</span>'


# --- שלד העמוד ------------------------------------------------------------


def topbar(nav_links: list[tuple[str, str, bool]] | None = None) -> str:
    """nav_links: (תווית, href, האם פעיל)"""
    items = ""
    if nav_links:
        for label, href, active in nav_links:
            if label == "|":
                items += '<span class="sep"></span>'
                continue
            cls = ' class="on"' if active else ""
            items += f'<a href="{esc(href)}"{cls}>{esc(label)}</a>'
    return (
        '<div class="topbar"><div class="inner">'
        '<div class="brand"><span class="dot"></span>מעקב פיננסי</div>'
        f'<nav class="nav">{items}</nav>'
        '<div class="spacer"></div>'
        '<button class="iconbtn" id="theme" title="מצב בהיר/כהה" '
        'aria-label="החלף מצב תצוגה">◐</button>'
        "</div></div>"
    )


def page(title: str, body: str, nav_links: list[tuple[str, str, bool]] | None = None) -> str:
    return (
        '<!doctype html>\n<html lang="he" dir="rtl">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
        f"{topbar(nav_links)}\n"
        f'<div class="wrap">\n{body}\n'
        "<footer>נוצר אוטומטית — מעקב פיננסי Claude Code</footer>\n</div>\n"
        f"<script>{JS}</script>\n</body>\n</html>\n"
    )


def head(title: str, subtitle: str) -> str:
    return f'<div class="head"><h1>{esc(title)}</h1><p class="sub">{esc(subtitle)}</p></div>'


# --- רכיבים ---------------------------------------------------------------


def tiles(items: list[dict]) -> str:
    """items: {label, amount, cls, note, accent} — amount מרונדר כ-HTML מבודד LTR."""
    cells = ""
    for item in items:
        accent = item.get("accent")
        style = f' style="--accent:{accent}"' if accent else ""
        note = item.get("note")
        cells += (
            f'<div class="tile"{style}>'
            f'<div class="label">{esc(item["label"])}</div>'
            f'<div class="value {item.get("cls", "")}">{money_html(item["amount"])}</div>'
            + (f'<div class="note">{note}</div>' if note else "")
            + "</div>"
        )
    return f'<div class="tiles">{cells}</div>'


def card(title: str, content: str, actions: str = "") -> str:
    return (
        f'<section class="card"><header><h2>{esc(title)}</h2>'
        f'<div class="spacer"></div>{actions}</header>{content}</section>'
    )


def bars(rows: list[tuple[str, float]], income: bool = False) -> str:
    """סדרה אחת (גודל) — בלי מקרא, עם תווית ישירה ואחוז מהסך לכל עמודה."""
    if not rows:
        return '<p class="empty">אין נתונים להצגה.</p>'
    peak = max(abs(v) for _, v in rows) or 1.0
    total = sum(abs(v) for _, v in rows) or 1.0
    cls = " income" if income else ""
    out = []
    for name, value in rows:
        magnitude = abs(value)
        share = magnitude / total * 100
        out.append(
            f'<div class="row" title="{esc(name)} — {money(magnitude)} ({share:.1f}% מהסך)">'
            f'<div class="name">{esc(name)}</div>'
            f'<div class="track"><div class="fill{cls}" '
            f'style="width:{magnitude / peak * 100:.2f}%"></div></div>'
            f'<div class="val">{money_html(magnitude)}</div>'
            f'<div class="pct">{share:.0f}%</div></div>'
        )
    return '<div class="rows">' + "".join(out) + "</div>"


def chart_card(title: str, rows: list[tuple[str, float]], unit: str = "סכום") -> str:
    """כרטיס תרשים עם מעבר לטבלה — תצוגת הטבלה היא דרישת נגישות, לא תוספת."""
    if not rows:
        return card(title, '<p class="empty">אין נתונים להצגה.</p>')
    total = sum(abs(v) for _, v in rows) or 1.0
    table_rows = [
        [
            esc(name),
            money_html(abs(value), sort_key=True),
            f"{abs(value) / total * 100:.1f}%",
        ]
        for name, value in rows
    ]
    body = (
        f'<div data-view="chart">{bars(rows)}</div>'
        f'<div data-view="table" class="hidden">'
        f'{table(["שם", unit, "אחוז"], table_rows)}</div>'
    )
    return card(title, body, '<button class="toggle" data-toggle>טבלה</button>')


def trend(months: list[tuple[str, float, float]]) -> str:
    """מגמה חודשית: הכנסות מול הוצאות, שתי סדרות על ציר ₪ אחד (לעולם לא שני צירים)."""
    if not months:
        return '<p class="empty">אין נתונים להצגה.</p>'
    peak = max(max(inc, exp) for _, inc, exp in months) or 1.0
    out = [
        '<div class="legend">'
        '<span><i class="swatch s1"></i>הכנסות</span>'
        '<span><i class="swatch s2"></i>הוצאות</span></div>',
        '<div class="trend">',
    ]
    for label, income_v, expense_v in months:
        net = income_v - expense_v
        out.append(
            f'<div class="m" title="{esc(label)} — נטו {money(net)}">'
            f'<div class="mn">{esc(label)}</div><div class="pair">'
            f'<div class="b"><div class="seg s1" style="width:{income_v / peak * 100:.2f}%"></div>'
            f'<div class="lab">{money_html(income_v)}</div></div>'
            f'<div class="b"><div class="seg s2" style="width:{expense_v / peak * 100:.2f}%"></div>'
            f'<div class="lab">{money_html(expense_v)}</div></div>'
            "</div></div>"
        )
    out.append("</div>")
    return "".join(out)


def table(
    headers: list[str],
    rows: list[list[str]],
    numeric_from: int = 1,
    table_id: str = "",
    sortable: bool = False,
) -> str:
    if not rows:
        return '<p class="empty">אין נתונים להצגה.</p>'
    head_cells = ""
    for i, header in enumerate(headers):
        cls = "sortable" if sortable else ""
        arrow = ' <span class="arw">▲▼</span>' if sortable else ""
        head_cells += f'<th class="{cls}">{esc(header)}{arrow}</th>'
    body = ""
    for row in rows:
        cells = ""
        for i, cell in enumerate(row):
            # מפתח המיון חייב לשבת על ה-<td> עצמו — הסקריפט קורא אותו משם,
            # ובלי זה מיון מספרי היה נופל בשקט להשוואת מחרוזות.
            match = _SORT_KEY.search(cell)
            sort_attr = f' data-sort="{match.group(1)}"' if match else ""
            cells += (
                f'<td class="{"num" if i >= numeric_from else ""}"{sort_attr}>{cell}</td>'
            )
        body += f"<tr>{cells}</tr>"
    ident = f' id="{esc(table_id)}"' if table_id else ""
    return (
        f'<div class="tablewrap"><table{ident}>'
        f"<thead><tr>{head_cells}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def searchable_table(
    title: str,
    headers: list[str],
    rows: list[list[str]],
    table_id: str,
    numeric_from: int = 1,
) -> str:
    actions = (
        f'<span class="count" id="{esc(table_id)}-count">{len(rows)} תנועות</span>'
        f'<input class="search" type="search" placeholder="חיפוש…" '
        f'data-search="{esc(table_id)}" data-count="{esc(table_id)}-count" '
        f'aria-label="חיפוש בטבלה">'
    )
    return card(
        title,
        table(headers, rows, numeric_from=numeric_from, table_id=table_id, sortable=True),
        actions,
    )
