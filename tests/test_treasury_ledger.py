"""Tests for the ledger-derived cash figures that size every policy breach."""
from __future__ import annotations

import pathlib
import re

import pandas as pd
import pytest

from treasury import config as cfg, ledger


def test_opening_cash_matches_the_streamlit_app():
    """treasury.ledger mirrors streamlit_app's cash logic. If the app's opening
    trial balance changes and this constant does not, every breach on the
    tearsheet is sized against a stale cash position."""
    src = pathlib.Path(cfg.REPO_ROOT / "streamlit_app.py").read_text()
    m = re.search(r"OPENING\s*=\s*dict\(cash=([0-9_]+)", src)
    assert m, "could not find OPENING['cash'] in streamlit_app.py"
    assert float(m.group(1).replace("_", "")) == cfg.OPENING_CASH


def test_closing_cash_ties_to_the_balance_sheet():
    # The app's balance sheet reports $6,140,706 of cash at 30 Jun 2026.
    closing = float(ledger.cash_by_month().iloc[-1])
    assert closing == pytest.approx(6_140_706, abs=1.0)


def test_cash_declines_across_the_two_years(): 
    cash = ledger.cash_by_month()
    assert len(cash) == 24
    assert cash.iloc[0] > cash.iloc[-1], "the group is burning cash"


def test_operating_accounts_are_actually_matched():
    """Regression test for a real bug: the filter was written against the
    classification 'Expenses' when the ledger says 'Expense', so it matched none
    of the 26 expense accounts and understated the burn by a third."""
    coa = pd.read_csv(cfg.LEDGER_DIR / "Chart_of_Accounts.csv", dtype=str)
    matched = coa[coa["Classification"].isin(("Expense", "Cost of Goods Sold"))]
    assert len(matched) >= 35, f"only {len(matched)} operating accounts matched"


def test_monthly_burn_is_consistent_with_the_income_statement():
    # H1-FY2026 cash opex plus cost of services runs about $2.07M/month.
    assert 1.8e6 <= ledger.monthly_cash_burn() <= 2.4e6


def test_investable_cash_cannot_exceed_the_cash_that_exists():
    closing = float(ledger.cash_by_month().iloc[-1])
    assert 0 < ledger.investable_cash() < closing


def test_a_conventional_three_month_buffer_leaves_nothing_to_invest():
    """Worth pinning: it is the honest finding behind the portfolio's size."""
    assert ledger.investable_cash(3) == 0.0
    assert ledger.investable_cash(2) > 1.0e6
