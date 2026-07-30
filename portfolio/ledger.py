"""The one ledger figure the portfolio page depends on.

Meridian Holdings Group's stakes are not on the balance sheet as an investments
line -- the ledger records the operating companies' own trading. What it does
record is what the members put in, and that is the cost basis of the four
stakes.

This module deliberately does NOT recompute net income or book equity. A first
attempt produced $20.62M against the app's $21.03M because it duplicated
`streamlit_app.income_statement` imperfectly. Two implementations of the same
number is how you end up reporting the wrong one, so anything the app already
computes stays in the app.
"""
from __future__ import annotations

from portfolio import config as cfg


def contributed_capital() -> float:
    """What the members put in -- the cost basis of the four stakes.

    Mirrors ``streamlit_app.OPENING["capital"]``; a test ties the two together.
    """
    return cfg.OPENING_CAPITAL
