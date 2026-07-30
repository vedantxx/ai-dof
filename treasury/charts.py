"""Plotly figures for the treasury tearsheet, as self-contained HTML fragments.

One shared dark theme, ported from the reference project's charts.py, keeps
every chart consistent with the surrounding stylesheet. Plotly's JS is injected
once by render.py rather than per figure, and never from a CDN -- this page has
to work offline.
"""
from __future__ import annotations

import plotly.graph_objects as go

from treasury import config as cfg
from treasury.analytics import AnalysisResult, drawdown_series, wealth_index

_ACCENT = "#4ade80"       # portfolio
_ACCENT_2 = "#60a5fa"     # benchmark
_DANGER = "#f87171"       # drawdowns and breaches
_WARN = "#fbbf24"
_MUTED = "#94a3b8"
_GRID = "rgba(148,163,184,0.12)"
_PAPER = "rgba(0,0,0,0)"
_FONT = "Inter, 'Segoe UI', system-ui, sans-serif"

_FACTOR_COLORS = {
    "Mkt-RF": "#60a5fa", "SMB": "#4ade80", "HML": "#fbbf24",
    "RMW": "#c084fc", "CMA": "#f472b6",
}
_CONFIG = {"displayModeBar": False, "responsive": True}


def _layout(title: str, height: int = 340) -> dict:
    return dict(
        title=dict(text=title, font=dict(size=15, color="#e2e8f0"), x=0.01,
                   xanchor="left"),
        template="plotly_dark",
        paper_bgcolor=_PAPER, plot_bgcolor=_PAPER,
        font=dict(family=_FONT, color=_MUTED, size=12),
        margin=dict(l=52, r=20, t=44, b=40),
        height=height, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right",
                    x=1.0, bgcolor=_PAPER, font=dict(size=11)),
        xaxis=dict(gridcolor=_GRID, zeroline=False),
        yaxis=dict(gridcolor=_GRID, zeroline=False),
    )


def _html(fig: go.Figure, div_id: str) -> str:
    # include_plotlyjs=False: render.py inlines the library once for the page.
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config=_CONFIG, div_id=div_id)


def build_equity_curve(res: AnalysisResult) -> str:
    port = wealth_index(res.returns["portfolio_return"])
    spy = wealth_index(res.returns["SPY"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=port.index, y=port.values, name="Treasury portfolio",
                             mode="lines", line=dict(color=_ACCENT, width=2.2),
                             fill="tozeroy", fillcolor="rgba(74,222,128,0.08)"))
    fig.add_trace(go.Scatter(x=spy.index, y=spy.values, name="SPY", mode="lines",
                             line=dict(color=_ACCENT_2, width=1.8, dash="dot")))
    fig.update_layout(**_layout("Equity Curve — Growth of $1"))
    # The reference fills to zero, which squashes a 1.0->1.2 range into the top
    # fifth of the panel. Keep the fill, but bound the axis to the data so the
    # drawdown episode is actually legible.
    lo = float(min(port.min(), spy.min()))
    hi = float(max(port.max(), spy.max()))
    pad = (hi - lo) * 0.12 or 0.02
    fig.update_yaxes(tickprefix="$", range=[lo - pad, hi + pad])
    return _html(fig, "chart-equity")


def build_drawdown(res: AnalysisResult) -> str:
    dd = drawdown_series(res.returns["portfolio_return"]) * 100.0
    limit = -cfg.POLICY["max_drawdown"] * 100.0
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dd.index, y=dd.values, name="Drawdown", mode="lines",
                             line=dict(color=_DANGER, width=1.4), fill="tozeroy",
                             fillcolor="rgba(248,113,113,0.20)"))
    fig.add_hline(y=limit, line=dict(color=_WARN, width=1, dash="dash"),
                  annotation_text=f"policy limit {limit:.0f}%",
                  annotation_font=dict(color=_WARN, size=10))
    fig.update_layout(**_layout("Underwater Plot — Drawdown from Peak"))
    fig.update_yaxes(ticksuffix="%")
    return _html(fig, "chart-drawdown")


def build_rolling_sharpe(res: AnalysisResult) -> str:
    rs = res.rolling_sharpe.dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rs.index, y=rs.values, name="Rolling Sharpe",
                             mode="lines", line=dict(color=_WARN, width=1.8),
                             fill="tozeroy", fillcolor="rgba(251,191,36,0.08)"))
    fig.add_hline(y=1.0, line=dict(color="rgba(148,163,184,0.5)", width=1, dash="dash"))
    fig.update_layout(**_layout(f"Rolling Sharpe Ratio ({res.window}-day window)"))
    return _html(fig, "chart-rollsharpe")


def build_rolling_attribution(res: AnalysisResult) -> str:
    """Rolling factor betas -- the chart that catches the mandate drift."""
    betas = res.rolling_betas
    fig = go.Figure()
    for col in betas.columns:
        fig.add_trace(go.Scatter(x=betas.index, y=betas[col], name=col, mode="lines",
                                 line=dict(color=_FACTOR_COLORS.get(col, _MUTED),
                                           width=1.8)))
    fig.add_hline(y=0.0, line=dict(color="rgba(148,163,184,0.4)", width=1))
    fig.add_hline(y=cfg.POLICY["max_beta"],
                  line=dict(color=_DANGER, width=1.2, dash="dash"),
                  annotation_text=f"mandate beta ceiling {cfg.POLICY['max_beta']:.1f}",
                  annotation_font=dict(color=_DANGER, size=10))
    fig.update_layout(**_layout(
        f"Rolling Fama-French Factor Betas ({res.window}-day window)", height=390))
    return _html(fig, "chart-attribution")


def build_factor_loadings_bar(res: AnalysisResult) -> str:
    loadings = [l for l in res.ff5.loadings if l.name != "Alpha"]
    names = [l.name for l in loadings]
    coefs = [l.coef for l in loadings]
    fig = go.Figure(go.Bar(
        x=names, y=coefs,
        marker=dict(color=[_FACTOR_COLORS.get(n, _MUTED) for n in names],
                    opacity=[1.0 if l.significant else 0.35 for l in loadings]),
        text=[f"{c:+.2f}" for c in coefs], textposition="outside",
        hovertext=[f"t={l.tstat:.2f}, p={l.pvalue:.3f}" for l in loadings]))
    fig.add_hline(y=0.0, line=dict(color="rgba(148,163,184,0.4)", width=1))
    fig.update_layout(**_layout("Fama-French 5-Factor Loadings (β)"))
    return _html(fig, "chart-loadings")


def build_operating_loadings(res: AnalysisResult) -> str:
    """Per-entity revenue sensitivity to the freight cycle.

    One series, not three: the per-entity multivariate coefficients on the other
    two macro factors are not identified well enough at 59 observations to put on
    a chart. See operating_factor_model.
    """
    ent = res.operating_entities.sort_values("freight_beta", ascending=False)
    betas = ent["freight_beta"].astype(float)
    # Every entity sits above 1.0, so a 1.0 threshold colours them all the same.
    # Split on 1.25 instead: that is where the freight-exposed pair separates
    # from the contract-based pair.
    fig = go.Figure(go.Bar(
        x=list(ent.index), y=betas.values,
        marker_color=[_ACCENT if b >= 1.25 else _ACCENT_2 for b in betas],
        text=[f"{b:.2f}" for b in betas], textposition="outside",
        hovertext=[f"R²={float(ent.loc[e, 'r_squared']):.2f}" for e in ent.index]))
    fig.add_hline(y=1.0, line=dict(color="rgba(148,163,184,0.45)", width=1,
                                   dash="dash"),
                  annotation_text="moves 1:1 with the freight cycle",
                  annotation_position="bottom left",
                  annotation_font=dict(color=_MUTED, size=10))
    fig.update_layout(**_layout(
        "Revenue Beta to the Freight Cycle, by Entity", height=360))
    return _html(fig, "chart-operating")


def build_all_charts(res: AnalysisResult) -> dict[str, str]:
    return {
        "equity": build_equity_curve(res),
        "drawdown": build_drawdown(res),
        "rolling_sharpe": build_rolling_sharpe(res),
        "attribution": build_rolling_attribution(res),
        "loadings": build_factor_loadings_bar(res),
        "operating": build_operating_loadings(res),
    }
