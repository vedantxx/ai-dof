"""Render the portfolio tearsheet to one self-contained HTML page.

The stylesheet and Plotly's JS are inlined, so the output works offline, in an
email client and in print -- the same constraint the CFO review dashboard in this
repo is built to. This module formats and assembles only; every number arrives
already computed on an AnalysisResult.
"""
from __future__ import annotations

import pathlib

from jinja2 import Environment, FileSystemLoader, select_autoescape

from portfolio import charts, config as cfg
from portfolio.analytics import AnalysisResult, _money

_HERE = pathlib.Path(__file__).resolve().parent
_TEMPLATES = _HERE / "templates"
_CSS = _HERE / "static" / "css" / "style.css"


def _plotly_js() -> str:
    """Plotly's minified bundle, read from the installed package.

    Inlined rather than pulled from a CDN: this page must render with no network.
    The file's location inside the package has moved between Plotly versions, so
    fall back to searching for it.
    """
    import plotly

    root = pathlib.Path(plotly.__file__).parent
    candidates = sorted(root.rglob("plotly.min.js"))
    if not candidates:
        raise FileNotFoundError(
            f"Could not locate plotly.min.js under {root} to inline. "
            "The page must not load Plotly from a CDN.")
    return candidates[0].read_text(encoding="utf-8")


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )


def _pct(v: float, dp: int = 2) -> str:
    return "—" if v != v else f"{v:.{dp}%}"


def _num(v: float, dp: int = 2) -> str:
    return "—" if v != v else f"{v:.{dp}f}"


def _loading_rows(result) -> list[dict]:
    return [{
        "name": l.name,
        "coef": _num(l.coef, 4),
        "annualized": _pct(l.annualized) if l.annualized is not None else "—",
        "tstat": _num(l.tstat),
        "pvalue": f"{l.pvalue:.3f}",
        "significant": l.significant,
        "description": l.description,
    } for l in result.loadings]


def _cards(res: AnalysisResult) -> list[dict]:
    p = res.perf_portfolio
    beta = res.capm.loading("Beta (Market)")
    beta_val = beta.coef if beta else float("nan")
    net_alpha = res.ff5.alpha_annualized
    return [
        dict(label="CAGR", value=_pct(p.cagr), positive=p.cagr > 0,
             hint="annualized geometric growth"),
        dict(label="Volatility", value=_pct(p.ann_vol), positive=None,
             hint="annualized, √252 scaling"),
        dict(label="Sharpe", value=_num(p.sharpe), positive=p.sharpe > 1,
             hint="excess return per unit of total risk"),
        dict(label="Sortino", value=_num(p.sortino), positive=p.sortino > 1,
             hint="downside risk only"),
        dict(label="Max drawdown", value=_pct(p.max_drawdown, 1),
             positive=abs(p.max_drawdown) < cfg.POLICY["max_drawdown"],
             hint=f"policy limit −{cfg.POLICY['max_drawdown']:.0%}"),
        dict(label="Beta (full period)", value=_num(beta_val, 3),
             positive=beta_val < cfg.POLICY["max_beta"],
             hint="hides the rolling breach"),
        dict(label="FF5 alpha, net", value=_pct(net_alpha), positive=net_alpha > 0,
             hint=f"after the {cfg.FEE_ANNUAL:.2%} fee"),
        dict(label="Hit rate", value=_pct(p.hit_rate, 1), positive=None,
             hint=f"best {p.best_day:+.2%} / worst {p.worst_day:+.2%}"),
    ]


def _theme_css(theme: str) -> str:
    """Light mode overrides the stylesheet's :root variables rather than shipping
    a second stylesheet that could drift out of step with the first."""
    if theme == "dark":
        return ""
    decls = "".join(f"{k}:{v};" for k, v in cfg.LIGHT_VARS.items())
    # .bg-grid paints the dark radial backdrop; neutralise it in light mode.
    return (f":root{{{decls}}}"
            ".bg-grid{background:var(--bg);}"
            ".bg-grid::after{opacity:0.5;}"
            ".topbar{background:rgba(255,255,255,0.85);}"
            ".metric-card::before{opacity:0.35;}"
            ".banner-warn{background:rgba(180,83,9,0.08);color:#7c3a06;}"
            ".banner-danger{background:rgba(179,38,30,0.06);color:#7f1d1d;}"
            ".breach-body .risk{color:#B3261E;}")


def _holding_rows(res: AnalysisResult) -> list[dict]:
    h = res.holdings.sort_values("value", ascending=False)
    return [dict(
        ticker=t,
        name=h.loc[t, "name"],
        business=h.loc[t, "business"],
        ownership=f"{float(h.loc[t, 'ownership']):.0%}",
        shares=f"{float(h.loc[t, 'shares']):,.0f}",
        price=f"${float(h.loc[t, 'price']):,.2f}",
        price_open=f"${float(h.loc[t, 'price_open']):,.2f}",
        cost=_money(float(h.loc[t, "cost"])),
        value=_money(float(h.loc[t, "value"])),
        gain=_money(float(h.loc[t, "gain"])),
        weight=f"{float(h.loc[t, 'weight']):.1%}",
        total_return=f"{float(h.loc[t, 'total_return']):+.1%}",
        over_limit=float(h.loc[t, "weight"]) > cfg.POLICY["max_weight"],
    ) for t in h.index]


def _view_model(res: AnalysisResult, theme: str = cfg.DEFAULT_THEME) -> dict:
    gain = res.notional - res.cost_basis
    return dict(
        inline_css=_CSS.read_text(encoding="utf-8") + _theme_css(theme),
        inline_plotly=_plotly_js(),
        chart_html=charts.build_all_charts(res, theme),
        n_obs=len(res.returns),
        start_date=res.returns.index.min().strftime("%d %b %Y"),
        end_date=res.returns.index.max().strftime("%d %b %Y"),
        window=res.window,
        notional=_money(res.notional),
        factor_source=res.factor_source,
        factor_is_synthetic=res.factor_is_synthetic,
        breach_count=sum(1 for b in res.breaches if b.breached),
        breaches=[dict(check=b.check, limit=b.limit, observed=b.observed,
                       breached=b.breached, cash=_money(b.cash_at_risk),
                       why=b.why, risk=b.risk, action=b.action,
                       owner=b.owner, due=b.due) for b in res.breaches],
        cards=_cards(res),
        spy_stats=dict(cagr=_pct(res.perf_spy.cagr), vol=_pct(res.perf_spy.ann_vol),
                       sharpe=_num(res.perf_spy.sharpe),
                       mdd=_pct(res.perf_spy.max_drawdown, 1)),
        ff5_rows=_loading_rows(res.ff5), ff5_r2=res.ff5.r_squared,
        ff3_rows=_loading_rows(res.ff3), ff3_r2=res.ff3.r_squared,
        capm_rows=_loading_rows(res.capm),
        capm_alpha=_pct(res.capm.alpha_annualized),
        ff5_alpha=_pct(res.ff5.alpha_annualized),
        holding_rows=_holding_rows(res),
        cost_basis=_money(res.cost_basis),
        portfolio_gain=_money(gain),
        portfolio_gain_pct=f"{gain / res.cost_basis:+.1%}",
        max_weight=f"{cfg.POLICY['max_weight']:.0%}",
    )


def render_tearsheet(res: AnalysisResult, theme: str = cfg.DEFAULT_THEME) -> str:
    """The complete page as one self-contained HTML string."""
    if theme not in cfg.THEMES:
        raise ValueError(f"theme must be one of {cfg.THEMES}, got {theme!r}")
    return _env().get_template("tearsheet.html").render(**_view_model(res, theme))


def write_artifact(res: AnalysisResult, path=None,
                   theme: str = cfg.DEFAULT_THEME) -> pathlib.Path:
    """Write the page to disk as a committable portfolio artifact."""
    path = pathlib.Path(path or cfg.ARTIFACT_HTML)
    path.write_text(render_tearsheet(res, theme), encoding="utf-8")
    return path
