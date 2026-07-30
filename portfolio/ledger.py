"""Cash figures read from the committed ledger.

The portfolio is a MODELLED overlay -- there is no investments line in
the ledger -- so its size has to be justified against cash that actually exists.
An earlier version hardcoded $9.0M, which was larger than the group's entire cash
balance ($6.14M at 30 Jun 2026) and therefore impossible. Everything here is
derived instead.

The cash-balance logic mirrors ``streamlit_app.balance_sheet``: opening cash plus
cumulative activity on account 1000. A test asserts the opening constant here
still matches the one in the app.
"""
from __future__ import annotations

import pandas as pd

from portfolio import config as cfg


def _postings() -> pd.DataFrame:
    """Every posting that moves cash (account 1000), by month.

    Invoices do not touch cash (they debit receivables), so only bank
    transactions and journal entries matter.
    """
    frames = []
    for name, acct_col, amt_col in (
        ("Bank_Data.csv", None, "AmountUSD"),
        ("Journal_Entries.csv", "AccountNum", "AmountUSD"),
    ):
        df = pd.read_csv(cfg.LEDGER_DIR / name)
        df[amt_col] = pd.to_numeric(df[amt_col], errors="coerce").fillna(0.0)
        if acct_col is None:
            # Bank rows debit cash by their full amount.
            frames.append(pd.DataFrame({"Period": df["Period"], "amount": df[amt_col]}))
        else:
            cash_rows = df[df[acct_col].astype(str) == "1000"]
            frames.append(pd.DataFrame({"Period": cash_rows["Period"],
                                        "amount": cash_rows[amt_col]}))
    return pd.concat(frames, ignore_index=True)


def cash_by_month() -> pd.Series:
    """Closing cash balance for each month in the ledger."""
    moves = _postings().groupby("Period")["amount"].sum().sort_index()
    return cfg.OPENING_CASH + moves.cumsum()


def monthly_cash_burn() -> float:
    """Average monthly cash operating cost over the most recent half-year.

    Depreciation is excluded: it is a non-cash charge and does not consume the
    operating buffer.
    """
    coa = pd.read_csv(cfg.LEDGER_DIR / "Chart_of_Accounts.csv", dtype=str)
    classification = dict(zip(coa["AccountNumber"], coa["Classification"]))

    je = pd.read_csv(cfg.LEDGER_DIR / "Journal_Entries.csv")
    je["AmountUSD"] = pd.to_numeric(je["AmountUSD"], errors="coerce").fillna(0.0)
    bank = pd.read_csv(cfg.LEDGER_DIR / "Bank_Data.csv")
    bank["AmountUSD"] = pd.to_numeric(bank["AmountUSD"], errors="coerce").fillna(0.0)

    recent = [m for m in sorted(set(je["Period"]) | set(bank["Period"]))][-6:]

    # NOTE: the ledger's Classification values are "Expense" and "Cost of Goods
    # Sold" -- singular. Spelling this "Expenses" matched none of the 26 expense
    # accounts and understated the burn by a third, silently.
    OPERATING_CLASSES = ("Expense", "Cost of Goods Sold")
    DEPRECIATION = "6700"          # non-cash, does not consume the buffer

    def is_operating(acct: str) -> bool:
        return (classification.get(str(acct), "") in OPERATING_CLASSES
                and str(acct) != DEPRECIATION)

    total = 0.0
    total += je[je["Period"].isin(recent)
                & je["AccountNum"].astype(str).map(is_operating)]["AmountUSD"].sum()
    total += -bank[bank["Period"].isin(recent)
                   & bank["CategoryAccountNum"].astype(str).map(is_operating)
                   ]["AmountUSD"].sum()
    return abs(total) / len(recent)


def investable_cash(buffer_months: int | None = None) -> float:
    """Cash the group could reasonably place in a portfolio.

    Closing cash less an operating buffer. The buffer is the assumption that
    matters: at the conventional three months Meridian has essentially no
    investable excess, which is itself worth a CFO's attention.
    """
    months = cfg.BUFFER_MONTHS if buffer_months is None else buffer_months
    closing = float(cash_by_month().iloc[-1])
    return max(0.0, closing - monthly_cash_burn() * months)
