"""Plotly figures for the portfolio tearsheet, as self-contained HTML fragments.

One shared dark theme, ported from the reference project's charts.py, keeps
every chart consistent with the surrounding stylesheet. Plotly's JS is injected
once by render.py rather than per figure, and never from a CDN -- this page has
to work offline.
"""
from __future__ import annotations

import plotly.graph_objects as go

from portfolio import config as cfg
from portfolio.analytics import (AnalysisResult, drawdown_series, load_prices,
                                 position_values, wealth_index)

_PAPER = "rgba(0,0,0,0)"   # panels supply the background, in both themes
_FONT = "Inter, 'Segoe UI', system-ui, sans-serif"
_CONFIG = {"displayModeBar": False, "responsive": True}

# Set by build_all_charts before each render. Module-level rather than threaded
# through every builder because the palette applies uniformly to all of them.
_C = cfg.CHART_COLORS[cfg.DEFAULT_THEME]


def _use_theme(theme: str) -> None:
    global _C, _ACCENT, _ACCENT_2, _DANGER, _WARN, _MUTED, _GRID, _FACTOR_COLORS
    _C = cfg.CHART_COLORS[theme]
    _ACCENT, _ACCENT_2 = _C["accent"], _C["accent_2"]
    _DANGER, _WARN, _MUTED = _C["danger"], _C["warn"], _C["muted"]
    _GRID, _FACTOR_COLORS = _C["grid"], _C["factors"]


def _layout(title: str, height: int = 340) -> dict:
    return dict(
        title=dict(text=title, font=dict(size=15, color=_C["title"]), x=0.01,
                   xanchor="left"),
        template=_C["template"],
        paper_bgcolor=_PAPER, plot_bgcolor=_PAPER,
        font=dict(family=_FONT, color=_MUTED, size=12),
        margin=dict(l=52, r=20, t=44, b=40),
        height=height, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right",
                    x=1.0, bgcolor=_PAPER, font=dict(size=11)),
        xaxis=dict(gridcolor=_GRID, zeroline=False),
        yaxis=dict(gridcolor=_GRID, zeroline=False),
    )


def _fill(hex_colour: str, alpha: float) -> str:
    """A translucent version of a palette colour, for area fills."""
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _html(fig: go.Figure, div_id: str) -> str:
    # include_plotlyjs=False: render.py inlines the library once for the page.
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config=_CONFIG, div_id=div_id)


def build_equity_curve(res: AnalysisResult) -> str:
    port = wealth_index(res.returns["portfolio_return"])
    spy = wealth_index(res.returns["SPY"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=port.index, y=port.values, name="Portfolio",
                             mode="lines", line=dict(color=_ACCENT, width=2.2),
                             fill="tozeroy", fillcolor=_fill(_ACCENT, 0.08)))
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
                             fillcolor=_fill(_DANGER, 0.20)))
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
                             fill="tozeroy", fillcolor=_fill(_WARN, 0.08)))
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


def build_holdings_value(res: AnalysisResult) -> str:
    """Position value per holding over time -- where the concentration comes from."""
    prices = load_prices()
    values = position_values(prices) / 1e6
    order = res.holdings.sort_values("value", ascending=False).index
    palette = [_ACCENT, _ACCENT_2, _WARN, _MUTED]

    fig = go.Figure()
    for colour, ticker in zip(palette, order):
        fig.add_trace(go.Scatter(
            x=values.index, y=values[ticker], name=ticker, mode="lines",
            line=dict(width=0.5, color=colour), stackgroup="one",
            fillcolor=_fill(colour, 0.55),
            hovertemplate=ticker + ": $%{y:.2f}M<extra></extra>"))
    fig.update_layout(**_layout(
        "Position Value by Holding — $M, never rebalanced", height=360))
    fig.update_yaxes(tickprefix="$", ticksuffix="M")
    return _html(fig, "chart-holdings")


def build_all_charts(res: AnalysisResult,
                     theme: str = cfg.DEFAULT_THEME) -> dict[str, str]:
    _use_theme(theme)
    return {
        "equity": build_equity_curve(res),
        "drawdown": build_drawdown(res),
        "rolling_sharpe": build_rolling_sharpe(res),
        "attribution": build_rolling_attribution(res),
        "loadings": build_factor_loadings_bar(res),
        "holdings": build_holdings_value(res),
    }
