"""Render the treasury tearsheet to one self-contained HTML page.

The stylesheet and Plotly's JS are inlined, so the output works offline, in an
email client and in print -- the same constraint the CFO review dashboard in this
repo is built to. This module formats and assembles only; every number arrives
already computed on an AnalysisResult.
"""
from __future__ import annotations

import pathlib

from jinja2 import Environment, FileSystemLoader, select_autoescape

from treasury import charts, config as cfg
from treasury.analytics import AnalysisResult, _money

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


def _view_model(res: AnalysisResult) -> dict:
    ent = res.operating_entities
    betas = ent["freight_beta"].astype(float).sort_values(ascending=False)
    exposed = ", ".join(betas.index[:2])
    defensive = ", ".join(betas.index[2:])
    return dict(
        inline_css=_CSS.read_text(encoding="utf-8"),
        inline_plotly=_plotly_js(),
        chart_html=charts.build_all_charts(res),
        n_obs=len(res.returns),
        start_date=res.returns.index.min().strftime("%d %b %Y"),
        end_date=res.returns.index.max().strftime("%d %b %Y"),
        window=res.window,
        notional=_money(cfg.PORTFOLIO_NOTIONAL),
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
        operating_rows=_loading_rows(res.operating_group),
        operating_r2=res.operating_group.r_squared,
        operating_n=res.operating_group.nobs,
        operating_actual_n=res.operating_actual_n,
        entity_rows=[dict(entity=e,
                          freight=_num(float(ent.loc[e, "freight_beta"]), 2),
                          tstat=_num(float(ent.loc[e, "tstat"]), 2),
                          r2=_num(float(ent.loc[e, "r_squared"]), 3))
                     for e in ent.index],
        operating_note=(
            f"{exposed} amplify the freight cycle at a beta near "
            f"{betas.iloc[:2].mean():.1f}; {defensive} sit near 1.0. The top two are "
            f"within {abs(betas.iloc[0] - betas.iloc[1]):.2f} of each other and are not "
            f"separable — a downturn in spot rates lands on both first."),
    )


def render_tearsheet(res: AnalysisResult) -> str:
    """The complete page as one self-contained HTML string."""
    return _env().get_template("tearsheet.html").render(**_view_model(res))


def write_artifact(res: AnalysisResult, path=None) -> pathlib.Path:
    """Write the page to disk as a committable portfolio artifact."""
    path = pathlib.Path(path or cfg.ARTIFACT_HTML)
    path.write_text(render_tearsheet(res), encoding="utf-8")
    return path
