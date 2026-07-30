"""Tests for the ledger figure the portfolio page is anchored to."""
from __future__ import annotations

import pathlib
import re

from portfolio import config as cfg, ledger


def test_cost_basis_matches_the_streamlit_app():
    """The stakes' cost basis is the app's contributed capital. If the app's
    opening trial balance changes and this constant does not, the portfolio's
    cost -- and every gain figure derived from it -- is wrong."""
    src = pathlib.Path(cfg.REPO_ROOT / "streamlit_app.py").read_text()
    m = re.search(r"capital=([0-9_]+)", src)
    assert m, "could not find OPENING['capital'] in streamlit_app.py"
    assert float(m.group(1).replace("_", "")) == cfg.OPENING_CAPITAL
    assert ledger.contributed_capital() == cfg.OPENING_CAPITAL


def test_the_ledger_module_does_not_reimplement_the_income_statement():
    """Guardrail. A duplicate net-income calculation here disagreed with the
    app's by $408k; the fix was to delete it rather than maintain two."""
    src = pathlib.Path(ledger.__file__).read_text()
    for banned in ("net_income", "book_equity", "Cost of Goods Sold"):
        assert banned not in src.split('"""')[2], f"{banned} is back in ledger.py"
