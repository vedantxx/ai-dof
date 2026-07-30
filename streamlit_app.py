"""
AI DOF — Command Centre
Streamlit dashboard for the Meridian Holdings Group demo.

Reads the consolidated ledger (data_compact/csv/) and reproduces, live:
  • Consolidated income statement, balance sheet and free cash flow
  • Operating-expense budget vs actual — FY2025 (closed, over budget) and
    FY2026 (in progress, H1 only) — with a cumulative actual-vs-plan line
    and an allocation pie
  • Accounts-receivable aging and customer collection risk
  • Details view: the full CFO review dashboard, embedded

Data source: the CSVs committed in this repo (data_compact/csv/), which are
the same underlying data imported into the Quadratic workbook. The app does
NOT query Quadratic live. Actuals are real general-ledger activity; opening
balances, budget allocations and the FY2026 projection are modelled.

Run locally:   streamlit run streamlit_app.py
"""

from __future__ import annotations
import hashlib
import itertools
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go

# --------------------------------------------------------------------------- #
#  Configuration
# --------------------------------------------------------------------------- #
DATA_DIR = Path(__file__).parent / "data_compact" / "csv"
CFO_HTML = Path(__file__).parent / "cfo-review-ai-dof-command-centre-jul2026.html"
FX_EUR = 1.09
NAVY, TEAL, AMBER, RED, GREEN, SLATE = (
    "#1F3864", "#0F6B4F", "#B45309", "#B3261E", "#2E5A9E", "#8A99AD",
)

QUARTERS = ["2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2",
            "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]
FY = {
    "FY2024 (H2)": ["2024-Q3", "2024-Q4"],
    "FY2025": ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"],
    "FY2026 (H1, ongoing)": ["2026-Q1", "2026-Q2"],
}
FY25 = ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]
H126 = ["2026-Q1", "2026-Q2"]

# Opening trial balance (1 Jul 2024) — MODELLED, source ledger has no opening position
OPENING = dict(cash=12_000_000, ar=0, allowance=0, ppe_gross=18_000_000,
               accum_dep=0, ap=1_200_000, notes=4_500_000, capital=24_300_000)

# Operating-expense categories:
#   (label, [accounts], behaviour, FY2025 allocation, FY2026 full-year budget)
# Actuals are computed live. Allocations & FY2026 budgets are MODELLED so that
# FY2025 lands over budget and FY2026 is tracked in-progress against plan.
OPEX_CATS = [
    ("Compensation & benefits",         ["6000"],                                 "Fixed",    4_600_000, 4_880_000),
    ("Occupancy & facilities",          ["6100", "6110", "6120", "6130", "6150"], "Fixed",      879_000,   950_000),
    ("Technology & data",               ["6200", "6210", "6220"],                 "Fixed",      357_000,   409_000),
    ("Insurance & risk",                ["6500", "6510"],                         "Fixed",      553_000,   587_000),
    ("Depreciation & amortisation",     ["6700"],                                 "Fixed",    1_848_000, 1_903_000),
    ("Professional & advisory fees",    ["6300", "6310", "6320"],                 "Variable",   310_000,   345_000),
    ("Brand, marketing & travel",       ["6400", "6420", "6430"],                 "Variable",   229_000,   220_000),
    ("Office & general administration", ["6140"],                                 "Variable",   178_000,   204_000),
    ("Other general & administrative",  ["6600", "6630"],                         "Variable",    99_000,    99_000),
    ("Credit provisions (bad debt)",    ["6610"],                                 "Variable",    44_000,    52_000),
]

ENTITY_NAMES = {
    "MHG": "Meridian Holdings Group LLC", "MLG": "Meridian Logistics LLC",
    "CFS": "Cascade Freight Systems Inc", "NWC": "Northwind Cargo B.V.",
    "APX": "Apex Warehousing LLC",
}


# --------------------------------------------------------------------------- #
#  Data loading & aggregation engine
# --------------------------------------------------------------------------- #
def _quarter(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    return f"{y}-Q{(m - 1) // 3 + 1}"


@st.cache_data(show_spinner=False)
def load_ledger():
    def rd(name):
        return pd.read_csv(DATA_DIR / name, dtype=str)

    coa, inv, je, bank = (rd("Chart_of_Accounts.csv"), rd("Invoices.csv"),
                          rd("Journal_Entries.csv"), rd("Bank_Data.csv"))
    cls = dict(zip(coa["AccountNumber"], coa["Classification"]))
    typ = dict(zip(coa["AccountNumber"], coa["AccountType"]))

    def f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return 0.0

    act: dict[tuple[str, str], float] = {}

    def post(acct, period, s):
        q = _quarter(period)
        act[(acct, q)] = act.get((acct, q), 0.0) + s

    for _, r in inv.iterrows():
        a = f(r["TotalAmtUSD"]); post("1100", r["Period"], +a); post(str(r["IncomeAccountNum"]), r["Period"], -a)
    for _, r in je.iterrows():
        post(str(r["AccountNum"]), r["Period"], f(r["AmountUSD"]))
    for _, r in bank.iterrows():
        a = f(r["AmountUSD"]); post("1000", r["Period"], +a); post(str(r["CategoryAccountNum"]), r["Period"], -a)

    return dict(act=act, cls=cls, typ=typ, coa=coa, inv=inv, je=je, bank=bank)


def build_engine(L):
    act, cls, typ = L["act"], L["cls"], L["typ"]
    accounts = sorted({k[0] for k in act})

    def activity(acct, qs):
        return sum(act.get((acct, q), 0.0) for q in qs)

    def A(accts, qs):
        return sum(act.get((a, q), 0.0) for a in accts for q in qs)

    def cumbal(acct, upto):
        return sum(act.get((acct, q), 0.0) for q in QUARTERS[:QUARTERS.index(upto) + 1])

    rev_ops = [a for a in accounts if typ.get(a) == "Income" and a != "4950"]
    cogs = [a for a in accounts if cls.get(a) == "Cost of Goods Sold"]
    return dict(accounts=accounts, activity=activity, A=A, cumbal=cumbal, rev_ops=rev_ops, cogs=cogs)


# --------------------------------------------------------------------------- #
#  Statement builders
# --------------------------------------------------------------------------- #
def income_statement(E):
    activity, rev_ops, cogs = E["activity"], E["rev_ops"], E["cogs"]
    rev = lambda qs: -sum(activity(a, qs) for a in rev_ops)
    cogs_v = lambda qs: sum(activity(a, qs) for a in cogs)
    grp = lambda accs, qs: sum(activity(a, qs) for a in accs if a in E["accounts"])
    cols, colq = list(FY.keys()) + ["2-Yr Total"], list(FY.values()) + [QUARTERS]

    def ni(qs):
        opex = sum(grp(a, qs) for _, a, _, _, _ in OPEX_CATS)
        return rev(qs) - cogs_v(qs) - opex - grp(["7030"], qs) - grp(["9000"], qs)

    rows = [("Revenue, net", [rev(q) for q in colq]),
            ("Cost of services", [cogs_v(q) for q in colq]),
            ("Gross profit", [rev(q) - cogs_v(q) for q in colq]),
            ("Gross margin %", [(rev(q) - cogs_v(q)) / rev(q) if rev(q) else 0 for q in colq])]
    for label, accs, _, _, _ in OPEX_CATS:
        rows.append((label, [grp(accs, q) for q in colq]))
    rows += [("Operating income (EBIT)",
              [rev(q) - cogs_v(q) - sum(grp(a, q) for _, a, _, _, _ in OPEX_CATS) for q in colq]),
             ("FX gain / (loss)", [-grp(["7030"], q) for q in colq]),
             ("Net income / (loss)", [ni(q) for q in colq])]
    df = pd.DataFrame({c: {r[0]: r[1][i] for r in rows} for i, c in enumerate(cols)})
    return df.reindex([r[0] for r in rows]), ni, rev


def balance_sheet(E, ni):
    cumbal = E["cumbal"]
    cols = ["Opening 1 Jul 24"] + QUARTERS
    cum_ni = lambda q: 0 if q is None else ni(QUARTERS[:QUARTERS.index(q) + 1])
    cb = lambda a, q: (cumbal(a, q) if q else 0)
    cash = lambda q: OPENING["cash"] + cb("1000", q)
    ar_g = lambda q: OPENING["ar"] + cb("1100", q)
    allow = lambda q: OPENING["allowance"] + cb("1150", q)
    ppe = lambda q: OPENING["ppe_gross"]
    acc = lambda q: OPENING["accum_dep"] + cb("1590", q)
    ap = lambda q: OPENING["ap"] - cb("2000", q)
    notes = lambda q: OPENING["notes"] - cb("2410", q)
    tot_a = lambda q: cash(q) + ar_g(q) + allow(q) + ppe(q) + acc(q)
    tot_l = lambda q: ap(q) + notes(q)
    tot_e = lambda q: OPENING["capital"] + cum_ni(q)
    rows = [("Cash & bank", cash), ("Accounts receivable, gross", ar_g),
            ("Allowance for doubtful accounts", allow), ("Property & equipment, gross", ppe),
            ("Accumulated depreciation", acc), ("Total assets", tot_a),
            ("Accounts payable", ap), ("Equipment notes payable", notes), ("Total liabilities", tot_l),
            ("Contributed capital (member units)", lambda q: OPENING["capital"]),
            ("Retained earnings / (deficit)", cum_ni), ("Total equity", tot_e),
            ("Total liabilities & equity", lambda q: tot_l(q) + tot_e(q))]
    val = lambda fn: [fn(None)] + [fn(q) for q in QUARTERS]
    df = pd.DataFrame({c: {lbl: val(fn)[i] for lbl, fn in rows} for i, c in enumerate(cols)})
    return df.reindex([r[0] for r in rows]), cash


def cash_flow(E, ni):
    A = E["A"]
    cols, colq = list(FY.keys()) + ["2-Yr Total"], list(FY.values()) + [QUARTERS]
    cfo = lambda qs: ni(qs) - A(["1590"], qs) - A(["1150"], qs) - A(["1100"], qs) - A(["2000"], qs)
    rows = [("Net income / (loss)", lambda qs: ni(qs)),
            ("Add: depreciation (non-cash)", lambda qs: -A(["1590"], qs)),
            ("Add: bad debt provision (non-cash)", lambda qs: -A(["1150"], qs)),
            ("(Increase)/decrease in receivables", lambda qs: -A(["1100"], qs)),
            ("Increase/(decrease) in payables", lambda qs: -A(["2000"], qs)),
            ("Net cash from operations", cfo),
            ("Repayment of equipment notes", lambda qs: -A(["2410"], qs)),
            ("Net change in cash", lambda qs: cfo(qs) - A(["2410"], qs)),
            ("Free cash flow (CFO less capex)", cfo)]
    df = pd.DataFrame({c: {lbl: fn(colq[i]) for lbl, fn in rows} for i, c in enumerate(cols)})
    return df.reindex([r[0] for r in rows])


def budget_model(E):
    """FY2025 (closed, over budget) and FY2026 (in progress, H1 only)."""
    activity = E["activity"]
    recs = []
    for label, accs, beh, alloc25, bud26 in OPEX_CATS:
        act25 = sum(activity(a, FY25) for a in accs if a in E["accounts"])
        h1 = sum(activity(a, H126) for a in accs if a in E["accounts"])
        proj = h1 * 2
        recs.append(dict(Category=label, Behaviour=beh,
                         Alloc25=alloc25, Act25=act25, Var25=alloc25 - act25,
                         Util25=act25 / alloc25 if alloc25 else 0,
                         Bud26=bud26, H1_26=h1, Proj26=proj,
                         PUtil26=proj / bud26 if bud26 else 0))
    df = pd.DataFrame(recs)

    # cumulative line: actual vs plan across the two budget years
    qx = ["Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26", "Q2'26", "Q3'26e", "Q4'26e"]
    q_actual = [sum(activity(a, [q]) for _, accs, _, _, _ in OPEX_CATS for a in accs if a in E["accounts"])
                for q in FY25 + H126]
    alloc25_t, bud26_t = df["Alloc25"].sum(), df["Bud26"].sum()
    h1_t = df["H1_26"].sum()
    budget_q = [alloc25_t / 4] * 4 + [bud26_t / 4] * 4
    actual_q = q_actual + [h1_t / 2, h1_t / 2]
    cum = lambda xs: list(itertools.accumulate(xs))
    budget_cum = cum(budget_q)
    actual_cum = cum(actual_q)
    return df, qx, budget_cum, actual_cum


TTM = ["2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]   # trailing twelve months


def kpi_ratios(E, ni, rev, bs_df):
    """Headline ratios on a trailing-twelve-month basis.

    TTM rather than fiscal year: FY2026 is a half-year in this dataset, so a
    fiscal-year figure would either be half-sized or an annualised guess. The
    trailing four quarters are all actual.
    """
    activity = E["activity"]
    cogs_ttm = sum(activity(a, TTM) for a in E["cogs"])
    rev_ttm = rev(TTM)
    opex_ttm = sum(activity(a, TTM) for _, accs, _, _, _ in OPEX_CATS
                   for a in accs if a in E["accounts"])
    dep_ttm = sum(activity(a, TTM) for a in ["6700"] if a in E["accounts"])
    ebit_ttm = rev_ttm - cogs_ttm - opex_ttm
    ni_ttm = ni(TTM)

    at = lambda row: float(bs_df.loc[row, "2026-Q2"])
    cash, ar_gross, allowance = at("Cash & bank"), at("Accounts receivable, gross"), \
        at("Allowance for doubtful accounts")
    ap, notes, equity = at("Accounts payable"), at("Equipment notes payable"), \
        at("Total equity")
    ar_net = ar_gross + allowance          # allowance is carried negative
    current_assets, current_liabs = cash + ar_net, ap
    # Cash operating cost excludes depreciation, which does not consume cash.
    monthly_burn = (cogs_ttm + opex_ttm - dep_ttm) / 12

    return dict(
        rev_ttm=rev_ttm, ebitda=ebit_ttm + dep_ttm, ebit=ebit_ttm, ni=ni_ttm,
        gross_margin=(rev_ttm - cogs_ttm) / rev_ttm,
        ebitda_margin=(ebit_ttm + dep_ttm) / rev_ttm,
        net_margin=ni_ttm / rev_ttm,
        roe=ni_ttm / equity,
        current_ratio=current_assets / current_liabs,
        working_capital=current_assets - current_liabs,
        net_debt=notes - cash,
        dso=ar_net / rev_ttm * 365,
        dpo=ap / cogs_ttm * 365,
        runway=cash / monthly_burn,
        cash=cash, equity=equity, ar_net=ar_net,
    )


@st.cache_data(show_spinner=False)
def ar_analysis(_inv: pd.DataFrame):
    inv = _inv.copy()
    for c in ("TotalAmtUSD", "Balance"):
        inv[c] = pd.to_numeric(inv[c], errors="coerce").fillna(0)
    inv["TxnDate"] = pd.to_datetime(inv["TxnDate"], errors="coerce")
    asof = pd.Timestamp("2026-06-30")
    o = inv[inv["Status"].str.lower() == "open"].copy()
    o["days"] = (asof - o["TxnDate"]).dt.days
    bucket = lambda d: ("Current / 0-30" if d <= 30 else "31-60" if d <= 60 else
                        "61-90" if d <= 90 else "91-120" if d <= 120 else "120+")
    o["bucket"] = o["days"].apply(bucket)
    order = ["Current / 0-30", "31-60", "61-90", "91-120", "120+"]
    aging = o.groupby("bucket")["Balance"].agg(["sum", "count"]).reindex(order).fillna(0)
    cust = (o.groupby("CustomerRef_name")
            .agg(Balance=("Balance", "sum"), Open=("Balance", "size"), AvgDays=("days", "mean"))
            .sort_values("Balance", ascending=False).head(12).round(0))
    return aging, cust, o["Balance"].sum()


@st.cache_data(show_spinner=False)
def portfolio_summary() -> dict | None:
    """Headline figures from the portfolio tearsheet, for the Details page card."""
    from portfolio import analytics as pan, config as pcfg

    if not pcfg.RETURNS_CSV.exists():
        return None
    res = pan.run_full_analysis(pan.load_returns(pcfg.RETURNS_CSV), try_live=False)
    breached = [b for b in res.breaches if b.breached]
    largest = res.holdings["weight"].astype(float).idxmax()
    return {
        "value": money(res.notional),
        "gain_pct": f"{res.notional / res.cost_basis - 1:+.1%}",
        "alpha": f"{res.ff5.alpha_annualized:+.1%}",
        "mdd": f"{res.perf_portfolio.max_drawdown:.1%}",
        "dd_limit": f"{pcfg.POLICY['max_drawdown']:.0%}",
        "breaches": f"{len(breached)} of {len(res.breaches)}",
        "breach_names": ", ".join(b.check.split()[0].lower() for b in breached),
        "largest": largest,
        "largest_weight": f"{float(res.holdings.loc[largest, 'weight']):.1%}",
        "weight_limit": f"{pcfg.POLICY['max_weight']:.0%}",
    }


@st.cache_data(show_spinner="Running the factor regressions…")
def portfolio_tearsheet(window: int, theme: str) -> str:
    """Full portfolio analysis, rendered to a self-contained HTML page.

    Cached per window: the rolling regressions re-fit on every window change and
    cost a second or two.
    """
    from portfolio import analytics as tan, config as tcfg, render as trender

    returns = tan.load_returns(tcfg.RETURNS_CSV)
    res = tan.run_full_analysis(returns, window=window, try_live=False)
    return trender.render_tearsheet(res, theme=theme)


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def money(v):
    if pd.isna(v):
        return ""
    v = float(v)
    if abs(v) >= 1e6: return f"${v/1e6:,.2f}M"
    if abs(v) >= 1e3: return f"${v/1e3:,.0f}k"
    return f"${v:,.0f}"


def fmt_df(df, pct_rows=()):
    return df.apply(lambda row: row.map(
        lambda v: f"{v*100:.1f}%" if row.name in pct_rows
        else (f"{v:,.0f}" if isinstance(v, (int, float)) else v)), axis=1)


# --------------------------------------------------------------------------- #
#  Theme
# --------------------------------------------------------------------------- #
#  Streamlit's own light/dark setting lives in its Settings menu and cannot be
#  changed from script code for a live session, so the toggle owns the styling:
#  injected CSS for the app chrome, a palette for every Plotly figure, and the
#  theme argument the tearsheet renders with. One caveat, called out in the
#  sidebar: st.dataframe renders to a canvas, so its cell colours follow
#  Streamlit's own setting rather than ours.
DARK = dict(bg="#0a0e17", panel="#131a2b", border="rgba(96,165,250,0.16)",
            text="#e2e8f0", muted="#94a3b8", accent="#4ade80",
            template="plotly_dark", grid="rgba(148,163,184,0.14)")
LIGHT = dict(bg="#ffffff", panel="#f6f8fb", border="rgba(31,56,100,0.14)",
             text="#14203a", muted="#5b6b85", accent="#0F6B4F",
             template="plotly_white", grid="rgba(31,56,100,0.10)")


def theme_palette(theme: str) -> dict:
    return DARK if theme == "dark" else LIGHT


def inject_theme_css(theme: str) -> None:
    """Restyle Streamlit's chrome to match the chosen theme."""
    p = theme_palette(theme)

    # The top bar replaces the sidebar, so its styling applies in both themes.
    st.markdown(f"""
        <style>
        /* No sidebar: pull the page up and give the top bar room. */
        [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{
            display: none;
        }}
        [data-testid="stAppViewBlockContainer"] {{ padding-top: 2.4rem; }}
        .brandbar {{ display: flex; align-items: baseline; gap: 8px;
                     flex-wrap: wrap; line-height: 1.2; }}
        .brandbar-mark {{ color: {p['accent']}; font-size: 17px; }}
        .brandbar-name {{ font-weight: 700; letter-spacing: 1.2px;
                          font-size: 17px; color: {p['text']}; }}
        .brandbar-sub {{ font-size: 11.5px; color: {p['muted']};
                         letter-spacing: 0.2px; }}
        .topbar-rule {{ height: 1px; background: {p['border']};
                        margin: 10px 0 18px; }}
        </style>""", unsafe_allow_html=True)

    if theme != "dark":
        return          # light is Streamlit's default; nothing further to override
    st.markdown(f"""
        <style>
        [data-testid="stAppViewContainer"], [data-testid="stHeader"],
        [data-testid="stBottomBlockContainer"] {{ background: {p['bg']}; }}
        [data-testid="stSidebarContent"] {{ background: {p['panel']}; }}
        [data-testid="stAppViewContainer"] *:not(svg):not(path),
        [data-testid="stSidebarContent"] *:not(svg):not(path) {{
            color: {p['text']};
        }}
        [data-testid="stMetricLabel"], [data-testid="stCaptionContainer"],
        .stCaption, small {{ color: {p['muted']} !important; }}
        [data-testid="stMetricValue"] {{ color: {p['text']} !important; }}
        /* The top-bar controls keep Streamlit's light widget background (base is
           light in config.toml), which left pale text on white. Restyle both
           states off aria-checked. */
        [data-testid="stButtonGroup"] button[aria-checked="false"] {{
            background: {p['panel']} !important;
            border-color: {p['border']} !important;
            color: {p['muted']} !important;
        }}
        [data-testid="stButtonGroup"] button[aria-checked="false"]:hover {{
            color: {p['text']} !important;
        }}
        [data-testid="stButtonGroup"] button[aria-checked="true"] {{
            background: rgba(74, 222, 128, 0.14) !important;
            border-color: rgba(74, 222, 128, 0.45) !important;
            color: {p['accent']} !important;
        }}
        [data-testid="stExpander"], [data-testid="stNotification"] {{
            background: {p['panel']}; border: 1px solid {p['border']};
        }}
        hr {{ border-color: {p['border']}; }}
        </style>""", unsafe_allow_html=True)


# Embedded documents are written to disk and shown with st.iframe(height="content"),
# which sizes the frame to its content so the page has ONE scrollbar. The obvious
# alternatives both fail: components.html takes a fixed height and gives the
# document its own scrollbar, and the streamlit:setFrameHeight message that custom
# components use is ignored for static HTML.
EMBED_DIR = Path(tempfile.gettempdir()) / "ai-dof-embeds"


# The CFO review dashboard is variable-driven, so dark mode is an override of its
# own :root rather than a rewrite. Its body background is hardcoded, hence the
# explicit rule.
_CFO_DARK_CSS = """
<style>
:root{
  --ink:#e2e8f0 !important; --ink-2:#cbd5e1 !important; --slate:#94a3b8 !important;
  --mute:#7b8aa3 !important; --line:rgba(96,165,250,0.18) !important;
  --line-2:rgba(96,165,250,0.10) !important; --canvas:#0a0e17 !important;
  --card:#131a2b !important;
  /* --brand is a BACKGROUND here (the masthead), not an accent: lightening it to
     #60a5fa produced a bright blue block with pale text on it. */
  --brand:#16233d !important; --brand-2:#7fb3ff !important;
  --critical:#f87171 !important; --critical-bg:rgba(248,113,113,0.12) !important;
  --high:#fbbf24 !important;    --high-bg:rgba(251,191,36,0.12) !important;
  --medium:#e9c46a !important;  --medium-bg:rgba(233,196,106,0.10) !important;
  --low:#86efac !important;     --low-bg:rgba(134,239,172,0.10) !important;
  --ok:#4ade80 !important;      --ok-bg:rgba(74,222,128,0.12) !important;
  --shadow:0 1px 2px rgba(0,0,0,.35), 0 4px 14px rgba(0,0,0,.35) !important;
}
html, body { background:#0a0e17 !important; color:var(--ink) !important; }
table, th, td { border-color:var(--line) !important; }
thead th { background:rgba(96,165,250,0.06) !important; }
</style>
"""


def embed_document(html: str, theme: str, extra_css: str = "") -> None:
    """Embed a self-contained HTML document with one scrollbar, not two."""
    if extra_css:
        if "</head>" in html:
            html = html.replace("</head>", extra_css + "</head>", 1)
        else:
            html = extra_css + html
    EMBED_DIR.mkdir(parents=True, exist_ok=True)
    # Content-addressed, so a given theme/window renders to one stable file.
    path = EMBED_DIR / f"{hashlib.sha256(html.encode()).hexdigest()[:16]}.html"
    if not path.exists():
        path.write_text(html, encoding="utf-8")
    st.iframe(path, height="content", width="stretch")


def style_fig(fig, theme: str):
    """Apply the active palette to a Plotly figure built for either theme."""
    p = theme_palette(theme)
    # Legend and axis text are SVG, coloured by `fill` rather than CSS `color`,
    # so the global font setting does not reach them — set both explicitly or the
    # legend renders dark-on-dark.
    fig.update_layout(template=p["template"],
                      paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color=p["muted"]),
                      legend=dict(font=dict(color=p["text"])))
    # Only touch the title when there is one: setting title.font on a figure
    # without title text makes Plotly render the literal string "undefined".
    if fig.layout.title.text:
        fig.update_layout(title=dict(font=dict(color=p["text"])))
    fig.update_xaxes(gridcolor=p["grid"], color=p["muted"],
                     title_font=dict(color=p["muted"]))
    fig.update_yaxes(gridcolor=p["grid"], color=p["muted"],
                     title_font=dict(color=p["muted"]))
    return fig


# --------------------------------------------------------------------------- #
#  App
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="AI DOF — Command Centre", page_icon="📊", layout="wide")

if not DATA_DIR.exists():
    st.error(f"Data folder not found at `{DATA_DIR}`. Run from the repo root.")
    st.stop()

L = load_ledger()
E = build_engine(L)
is_df, ni, rev = income_statement(E)
bs_df, cash_fn = balance_sheet(E, ni)
cf_df = cash_flow(E, ni)
bud, qx, budget_cum, actual_cum = budget_model(E)
aging, cust_risk, ar_open = ar_analysis(L["inv"])

total_rev = rev(QUARTERS)
total_ni = ni(QUARTERS)

# --------------------------------------------------------------------------- #
#  Top bar — brand, navigation, theme
# --------------------------------------------------------------------------- #
PAGES = ["Overview", "Financial statements", "Budget tracker",
         "Receivables & risk", "Portfolio & factors", "Details"]
THEME_ICONS = {"dark": ":material/dark_mode:", "light": ":material/light_mode:"}

# Seed the theme from the URL on first load so ?theme=light is shareable, then
# let the control own it.
_qp_theme = st.query_params.get("theme")
if "theme" not in st.session_state:
    st.session_state["theme"] = _qp_theme if _qp_theme in ("dark", "light") else "dark"

brand, nav, toggle = st.columns([2.1, 6.4, 1.5], vertical_alignment="center")
with brand:
    st.markdown(
        "<div class='brandbar'><span class='brandbar-mark'>◆</span>"
        "<span class='brandbar-name'>AI DOF</span>"
        "<span class='brandbar-sub'>Meridian Holdings Group · consolidated · USD</span>"
        "</div>", unsafe_allow_html=True)
with nav:
    page = st.segmented_control(
        "View", PAGES, default=st.session_state.get("page", PAGES[0]),
        key="page", label_visibility="collapsed")
with toggle:
    theme = st.segmented_control(
        "Theme", ["dark", "light"], key="theme", label_visibility="collapsed",
        format_func=lambda t: THEME_ICONS[t])

# segmented_control returns None if the user deselects; fall back rather than crash.
page = page or PAGES[0]
theme = theme or "dark"
if st.query_params.get("theme") != theme:
    st.query_params["theme"] = theme
inject_theme_css(theme)
st.markdown("<div class='topbar-rule'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- Overview -- #
if page == "Overview":
    st.title("AI DOF — Command Centre")
    st.caption("An AI-augmented Director of Finance workflow · 24 months to Jun 2026")
    c = st.columns(4)
    gp = total_rev - sum(E["activity"](a, QUARTERS) for a in E["cogs"])
    c[0].metric("Revenue (2 yr)", money(total_rev))
    c[1].metric("Gross margin", f"{gp/total_rev*100:.1f}%")
    c[2].metric("Net income (2 yr)", money(total_ni))
    c[3].metric("Cash, Jun 2026", money(cash_fn("2026-Q2")))

    st.markdown("#### Revenue and gross margin by quarter")
    q_rev = [rev([q]) for q in QUARTERS]
    q_gp = [rev([q]) - sum(E["activity"](a, [q]) for a in E["cogs"]) for q in QUARTERS]
    q_gm = [g / r if r else 0 for g, r in zip(q_gp, q_rev)]
    fig = go.Figure()
    fig.add_bar(x=QUARTERS, y=q_rev, name="Revenue", marker_color=NAVY)
    fig.add_bar(x=QUARTERS, y=q_gp, name="Gross profit", marker_color=TEAL)
    fig.add_scatter(x=QUARTERS, y=[g * max(q_rev) for g in q_gm], name="Gross margin %",
                    yaxis="y2", mode="lines+markers", line=dict(color=AMBER, width=3))
    fig.update_layout(barmode="group", height=380, legend=dict(orientation="h", y=1.1),
                      yaxis=dict(title="USD"),
                      yaxis2=dict(overlaying="y", side="right", showgrid=False,
                                  range=[0, max(q_rev)], showticklabels=False),
                      margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(style_fig(fig, theme), use_container_width=True)
    st.info("Gross margin steps down 36.6% → 35.5% → 34.4% — the planted Cascade Freight "
            "erosion, masked at group level by Apex improving in step.")

    st.markdown("#### The company")
    st.dataframe(pd.DataFrame([
        {"Entity": k, "Legal name": v, "Currency": "EUR" if k == "NWC" else "USD", "Role": role}
        for (k, v), role in zip(ENTITY_NAMES.items(), [
            "Holding company / shared services", "Freight brokerage & last mile",
            "Asset-based trucking (acquired Mar-2024)", "EU forwarding, customs & TMS software",
            "Warehousing & fulfillment (3PL)"])]),
        hide_index=True, use_container_width=True)

# --------------------------------------------------- Financial statements -- #
elif page == "Financial statements":
    st.title("Financial statements")
    st.caption("Consolidated · USD · EUR entity at 1.09 · intercompany eliminated · "
               "FY2026 is a half-year (H1) — the year is still in progress")

    k = kpi_ratios(E, ni, rev, bs_df)
    st.markdown("##### Trailing twelve months · Jul 2025 → Jun 2026")
    c = st.columns(4)
    c[0].metric("Revenue", money(k["rev_ttm"]))
    c[1].metric("EBITDA", money(k["ebitda"]), f"{k['ebitda_margin']*100:.1f}% margin")
    c[2].metric("Net income", money(k["ni"]), f"{k['net_margin']*100:.1f}% margin",
                delta_color="inverse" if k["ni"] < 0 else "normal")
    c[3].metric("Return on equity", f"{k['roe']*100:.1f}%",
                delta_color="inverse" if k["roe"] < 0 else "normal")

    st.markdown("##### Liquidity & working capital · as at 30 Jun 2026")
    c = st.columns(4)
    c[0].metric("Current ratio", f"{k['current_ratio']:.2f}×",
                f"working capital {money(k['working_capital'])}")
    c[1].metric("Net debt", money(k["net_debt"]),
                "notes payable less cash",
                delta_color="inverse" if k["net_debt"] > 0 else "normal")
    c[2].metric("DSO", f"{k['dso']:.0f} days", f"DPO {k['dpo']:.0f} days")
    c[3].metric("Cash runway", f"{k['runway']:.1f} months",
                "at the trailing cash cost")
    st.info(
        f"Two things stand out. The group is essentially **EBITDA-breakeven** on a "
        f"trailing basis ({k['ebitda_margin']*100:.1f}% margin on "
        f"{money(k['rev_ttm'])} of revenue), so there is no operating cushion under "
        f"the {money(abs(k['ni']))} loss. And it collects in {k['dso']:.0f} days while "
        f"paying in {k['dpo']:.0f} — a {k['dso'] - k['dpo']:.0f}-day gap it funds from "
        f"its own balance sheet, which is what leaves {k['runway']:.1f} months of "
        f"runway on {money(k['cash'])} of cash.")
    st.caption(
        "Ratios use the trailing four quarters of actual ledger activity; "
        "balance-sheet inputs sit on the modelled opening position. Current "
        "liabilities are accounts payable only — this ledger carries no accruals or "
        "current portion of debt, which is why the current ratio reads high. Cash "
        "runway excludes depreciation, which does not consume cash.")
    st.markdown("")

    t1, t2, t3 = st.tabs(["Income statement", "Balance sheet", "Cash flow"])
    with t1:
        st.dataframe(fmt_df(is_df, ["Gross margin %"]), use_container_width=True, height=560)
    with t2:
        st.warning("Opening balances (1 Jul 2024) are **modelled**; every column balances "
                   "(assets = liabilities + equity).")
        st.dataframe(fmt_df(bs_df), use_container_width=True, height=520)
    with t3:
        st.dataframe(fmt_df(cf_df), use_container_width=True, height=380)

# ------------------------------------------------------- Budget tracker --- #
elif page == "Budget tracker":
    st.title("Operating expense — budget vs actual")
    st.caption("Actuals from the ledger · allocations and the FY2026 projection modelled")

    # ---- FY2025 (closed, over budget) ----
    a25, b25 = bud["Act25"].sum(), bud["Alloc25"].sum()
    overs = int((bud["Util25"] > 1).sum())
    st.subheader("FY2025 · closed")
    c = st.columns(4)
    c[0].metric("Allocation", money(b25))
    c[1].metric("Actual", money(a25), f"{a25/b25*100:.1f}% of budget", delta_color="inverse")
    c[2].metric("Over budget by", money(a25 - b25), delta_color="inverse")
    c[3].metric("Categories over", f"{overs} of {len(bud)}", delta_color="inverse")

    b = bud.sort_values("Util25")
    colors = [RED if u > 1.10 else AMBER if u > 1 else TEAL for u in b["Util25"]]
    fig = go.Figure(go.Bar(x=b["Util25"] * 100, y=b["Category"], orientation="h",
                           marker_color=colors, text=[f"{u*100:.0f}%" for u in b["Util25"]],
                           textposition="outside"))
    fig.add_vline(x=100, line=dict(color=RED, dash="dash"), annotation_text="100% allocation")
    fig.update_layout(height=430, xaxis_title="Utilisation %", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(style_fig(fig, theme), use_container_width=True)

    # ---- FY2026 (in progress) ----
    st.subheader("FY2026 · in progress (H1 actuals only)")
    bud26, h1, proj = bud["Bud26"].sum(), bud["H1_26"].sum(), bud["Proj26"].sum()
    c = st.columns(4)
    c[0].metric("Full-year budget", money(bud26))
    c[1].metric("H1 actual", money(h1), "50% of year elapsed")
    c[2].metric("Projected full-year", money(proj), f"{proj/bud26*100:.0f}% of budget", delta_color="inverse")
    c[3].metric("Projected variance", money(bud26 - proj), delta_color="normal")
    st.caption("Projection annualises H1 actuals. On current pace FY2026 also runs over plan.")

    # ---- line: cumulative actual vs plan ----
    st.markdown("#### Actual vs planned allocation — cumulative")
    fig2 = go.Figure()
    fig2.add_scatter(x=qx, y=budget_cum, name="Planned allocation", mode="lines+markers",
                     line=dict(color=NAVY, width=3))
    fig2.add_scatter(x=qx[:6], y=actual_cum[:6], name="Actual spend", mode="lines+markers",
                     line=dict(color=TEAL, width=3))
    fig2.add_scatter(x=qx[5:], y=actual_cum[5:], name="Projected", mode="lines+markers",
                     line=dict(color=AMBER, width=3, dash="dash"))
    fig2.update_layout(height=400, yaxis_title="Cumulative USD",
                       legend=dict(orientation="h", y=1.12), margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(style_fig(fig2, theme), use_container_width=True)

    # ---- pie: allocation mix ----
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("#### FY2025 allocation by category")
        fig3 = go.Figure(go.Pie(labels=bud["Category"], values=bud["Alloc25"], hole=0.45,
                                textinfo="percent", sort=False))
        fig3.update_layout(height=430, legend=dict(orientation="v", x=1.0, font=dict(size=10)),
                           margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(style_fig(fig3, theme), use_container_width=True)
    with col2:
        st.markdown("#### Detail")
        show = bud.copy()
        for c_ in ("Alloc25", "Act25", "Var25", "Bud26", "H1_26", "Proj26"):
            show[c_] = show[c_].map(lambda v: f"{v:,.0f}")
        show["Util25"] = show["Util25"].map(lambda v: f"{v*100:.0f}%")
        show = show.rename(columns={"Alloc25": "FY25 alloc", "Act25": "FY25 actual",
                                    "Util25": "FY25 util", "Bud26": "FY26 budget", "H1_26": "FY26 H1"})
        st.dataframe(show[["Category", "Behaviour", "FY25 alloc", "FY25 actual",
                           "FY25 util", "FY26 budget", "FY26 H1"]],
                     hide_index=True, use_container_width=True, height=430)

# --------------------------------------------------- Receivables & risk --- #
elif page == "Receivables & risk":
    st.title("Accounts receivable & collection risk")
    st.caption("Open invoices as at 30 Jun 2026")
    c = st.columns(3)
    over90 = aging.loc[["91-120", "120+"], "sum"].sum()
    c[0].metric("Open receivables", money(ar_open))
    c[1].metric("Aged 90+ days", money(over90))
    c[2].metric("90+ share", f"{over90/ar_open*100:.0f}%")
    st.markdown("#### Aging profile")
    colors = [TEAL, "#6E9B33", AMBER, "#C0392B", RED]
    fig = go.Figure(go.Bar(x=aging.index, y=aging["sum"], marker_color=colors,
                           text=[money(v) for v in aging["sum"]], textposition="outside"))
    fig.update_layout(height=360, yaxis_title="Balance (USD)", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(style_fig(fig, theme), use_container_width=True)
    st.markdown("#### Largest open balances")
    cr = cust_risk.reset_index().rename(columns={"CustomerRef_name": "Customer", "AvgDays": "Avg days outstanding"})
    cr["Balance"] = cr["Balance"].map(money)
    cr["Avg days outstanding"] = cr["Avg days outstanding"].map(lambda v: f"{v:.0f}")
    st.dataframe(cr, hide_index=True, use_container_width=True)

# --------------------------------------------------- Portfolio & factors --- #
elif page == "Portfolio & factors":
    from portfolio import config as tcfg

    st.title("Portfolio & factor analysis")
    st.caption(
        "Meridian Holdings Group as investor: the four operating stakes it owns, "
        "marked and analysed · CAPM, Fama-French 3- and 5-factor regressions, "
        "rolling factor betas and investment-policy compliance")

    if not tcfg.RETURNS_CSV.exists():
        st.error(
            "Portfolio data not found. Generate it with:\n\n"
            "```\npython3 generate_portfolio_data.py\n```")
    else:
        window = st.radio(
            "Rolling window", tcfg.ALLOWED_WINDOWS,
            index=tcfg.ALLOWED_WINDOWS.index(tcfg.DEFAULT_WINDOW),
            format_func=lambda w: f"{w} days",
            horizontal=True,
            help="63 trading days ≈ one quarter. Shorter windows react faster to "
                 "style drift; longer ones are less noisy.")
        st.markdown(
            "The portfolio's full-period beta sits inside the 1.00 mandate ceiling. "
            "The rolling window does not — which is the point of the page.")
        # components.html despite the deprecation notice: st.iframe takes a src
        # path or URL, not a rendered HTML string, and the iframe sandbox is what
        # stops the tearsheet's dark stylesheet leaking into the Streamlit chrome.
        embed_document(portfolio_tearsheet(window, theme), theme)

# ----------------------------------------------------------------- Details - #
elif page == "Details":
    st.title("CFO review — detail")
    st.caption("The full CFO review dashboard, embedded. Follows the app theme.")

    # One card carrying the portfolio tearsheet's conclusion, so the review page
    # opens with it rather than requiring a trip to the other tab.
    summary = portfolio_summary()
    if summary:
        with st.container(border=True):
            st.markdown("#### Portfolio — from the tearsheet")
            c = st.columns(4)
            c[0].metric("Marked value", summary["value"],
                        summary["gain_pct"] + " vs cost")
            c[1].metric("FF5 alpha, net", summary["alpha"], "after the 45bp charge")
            c[2].metric("Max drawdown", summary["mdd"],
                        f"policy −{summary['dd_limit']}", delta_color="inverse")
            c[3].metric("Policy breaches", summary["breaches"],
                        summary["breach_names"], delta_color="inverse")
            st.caption(
                f"{summary['largest']} is the largest position at "
                f"{summary['largest_weight']} against a {summary['weight_limit']} "
                f"limit · full detail on the Portfolio & factors page.")
    if CFO_HTML.exists():
        html = CFO_HTML.read_text(encoding="utf-8")
        if theme == "dark":
            extra = _CFO_DARK_CSS
        else:
            # Light mode keeps the review's own palette, shifted to the app's teal.
            extra = ("<style>:root{--brand:#0F5132 !important;"
                     "--brand-2:#198754 !important;}</style>")
        embed_document(html, theme, extra)
    else:
        st.error("cfo-review-ai-dof-command-centre-jul2026.html not found in the repo root.")

st.markdown("<div class='topbar-rule'></div>", unsafe_allow_html=True)
st.caption("© Meridian Holdings Group is fictional. Data is synthetic.")
