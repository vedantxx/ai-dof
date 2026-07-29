"""Quantitative machinery for the treasury tearsheet.

Deliberately free of any presentation dependency -- no streamlit, no plotly, no
jinja2 -- so the math can be read, tested and reused on its own. A test enforces
this.

The module answers the four questions a Director of Finance must answer about a
treasury portfolio:

1. How did it perform?          -> performance_stats
2. Is there skill, or just market exposure?  -> capm_regression
3. What is actually driving the returns?     -> fama_french_regression
4. Has the mandate drifted?     -> rolling_factor_betas

Everything is computed on simple daily returns as decimals (0.001 = 0.1%).

The public surface mirrors the Quant Guild "Intro - Trading Dashboard" reference
project so its templates render our results unchanged.
"""
from __future__ import annotations

import io
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm

from treasury import config as cfg

TRADING_DAYS_PER_YEAR = cfg.TRADING_DAYS_PER_YEAR

# --------------------------------------------------------------------------- #
#  1. Input parsing
# --------------------------------------------------------------------------- #
# Liberal in what we accept: this is the seam the visitor-upload flow will use,
# and real users mis-name columns constantly.
_PORTFOLIO_ALIASES = {
    "portfolio_return", "portfolio", "portfolio_returns", "port", "port_return",
    "returns", "return", "strategy", "strategy_return", "treasury", "treasury_return",
}
_SPY_ALIASES = {
    "spy", "spy_return", "spy_returns", "benchmark", "benchmark_return",
    "market", "market_return", "mkt",
}
_DATE_ALIASES = {"date", "dates", "datetime", "timestamp", "day", "month"}

MIN_OBSERVATIONS = 30


def _normalize(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_")


def load_returns(source) -> pd.DataFrame:
    """Read and normalize a daily returns CSV.

    ``source`` may be a path, a file-like object, raw bytes, or raw CSV text --
    the last two are what a web upload delivers.
    """
    if isinstance(source, bytes):
        source = io.BytesIO(source)
    elif isinstance(source, str) and ("\n" in source or "," in source):
        source = io.StringIO(source)

    df = pd.read_csv(source)
    if df.empty:
        raise ValueError("The returns CSV appears to be empty.")

    lookup = {_normalize(c): c for c in df.columns}

    def _find(aliases: set[str], what: str) -> str:
        for alias in aliases:
            if alias in lookup:
                return lookup[alias]
        raise ValueError(
            f"Could not find a {what} column. Looked for any of: "
            f"{sorted(aliases)}. Found: {list(df.columns)}."
        )

    date_col = _find(_DATE_ALIASES, "date")
    port_col = _find(_PORTFOLIO_ALIASES, "portfolio return")
    spy_col = _find(_SPY_ALIASES, "benchmark (SPY) return")

    out = pd.DataFrame({
        "portfolio_return": pd.to_numeric(df[port_col], errors="coerce"),
        "SPY": pd.to_numeric(df[spy_col], errors="coerce"),
    })
    out.index = pd.to_datetime(df[date_col], errors="coerce")
    out.index.name = "date"
    out = out[~out.index.isna()].dropna().sort_index()

    if len(out) < MIN_OBSERVATIONS:
        raise ValueError(
            f"Need at least {MIN_OBSERVATIONS} valid daily observations to "
            f"compute meaningful statistics; found {len(out)}."
        )
    if out.abs().median().median() > 1.0:
        warnings.warn(
            "Returns look large for decimals -- are these percentages? "
            "Values are used as-is; divide by 100 if needed."
        )
    return out


# --------------------------------------------------------------------------- #
#  2. Factor panel
# --------------------------------------------------------------------------- #
@dataclass
class FactorData:
    """A factor panel plus provenance, for the page's source banner."""
    factors: pd.DataFrame
    source: str
    is_synthetic: bool = False


def _load_committed_panel() -> FactorData:
    if not cfg.FACTORS_CSV.exists():
        raise FileNotFoundError(
            f"Factor panel not found at {cfg.FACTORS_CSV}. "
            "Run: python3 generate_treasury_data.py"
        )
    panel = pd.read_csv(cfg.FACTORS_CSV, parse_dates=["date"]).set_index("date")
    return FactorData(
        factors=panel,
        source="MODELLED panel committed to this repo (offline, deterministic)",
        is_synthetic=True,
    )


def load_factors(try_live: bool = True) -> FactorData:
    """Daily Fama-French factors.

    Tries Ken French's library first when ``try_live`` is set, then falls back to
    the committed MODELLED panel. The fallback is the normal case: this project
    must render identically offline, and the page says so in a banner rather than
    quietly passing modelled factors off as market data.
    """
    if try_live:
        try:
            from pandas_datareader import data as pdr  # type: ignore

            raw = pdr.DataReader("F-F_Research_Data_5_Factors_2x3_daily",
                                 "famafrench", cfg.START, cfg.END)[0]
            raw.index = pd.to_datetime(raw.index.astype(str))
            panel = raw / 100.0            # Ken French ships percent
            if not panel.empty:
                return FactorData(panel, "pandas_datareader (Ken French library)",
                                  is_synthetic=False)
        except Exception:
            pass
    return _load_committed_panel()


# --------------------------------------------------------------------------- #
#  3. Performance and risk
# --------------------------------------------------------------------------- #
def wealth_index(returns: pd.Series, initial: float = 1.0) -> pd.Series:
    """Cumulative growth of $1 -- the equity curve."""
    return initial * (1.0 + returns).cumprod()


def drawdown_series(returns: pd.Series) -> pd.Series:
    """Percentage decline from the running peak -- the underwater curve."""
    wealth = wealth_index(returns)
    return wealth / wealth.cummax() - 1.0


def max_drawdown(returns: pd.Series) -> float:
    """Worst peak-to-trough decline, as a negative number."""
    return float(drawdown_series(returns).min())


def annualized_return(returns: pd.Series) -> float:
    """CAGR implied by the realized cumulative return."""
    n = len(returns)
    if n == 0:
        return float("nan")
    growth = float((1.0 + returns).prod())
    if growth <= 0:
        return -1.0
    return growth ** (TRADING_DAYS_PER_YEAR / n) - 1.0


def annualized_volatility(returns: pd.Series) -> float:
    """Daily standard deviation scaled by the square-root-of-time rule."""
    return float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def sharpe_ratio(returns: pd.Series, rf_daily=0.0) -> float:
    """Annualized excess return per unit of total volatility."""
    excess = returns - rf_daily
    sd = excess.std(ddof=1)
    if sd == 0 or np.isnan(sd):
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(returns: pd.Series, rf_daily=0.0) -> float:
    """Like Sharpe, but penalizing only downside deviation."""
    excess = returns - rf_daily
    downside = excess[excess < 0]
    sd = downside.std(ddof=1) if len(downside) > 1 else float("nan")
    if not np.isfinite(sd) or sd == 0:
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS_PER_YEAR))


def rolling_sharpe(returns: pd.Series, window: int = cfg.DEFAULT_WINDOW,
                   rf_daily=0.0) -> pd.Series:
    """Trailing annualized Sharpe over a moving window."""
    excess = returns - rf_daily
    mean = excess.rolling(window).mean()
    sd = excess.rolling(window).std(ddof=1)
    return (mean / sd) * np.sqrt(TRADING_DAYS_PER_YEAR)


@dataclass
class PerformanceStats:
    total_return: float
    cagr: float
    ann_vol: float
    sharpe: float
    sortino: float
    max_drawdown: float
    hit_rate: float
    best_day: float
    worst_day: float


def performance_stats(returns: pd.Series, rf_daily=0.0) -> PerformanceStats:
    """The headline performance and risk metrics for one return series."""
    return PerformanceStats(
        total_return=float((1.0 + returns).prod() - 1.0),
        cagr=annualized_return(returns),
        ann_vol=annualized_volatility(returns),
        sharpe=sharpe_ratio(returns, rf_daily),
        sortino=sortino_ratio(returns, rf_daily),
        max_drawdown=max_drawdown(returns),
        hit_rate=float((returns > 0).mean()),
        best_day=float(returns.max()),
        worst_day=float(returns.min()),
    )


# --------------------------------------------------------------------------- #
#  4. Regressions -- CAPM and Fama-French share one OLS engine
# --------------------------------------------------------------------------- #
@dataclass
class FactorLoading:
    name: str
    coef: float
    tstat: float
    pvalue: float
    annualized: Optional[float] = None
    description: str = ""

    @property
    def significant(self) -> bool:
        return self.pvalue < 0.05


@dataclass
class RegressionResult:
    label: str
    loadings: list[FactorLoading]
    r_squared: float
    adj_r_squared: float
    nobs: int
    alpha_annualized: float = field(default=float("nan"))

    def loading(self, name: str) -> Optional[FactorLoading]:
        for l in self.loadings:
            if l.name.lower() == name.lower():
                return l
        return None


def _ols(y: pd.Series, X: pd.DataFrame, label: str) -> RegressionResult:
    """OLS of y on X, with a constant added and the intercept annualized.

    The daily intercept is multiplied by 252 -- the standard convention for
    daily-frequency factor regressions.
    """
    X = sm.add_constant(X, has_constant="add")
    model = sm.OLS(y, X, missing="drop").fit()

    loadings: list[FactorLoading] = []
    for name in X.columns:
        coef = float(model.params[name])
        is_const = name == "const"
        loadings.append(FactorLoading(
            name="Alpha" if is_const else name,
            coef=coef,
            tstat=float(model.tvalues[name]),
            pvalue=float(model.pvalues[name]),
            annualized=coef * TRADING_DAYS_PER_YEAR if is_const else None,
            description=("Return not explained by the factors below."
                         if is_const else cfg.FACTOR_DESCRIPTIONS.get(name, "")),
        ))

    return RegressionResult(
        label=label,
        loadings=loadings,
        r_squared=float(model.rsquared),
        adj_r_squared=float(model.rsquared_adj),
        nobs=int(model.nobs),
        alpha_annualized=float(model.params["const"] * TRADING_DAYS_PER_YEAR),
    )


def capm_regression(portfolio: pd.Series, spy: pd.Series,
                    rf_daily=0.0) -> RegressionResult:
    """CAPM: (r_p - rf) = alpha + beta (r_m - rf) + e

    With only a market factor, any return earned from style tilts lands in the
    intercept. That is exactly the trap this page is built to expose -- compare
    this alpha with the Fama-French alpha before calling it skill.
    """
    y = (portfolio - rf_daily).rename("excess_portfolio")
    x = (spy - rf_daily).rename("MKT")
    data = pd.concat([y, x], axis=1).dropna()
    result = _ols(data["excess_portfolio"], data[["MKT"]], label="CAPM")
    for l in result.loadings:
        if l.name == "MKT":
            l.name = "Beta (Market)"
            l.description = "Sensitivity to the market: 1.0 moves with it."
    return result


def fama_french_regression(portfolio: pd.Series, factor_data: FactorData,
                           factors: list[str]) -> RegressionResult:
    """Regress excess returns on a set of Fama-French factors."""
    merged = pd.concat([portfolio.rename("portfolio"), factor_data.factors],
                       axis=1, join="inner").dropna()
    if len(merged) < MIN_OBSERVATIONS:
        raise ValueError(
            "Too few overlapping dates between returns and factors "
            f"({len(merged)}) to run the factor regression."
        )
    excess = merged["portfolio"] - merged["RF"]
    return _ols(excess, merged[factors], label=f"Fama-French {len(factors)}-Factor")


def rolling_factor_betas(portfolio: pd.Series, factor_data: FactorData,
                         factors: list[str],
                         window: int = cfg.DEFAULT_WINDOW) -> pd.DataFrame:
    """Re-estimate the factor loadings over a moving window.

    Wandering lines are style drift. For this portfolio it is the only view that
    catches the mandate breach -- the full-period beta is inside the limit.
    """
    merged = pd.concat([portfolio.rename("portfolio"), factor_data.factors],
                       axis=1, join="inner").dropna()
    if len(merged) < window:
        return pd.DataFrame(columns=factors)

    excess = merged["portfolio"] - merged["RF"]
    X = sm.add_constant(merged[factors], has_constant="add")

    rows, index = [], []
    for i in range(window, len(merged) + 1):
        sl = slice(i - window, i)
        try:
            params = sm.OLS(excess.iloc[sl], X.iloc[sl]).fit().params
        except Exception:
            continue
        rows.append({f: float(params.get(f, np.nan)) for f in factors})
        index.append(merged.index[i - 1])

    if not rows:
        return pd.DataFrame(columns=factors)
    out = pd.DataFrame(rows, index=pd.DatetimeIndex(index, name="date"))
    return out


# --------------------------------------------------------------------------- #
#  5. Judgment -- the investment policy the DOF is accountable for
# --------------------------------------------------------------------------- #
@dataclass
class Breach:
    """One policy check, sized and assigned.

    Follows the ai-dof skill's rule that a finding must answer three questions:
    why it matters sized in cash, what risk it creates, and what management
    should do -- with an owner and a date.
    """
    check: str
    limit: str
    observed: str
    breached: bool
    cash_at_risk: float
    why: str
    risk: str
    action: str
    owner: str
    due: str


POLICY_OWNER = "Group CFO"
POLICY_DUE = "2026-09-30"


def _money(v: float) -> str:
    """Match the existing app's money formatting."""
    v = float(v)
    if abs(v) >= 1e6:
        return f"${v / 1e6:,.2f}M"
    if abs(v) >= 1e3:
        return f"${v / 1e3:,.0f}k"
    return f"${v:,.0f}"


def policy_check(perf: PerformanceStats, capm: RegressionResult,
                 ff5: RegressionResult, rolling: pd.DataFrame) -> list[Breach]:
    """Evaluate the treasury investment policy.

    Returns all three checks in a stable order whether or not they breach, so
    the page can show a compliance table rather than only bad news.
    """
    notional = cfg.PORTFOLIO_NOTIONAL
    limits = cfg.POLICY

    # --- 1. Mandate drift. The peak ROLLING beta, not the full-period beta:
    # the full-period number is inside the limit, which is the whole point.
    peak_beta = (float(rolling["Mkt-RF"].max())
                 if not rolling.empty and "Mkt-RF" in rolling else float("nan"))
    full_beta = capm.loading("Beta (Market)")
    full_beta_val = full_beta.coef if full_beta else float("nan")
    beta_excess = max(0.0, peak_beta - limits["max_beta"]) if np.isfinite(peak_beta) else 0.0
    beta_breached = np.isfinite(peak_beta) and peak_beta > limits["max_beta"]

    beta = Breach(
        check="Peak rolling market beta",
        limit=f"{limits['max_beta']:.2f}",
        observed=f"{peak_beta:.3f}",
        breached=bool(beta_breached),
        cash_at_risk=beta_excess * limits["market_stress"] * notional,
        why=(f"Peak {cfg.DEFAULT_WINDOW}-day rolling beta reached {peak_beta:.2f} "
             f"against a {limits['max_beta']:.2f} mandate ceiling. The full-period "
             f"beta is {full_beta_val:.2f} and looks compliant, so the annual "
             f"report would not have caught this."),
        risk=(f"In a {limits['market_stress']:.0%} market decline the excess "
              f"exposure alone costs roughly "
              f"{_money(beta_excess * limits['market_stress'] * notional)} of "
              f"operating cash the group has not budgeted to lose."),
        action="Rebalance to the mandate ceiling and add a rolling-beta breach alert.",
        owner=POLICY_OWNER,
        due=POLICY_DUE,
    )

    # --- 2. Capital preservation.
    mdd = abs(perf.max_drawdown)
    dd_excess = max(0.0, mdd - limits["max_drawdown"])
    drawdown = Breach(
        check="Maximum drawdown",
        limit=f"-{limits['max_drawdown']:.0%}",
        observed=f"{perf.max_drawdown:.1%}",
        breached=bool(mdd > limits["max_drawdown"]),
        cash_at_risk=dd_excess * notional,
        why=(f"Peak-to-trough decline reached {perf.max_drawdown:.1%} against a "
             f"-{limits['max_drawdown']:.0%} tolerance — "
             f"{_money(dd_excess * notional)} beyond policy on "
             f"{_money(notional)} invested."),
        risk=("Treasury exists to preserve operating liquidity, not to earn a "
              "risk premium. A drawdown of this size can collide with a quarter "
              "in which the group needs the cash."),
        action="Cut equity beta until the trailing drawdown is inside tolerance.",
        owner=POLICY_OWNER,
        due=POLICY_DUE,
    )

    # --- 3. Is anyone actually adding value? Compare the two alphas.
    net_alpha = ff5.alpha_annualized
    gross_alpha = net_alpha + cfg.FEE_ANNUAL
    fee_cost = cfg.FEE_ANNUAL * notional
    alpha = Breach(
        check="Alpha, net of fees",
        limit=f"{limits['min_net_alpha']:.0%}",
        observed=f"{net_alpha:+.2%}",
        breached=bool(net_alpha < limits["min_net_alpha"]),
        cash_at_risk=fee_cost,
        why=(f"CAPM reports {capm.alpha_annualized:+.2%} alpha, but that is style "
             f"premia a single market factor cannot see. Controlling for all five "
             f"Fama-French factors leaves {gross_alpha:+.2%} gross and "
             f"{net_alpha:+.2%} net of the {cfg.FEE_ANNUAL:.2%} fee."),
        risk=(f"The group pays {_money(fee_cost)} a year for exposure it could "
              f"hold passively. The apparent outperformance is factor beta, not "
              f"manager skill, and it will reverse when those factors do."),
        action=("Move the mandate to a low-cost index sleeve or renegotiate the "
                "fee against a factor-adjusted benchmark."),
        owner=POLICY_OWNER,
        due=POLICY_DUE,
    )

    return [beta, drawdown, alpha]
