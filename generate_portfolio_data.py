#!/usr/bin/env python3
"""Generate the synthetic portfolio datasets for the AI DOF Command Centre.

Run once; the output is committed:

    python3 generate_portfolio_data.py            # write the CSVs
    python3 generate_portfolio_data.py --report   # write, then print realized stats

Everything here is MODELLED and deterministic under ``portfolio.config.SEED``.
Two properties matter and are easy to get wrong:

1. The factor panel is built FIRST and both SPY and the portfolio are derived
   from it (``SPY = Mkt-RF + RF``). Generating the portfolio independently would
   make every Fama-French loading a regression of one noise series on another.
2. Returns are written NET of the management fee, matching how a custodian
   statement reads. Gross figures are recovered by adding the fee back.
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
    # Putting it in the portfolio's residual instead would dump the whole
    # episode into the regression intercept and wreck the alpha finding.
    shock = ((panel.index >= pd.Timestamp(cfg.SHOCK_START))
             & (panel.index <= pd.Timestamp(cfg.SHOCK_END)))
    panel.loc[shock, "Mkt-RF"] += cfg.SHOCK_DAILY
    return panel


def build_portfolio_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Portfolio and benchmark returns generated from the factor panel.

    The portfolio is a two-regime factor bet: defensive and value-tilted through
    2025, then rotating into high-beta small-cap growth from 2026-01. Full-period
    beta lands inside the policy limit, so only the rolling window exposes the
    drift -- which is the finding the page exists to surface.
    """
    rng = np.random.default_rng(cfg.SEED + 1)
    idx = panel.index
    d = cfg.TRADING_DAYS_PER_YEAR
    split = pd.Timestamp(cfg.REGIME_SPLIT)

    excess = np.zeros(len(idx))
    for i, ts in enumerate(idx):
        r = cfg.REGIMES["FY2025"] if ts < split else cfg.REGIMES["FY2026"]
        loadings = {"Mkt-RF": r["mkt"], "SMB": r["smb"], "HML": r["hml"],
                    "RMW": r["rmw"], "CMA": r["cma"]}
        systematic = sum(loadings[f] * panel[f].iloc[i] for f in cfg.FF5_FACTORS)
        idio = rng.normal(0.0, r["idio"] / np.sqrt(d))
        excess[i] = r["alpha"] / d + systematic + idio

    # NOTE: the drawdown episode is not applied here. It lives in the panel's
    # Mkt-RF series, so the portfolio inherits it through its beta -- see
    # build_factor_panel.

    # Net of fees, and back to total returns.
    portfolio = excess + panel["RF"].to_numpy() - cfg.FEE_ANNUAL / d
    spy = panel["Mkt-RF"].to_numpy() + panel["RF"].to_numpy()

    out = pd.DataFrame({"portfolio_return": portfolio, "SPY": spy}, index=idx)
    out.index.name = "date"
    return out


def ledger_monthly_revenue() -> pd.DataFrame:
    """ACTUAL monthly revenue per entity, from the committed ledger.

    Invoices.csv carries a monthly ``Period`` (2024-07 .. 2026-06) and an
    ``Entity`` column, so this half of the operating panel needs no modelling
    at all.
    """
    inv = pd.read_csv(cfg.LEDGER_DIR / "Invoices.csv")
    inv["TotalAmtUSD"] = pd.to_numeric(inv["TotalAmtUSD"], errors="coerce").fillna(0.0)
    wide = (inv.pivot_table(index="Period", columns="Entity",
                            values="TotalAmtUSD", aggfunc="sum")
            .reindex(columns=cfg.OPERATING_ENTITIES)
            .fillna(0.0)
            .sort_index())
    wide["GROUP"] = wide.sum(axis=1)
    wide.index.name = "month"
    return wide


def build_operating_panel() -> pd.DataFrame:
    """Monthly revenue growth and freight-market factors, 60 months.

    Revenue for the overlap with the ledger is ACTUAL. The factors are the
    MODELLED quantity throughout, and the direction of construction matters:

    * Over the ledger window the freight index is derived FROM observed group
      revenue growth. Actual revenue cannot load on an invented exogenous
      series -- pooling the two produced an insignificant freight coefficient
      (p = 0.085, R² = 0.13) because the real variance simply swamped the
      invented signal.
    * Each entity's sensitivity to that index is then MEASURED over the ledger
      window, and those measured betas generate the pre-history. So the whole
      59-month sample is internally coherent, and "which entity is most
      cyclical" is a property of Meridian's actual revenue rather than an
      assumption baked in here.
    """
    rng = np.random.default_rng(cfg.SEED + 2)
    months = pd.period_range(cfg.OPERATING_START, cfg.LEDGER_END, freq="M")
    n = len(months)
    keys = [str(m) for m in months]

    ledger = ledger_monthly_revenue()
    ledger_growth = ledger.pct_change()
    actual_keys = [k for k in keys
                   if k in ledger_growth.index
                   and not ledger_growth.loc[k].isna().all()]

    # --- 1. The freight cycle. Persistent (freight rates are autocorrelated,
    # not white noise) over the pre-history; derived from observed revenue over
    # the ledger window.
    freight = np.zeros(n)
    for i in range(1, n):
        freight[i] = 0.55 * freight[i - 1] + rng.normal(0.0, 0.028)

    g_actual = ledger_growth.loc[actual_keys, "GROUP"].astype(float)
    freight_actual = ((g_actual - g_actual.mean()) / cfg.REVENUE_FREIGHT_BETA
                      + rng.normal(0.0, cfg.FREIGHT_NOISE, len(g_actual)))
    for k, v in zip(actual_keys, freight_actual):
        freight[keys.index(k)] = float(v)

    diesel = 0.45 * freight + rng.normal(0.0, 0.030, n)
    # Only mildly tied to freight: at 0.35 the collinearity with the freight
    # index scrambled the multivariate partial coefficients, producing entity
    # loadings on industrial production of +2.0 and -1.0 that were artifacts.
    indpro = 0.20 * freight + rng.normal(0.0015, 0.008, n)
    freight_by_key = dict(zip(keys, freight))

    # --- 2. Measure each entity's freight sensitivity on the ACTUAL window.
    measured = {}
    fa = np.asarray([freight_by_key[k] for k in actual_keys])
    for e in cfg.OPERATING_ENTITIES:
        ea = ledger_growth.loc[actual_keys, e].astype(float).to_numpy()
        # Simple univariate slope; the pre-history only needs the magnitude.
        measured[e] = float(np.cov(ea, fa, ddof=1)[0, 1] / np.var(fa, ddof=1))

    rows = []
    for i, key in enumerate(keys):
        actual = key in actual_keys
        row = {"month": key, "is_actual": int(actual),
               "freight_rate_index": freight[i], "diesel_price": diesel[i],
               "industrial_production": indpro[i]}
        for e in cfg.OPERATING_ENTITIES:
            if actual:
                row[f"{e}_growth"] = float(ledger_growth.loc[key, e])
            else:
                beta = measured[e]
                # Every macro sensitivity scales with the entity's own beta.
                # A shared indpro term made the entities differ on one factor
                # but not the others, which distorted the partial coefficients.
                row[f"{e}_growth"] = float(
                    0.004 + beta * freight[i] - 0.20 * beta * diesel[i]
                    + 0.55 * beta * indpro[i] + rng.normal(0.0, cfg.OPERATING_IDIO)
                )
        rows.append(row)

    panel = pd.DataFrame(rows)
    # Group growth is revenue-weighted, so it is not the mean of entity growths.
    ledger_totals = ledger[cfg.OPERATING_ENTITIES].sum()
    weights = ledger_totals / ledger_totals.sum()
    modelled_group = sum(panel[f"{e}_growth"] * weights[e]
                         for e in cfg.OPERATING_ENTITIES)
    panel["group_growth"] = modelled_group
    is_actual = panel["is_actual"] == 1
    actual_group = (panel.loc[is_actual, "month"]
                    .map(ledger_growth["GROUP"]).astype(float))
    panel.loc[is_actual, "group_growth"] = actual_group.values

    # The first month has no prior month, so no growth rate exists for it.
    panel = panel.iloc[1:].reset_index(drop=True)
    cols = (["month", "is_actual"]
            + [f"{e}_growth" for e in cfg.OPERATING_ENTITIES]
            + ["group_growth"] + cfg.OPERATING_FACTORS)
    return panel[cols]


def _write(df: pd.DataFrame, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 6 decimal places, matching the reference sample's formatting.
    df.round(6).to_csv(path, float_format="%.6g")
    print(f"wrote {path.relative_to(cfg.REPO_ROOT)}  ({len(df)} rows)")


def report(panel: pd.DataFrame, returns: pd.DataFrame) -> None:
    """Print realized statistics, for the calibration loop in the plan."""
    d = cfg.TRADING_DAYS_PER_YEAR
    p = returns["portfolio_return"]
    wealth = (1.0 + p).cumprod()
    mdd = float((wealth / wealth.cummax() - 1.0).min())
    print("\n-- realized calibration --")
    print(f"  observations      : {len(p)}")
    print(f"  SPY daily sd      : {returns['SPY'].std(ddof=1):.5f}")
    print(f"  portfolio daily sd: {p.std(ddof=1):.5f}")
    print(f"  portfolio ann vol : {p.std(ddof=1) * np.sqrt(d):.2%}")
    print(f"  max drawdown      : {mdd:.2%}   (policy limit "
          f"-{cfg.POLICY['max_drawdown']:.0%})")

    import statsmodels.api as sm
    rf = panel["RF"]
    y = p - rf
    # CAPM: one factor, so the style premia leak into the intercept.
    x1 = sm.add_constant(pd.DataFrame({"MKT": returns["SPY"] - rf}))
    capm = sm.OLS(y, x1).fit()
    # FF5: controls for them, so the intercept is closer to true alpha.
    x5 = sm.add_constant(panel[cfg.FF5_FACTORS])
    ff5 = sm.OLS(y, x5).fit()
    print(f"  CAPM alpha (ann)  : {capm.params['const'] * d:+.2%}  "
          f"beta {capm.params['MKT']:.3f}")
    print(f"  FF5 alpha (ann)   : {ff5.params['const'] * d:+.2%}   "
          f"<- net of the {cfg.FEE_ANNUAL:.2%} fee")
    print(f"  FF5 Mkt-RF beta   : {ff5.params['Mkt-RF']:.3f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true",
                    help="print realized statistics after writing")
    args = ap.parse_args()

    panel = build_factor_panel()
    returns = build_portfolio_returns(panel)
    operating = build_operating_panel()
    _write(panel, cfg.FACTORS_CSV)
    _write(returns, cfg.RETURNS_CSV)
    operating.to_csv(cfg.OPERATING_CSV, index=False, float_format="%.6g")
    print(f"wrote {cfg.OPERATING_CSV.relative_to(cfg.REPO_ROOT)}  "
          f"({len(operating)} rows)")
    if args.report:
        report(panel, returns)


if __name__ == "__main__":
    main()
