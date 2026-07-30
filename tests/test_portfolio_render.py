"""Tests for the portfolio chart and HTML rendering layers."""
from __future__ import annotations

import pathlib

import pytest

from portfolio import config as cfg

pytestmark = pytest.mark.skipif(
    not cfg.RETURNS_CSV.exists(),
    reason="run `python3 generate_portfolio_data.py` first",
)


@pytest.fixture(scope="module")
def analysis():
    from portfolio import analytics as an
    returns = an.load_returns(cfg.RETURNS_CSV)
    return an.run_full_analysis(returns, window=cfg.DEFAULT_WINDOW, try_live=False)


def test_run_full_analysis_bundles_everything_the_page_needs(analysis):
    for attr in ("returns", "rf_daily", "perf_portfolio", "perf_spy", "capm",
                 "ff5", "ff3", "rolling_betas", "rolling_sharpe", "breaches",
                 "notional", "holdings", "cost_basis", "factor_source",
                 "factor_is_synthetic", "window"):
        assert hasattr(analysis, attr), attr


def test_charts_are_self_contained_fragments_with_no_cdn(analysis):
    from portfolio import charts
    figs = charts.build_all_charts(analysis)
    assert set(figs) == {"equity", "drawdown", "rolling_sharpe", "attribution",
                         "loadings", "holdings"}
    for name, html in figs.items():
        assert html.strip(), name
        assert "cdn.plot.ly" not in html, f"{name} must not reach a CDN"
        assert "<div" in html


def test_charts_use_the_reference_dark_palette(analysis):
    from portfolio import charts
    figs = charts.build_all_charts(analysis)
    assert "#4ade80" in figs["equity"]      # accent: portfolio
    assert "#60a5fa" in figs["equity"]      # accent-2: benchmark
    assert "#f87171" in figs["drawdown"]    # danger: drawdowns


def test_attribution_chart_marks_the_policy_ceiling(analysis):
    from portfolio import charts
    html = charts.build_all_charts(analysis)["attribution"]
    # The mandate ceiling must be drawn, or the drift has no reference line.
    assert "mandate" in html.lower()


# ---------------------------------------------------------------- renderer -- #
@pytest.fixture(scope="module")
def page(analysis) -> str:
    from portfolio import render
    return render.render_tearsheet(analysis)


def test_page_is_self_contained_and_offline(page):
    """No external resource may be LOADED.

    Substring checks are the wrong instrument here: the inlined Plotly bundle
    contains 'cdn.plot.ly' as its default topojsonURL config value, which is only
    ever fetched for choropleth maps this page does not draw. What matters is
    that no tag points off-host.
    """
    import re

    assert page.lstrip().startswith("<!DOCTYPE html>")

    external_src = re.findall(r'<(?:script|img|iframe)[^>]+src\s*=\s*["\']https?://',
                              page, re.IGNORECASE)
    assert not external_src, f"external src refs: {external_src}"

    external_href = re.findall(r'<link[^>]+href\s*=\s*["\']https?://', page,
                               re.IGNORECASE)
    assert not external_href, f"external stylesheet refs: {external_href}"

    assert "@import" not in page, "no CSS @import (would fetch off-host)"
    assert "fonts.googleapis.com" not in page, "webfonts must be system stacks"

    # And the library really is embedded rather than referenced.
    assert "Plotly.newPlot" in page
    assert "<script>" in page


def test_inlined_css_and_js_are_not_html_escaped(page):
    """Autoescaping the <style> and <script> payloads renders every quote as
    &#34;, which silently breaks the font stacks and every chart. Caught only by
    screenshotting the page, so it is pinned here."""
    style = page[page.index("<style>"):page.index("</style>")]
    assert "&#34;" not in style and "&quot;" not in style
    assert '"Inter"' in style, "font stack must survive intact"

    # Plotly's own source contains the literal string "&#34;" in its entity
    # handling, so scanning the bundle for entities gives false positives. Test
    # the property that matters instead: its UMD wrapper's quotes are real, which
    # is exactly what escaping destroys.
    assert 'typeof module === "object"' in page
    assert "typeof module === &#34;object&#34;" not in page


def test_every_chart_div_has_a_matching_plot_call(page):
    """A panel can render as an empty box while the page looks structurally
    fine -- assert each chart div is actually plotted into. This is the failure
    the escaping bug produced, and only a screenshot revealed it."""
    import re

    div_ids = sorted(set(re.findall(r'<div id="(chart-[^"]+)"', page)))
    plotted = sorted(set(re.findall(r'Plotly\.newPlot\(\s*"([\w-]+)"', page)))
    assert len(div_ids) == 6, div_ids
    assert div_ids == plotted, f"divs {div_ids} vs plotted {plotted}"


def test_page_carries_the_reference_layout_classes(page):
    for cls in ("results-head", "results-title", "cards-grid", "metric-card",
                "charts-grid", "panel-wide", "benchmark-panel", "factor-table",
                "divider-row", "tables-grid", "bg-grid", "topbar"):
        assert cls in page, cls


def test_page_declares_the_reference_palette(page):
    for colour in ("#0a0e17", "rgba(20, 27, 45, 0.72)", "#4ade80", "#60a5fa",
                   "#f87171", "#fbbf24"):
        assert colour in page, colour


def test_page_labels_the_modelled_factor_source(page):
    """Honesty requirement: modelled factors must never pass as market data."""
    assert "banner-warn" in page
    assert "MODELLED" in page


def test_page_reports_all_three_policy_breaches_with_owners(page, analysis):
    assert "banner-danger" in page
    assert "3 breaches" in page.lower()
    for b in analysis.breaches:
        assert b.check in page
        assert b.owner in page
        assert b.due in page


def test_page_includes_both_factor_tables_and_the_holdings_card(page):
    assert "Fama-French 5-Factor" in page
    assert "Fama-French 3-Factor" in page
    assert "CAPM" in page
    assert "Portfolio Companies" in page
    import html

    for ticker, h in cfg.HOLDINGS.items():
        assert ticker in page
        assert h["name"] in page
        # Autoescaping renders "&" as "&amp;" -- compare what the page holds.
        assert html.escape(h["business"]) in page


def test_the_page_no_longer_carries_the_operating_factor_section(page):
    """Dropped deliberately: it regressed the same four companies' revenue from
    the other direction, which is the portfolio itself."""
    assert "Operating Factor Model" not in page
    assert "freight_rate_index" not in page


def test_holdings_card_flags_the_position_over_the_limit(page, analysis):
    over = [t for t in analysis.holdings.index
            if float(analysis.holdings.loc[t, "weight"]) > cfg.POLICY["max_weight"]]
    assert over, "the concentration finding needs a position over the limit"
    assert "weight-over" in page


def test_holdings_card_states_cost_and_mark(page, analysis):
    from portfolio.analytics import _money
    assert _money(analysis.cost_basis) in page
    assert _money(analysis.notional) in page


def test_page_states_the_observation_count_and_date_range(page, analysis):
    assert str(len(analysis.returns)) in page
    assert "2024" in page and "2026" in page


def test_write_artifact_produces_a_committable_file(analysis, tmp_path):
    from portfolio import render
    out = render.write_artifact(analysis, tmp_path / "tearsheet.html")
    assert out.exists()
    assert out.stat().st_size > 500_000, "Plotly is inlined, so expect a large file"


# ------------------------------------------------------------------ themes -- #
def test_dark_is_the_default_and_leaves_the_stylesheet_alone(analysis):
    from portfolio import render
    page = render.render_tearsheet(analysis)
    assert "--bg: #0a0e17" in page
    assert "--bg:#f6f8fb" not in page, "no light override in the default theme"


def test_light_theme_overrides_the_root_variables(analysis):
    from portfolio import render
    page = render.render_tearsheet(analysis, theme="light")
    # The dark declarations stay (one stylesheet); the override wins by order.
    assert "--bg: #0a0e17" in page
    assert "--bg:#f6f8fb" in page
    assert page.index("--bg: #0a0e17") < page.index("--bg:#f6f8fb"), \
        "the light override must come after the dark declaration to win"


def test_light_theme_recolours_the_charts(analysis):
    from portfolio import charts
    light = charts.build_all_charts(analysis, "light")
    assert "#0F6B4F" in light["equity"], "light accent (the app's teal)"
    assert "#4ade80" not in light["equity"], "dark accent must not leak through"
    # Restore the module palette so later tests see the default.
    charts.build_all_charts(analysis, "dark")


def test_render_rejects_an_unknown_theme(analysis):
    from portfolio import render
    with pytest.raises(ValueError, match="theme must be one of"):
        render.render_tearsheet(analysis, theme="solarized")
