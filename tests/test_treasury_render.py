"""Tests for the treasury chart and HTML rendering layers."""
from __future__ import annotations

import pathlib

import pytest

from treasury import config as cfg

pytestmark = pytest.mark.skipif(
    not cfg.RETURNS_CSV.exists(),
    reason="run `python3 generate_treasury_data.py` first",
)


@pytest.fixture(scope="module")
def analysis():
    from treasury import analytics as an
    returns = an.load_returns(cfg.RETURNS_CSV)
    return an.run_full_analysis(returns, window=cfg.DEFAULT_WINDOW, try_live=False)


def test_run_full_analysis_bundles_everything_the_page_needs(analysis):
    for attr in ("returns", "rf_daily", "perf_portfolio", "perf_spy", "capm",
                 "ff5", "ff3", "rolling_betas", "rolling_sharpe", "breaches",
                 "operating_group", "operating_entities", "factor_source",
                 "factor_is_synthetic", "window"):
        assert hasattr(analysis, attr), attr


def test_charts_are_self_contained_fragments_with_no_cdn(analysis):
    from treasury import charts
    figs = charts.build_all_charts(analysis)
    assert set(figs) == {"equity", "drawdown", "rolling_sharpe", "attribution",
                         "loadings", "operating"}
    for name, html in figs.items():
        assert html.strip(), name
        assert "cdn.plot.ly" not in html, f"{name} must not reach a CDN"
        assert "<div" in html


def test_charts_use_the_reference_dark_palette(analysis):
    from treasury import charts
    figs = charts.build_all_charts(analysis)
    assert "#4ade80" in figs["equity"]      # accent: portfolio
    assert "#60a5fa" in figs["equity"]      # accent-2: benchmark
    assert "#f87171" in figs["drawdown"]    # danger: drawdowns


def test_attribution_chart_marks_the_policy_ceiling(analysis):
    from treasury import charts
    html = charts.build_all_charts(analysis)["attribution"]
    # The mandate ceiling must be drawn, or the drift has no reference line.
    assert "mandate" in html.lower()
