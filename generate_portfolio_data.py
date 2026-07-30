#!/usr/bin/env python3
"""Generate the synthetic portfolio datasets for the AI DOF Command Centre.

Meridian Holdings Group is the investor; its portfolio is the four operating
companies it owns. This script models that portfolio.

Run once; the output is committed:

    python3 generate_portfolio_data.py            # write the CSVs
    python3 generate_portfolio_data.py --report   # write, then print realized stats

Everything here is MODELLED and deterministic under ``portfolio.config.SEED``.
Three properties matter and are easy to get wrong:

1. The factor panel is built FIRST and every holding is derived from it
   (``SPY = Mkt-RF + RF``). Generating the holdings independently would make each
   Fama-French loading a regression of one noise series on another.
2. The portfolio is value-weighted across the four stakes, so its drift is a
   property of the positions rather than something imposed on the aggregate.
3. Weights are never rebalanced. Nobody rebalances a holdco's subsidiaries, and
   that is how the largest position runs through the concentration limit.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from portfolio import config as cfg


def trading_days() -> pd.DatetimeIndex:
    """Business days over the sample.

    Holidays are deliberately NOT excluded: the reference project's sample CSV
    contains 2023-07-04 and 2023-12-25, and our file must be interchangeable
    with it.
    """
    idx = pd.bdate_range(start=cfg.START, end=cfg.END)
    idx.name = "date"
    return idx


def build_factor_panel() -> pd.DataFrame:
    """Daily Fama-French style factor panel with realistic vols and premia."""
    rng = np.random.default_rng(cfg.SEED)
    idx = trading_days()
    n = len(idx)
    d = cfg.TRADING_DAYS_PER_YEAR

    data = {}
    for name in cfg.FF5_FACTORS:
        drift = cfg.FACTOR_PREMIUM[name] / d
        data[name] = rng.normal(drift, cfg.FACTOR_VOL[name], size=n)
    data["RF"] = np.full(n, cfg.RF_ANNUAL / d)

    panel = pd.DataFrame(data, index=idx)
    panel.index.name = "date"

    # A six-week market selloff. It belongs in the market factor so the
    # portfolio's drawdown is something it AMPLIFIED through its drifted beta.
    # Putting it in a holding's residual instead would dump the episode into the
    # regression intercept and corrupt the alpha figure.
    shock = ((panel.index >= pd.Timestamp(cfg.SHOCK_START))
             & (panel.index <= pd.Timestamp(cfg.SHOCK_END)))
    panel.loc[shock, "Mkt-RF"] += cfg.SHOCK_DAILY
    return panel


def share_counts() -> dict[str, float]:
    """Shares held per holding, so opening position values match opening weights.

    The total cost basis is the ledger's contributed capital: what the members
    put in is what the stakes cost.
    """
    return {t: (cfg.OPENING_CAPITAL * h["weight"]) / h["price"]
            for t, h in cfg.HOLDINGS.items()}


def build_holdings_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Daily total return for each of MHG's four stakes.

    Every holding is generated from the factor panel with its own loadings, which
    re-rate at REGIME_SPLIT.
    """
    idx = panel.index
    d = cfg.TRADING_DAYS_PER_YEAR
    split = pd.Timestamp(cfg.REGIME_SPLIT)
    factor_keys = (("Mkt-RF", "mkt"), ("SMB", "smb"), ("HML", "hml"),
                   ("RMW", "rmw"), ("CMA", "cma"))
    out = {}

    for i, (ticker, h) in enumerate(cfg.HOLDINGS.items()):
        rng = np.random.default_rng(cfg.SEED + 10 + i)
        r = np.zeros(len(idx))
        for j, ts in enumerate(idx):
            load = h["fy25"] if ts < split else h["fy26"]
            systematic = sum(load[key] * panel[factor].iloc[j]
                             for factor, key in factor_keys)
            idio = rng.normal(0.0, load["idio"] / np.sqrt(d))
            r[j] = h["alpha"] / d + systematic + idio
        # Excess return plus the risk-free rate, less the holdco charge.
        out[ticker] = r + panel["RF"].to_numpy() - cfg.FEE_ANNUAL / d

    df = pd.DataFrame(out, index=idx)
    df.index.name = "date"
    return df


def build_prices(holdings: pd.DataFrame) -> pd.DataFrame:
    """Share price per holding, compounded from its return series."""
    prices = {t: cfg.HOLDINGS[t]["price"] * (1.0 + holdings[t]).cumprod()
              for t in cfg.TICKERS}
    df = pd.DataFrame(prices, index=holdings.index)
    df.index.name = "date"
    return df


def build_portfolio_returns(holdings: pd.DataFrame, prices: pd.DataFrame,
                            panel: pd.DataFrame) -> pd.DataFrame:
    """The portfolio series the tearsheet analyses.

    Value-weighted across the four stakes, using yesterday's weights on today's
    returns, and never rebalanced.
    """
    shares = share_counts()
    values = pd.DataFrame({t: shares[t] * prices[t] for t in cfg.TICKERS},
                          index=holdings.index)
    weights = values.div(values.sum(axis=1), axis=0).shift(1)
    weights.iloc[0] = pd.Series({t: cfg.HOLDINGS[t]["weight"] for t in cfg.TICKERS})
    portfolio = (weights * holdings[cfg.TICKERS]).sum(axis=1)

    spy = panel["Mkt-RF"].to_numpy() + panel["RF"].to_numpy()
    out = pd.DataFrame({"portfolio_return": portfolio.to_numpy(), "SPY": spy},
                       index=holdings.index)
    out.index.name = "date"
    return out


def _write(df: pd.DataFrame, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 6 decimal places, matching the reference sample's formatting.
    df.round(6).to_csv(path, float_format="%.6g")
    print(f"wrote {path.relative_to(cfg.REPO_ROOT)}  ({len(df)} rows)")


def report(panel: pd.DataFrame, returns: pd.DataFrame,
           prices: pd.DataFrame) -> None:
    """Print realized statistics, for the calibration loop."""
    d = cfg.TRADING_DAYS_PER_YEAR
    p = returns["portfolio_return"]
    spy = returns["SPY"]
    wealth = (1.0 + p).cumprod()
    mdd = float((wealth / wealth.cummax() - 1.0).min())
    print("\n-- realized calibration --")
    print(f"  observations      : {len(p)}")
    print(f"  SPY daily sd      : {spy.std(ddof=1):.5f}")
    print(f"  portfolio ann vol : {p.std(ddof=1) * np.sqrt(d):.2%}")
    print(f"  max drawdown      : {mdd:.2%}   (policy limit "
          f"-{cfg.POLICY['max_drawdown']:.0%})")
    print(f"  2-yr total return : {float((1 + p).prod() - 1):+.1%}  "
          f"vs SPY {float((1 + spy).prod() - 1):+.1%}")

    import statsmodels.api as sm
    rf = panel["RF"]
    y = p - rf
    capm = sm.OLS(y, sm.add_constant(pd.DataFrame({"MKT": spy - rf}))).fit()
    ff5 = sm.OLS(y, sm.add_constant(panel[cfg.FF5_FACTORS])).fit()
    print(f"  CAPM alpha (ann)  : {capm.params['const'] * d:+.2%}  "
          f"beta {capm.params['MKT']:.3f}")
    print(f"  FF5 alpha (ann)   : {ff5.params['const'] * d:+.2%}   "
          f"<- net of the {cfg.FEE_ANNUAL:.2%} charge")
    print(f"  FF5 Mkt-RF beta   : {ff5.params['Mkt-RF']:.3f}")

    shares = share_counts()
    values = {t: shares[t] * float(prices[t].iloc[-1]) for t in cfg.TICKERS}
    total = sum(values.values())
    print(f"\n  portfolio value   : ${total/1e6:.2f}M  "
          f"(cost ${cfg.OPENING_CAPITAL/1e6:.2f}M)")
    for t in cfg.TICKERS:
        print(f"    {t}  weight {values[t]/total:6.1%}  "
              f"price ${float(prices[t].iloc[-1]):8.2f}  "
              f"value ${values[t]/1e6:5.2f}M")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true",
                    help="print realized statistics after writing")
    args = ap.parse_args()

    panel = build_factor_panel()
    holdings = build_holdings_returns(panel)
    prices = build_prices(holdings)
    returns = build_portfolio_returns(holdings, prices, panel)

    _write(panel, cfg.FACTORS_CSV)
    _write(returns, cfg.RETURNS_CSV)
    _write(prices, cfg.PRICES_CSV)
    if args.report:
        report(panel, returns, prices)


if __name__ == "__main__":
    main()
