# AI DOF

An AI-augmented Director of Finance workflow: synthetic multi-entity financial data, an analytical layer built in Quadratic, and a Claude Skill that turns finished analysis into an executive-ready CFO review.

## The thesis

Standard FP&A work — building the aging report, running the variance, assembling the pack — is increasingly something Claude can do unassisted. The edge is no longer in producing the analysis. It is in the judgment layer above it: knowing which of thirty true findings changes the quarter, sizing it in cash, naming the risk, and assigning the action.

This project demonstrates that layer end to end, at a scale that would normally take a finance team of ten.

## Repository contents

```
.
├── data_compact/                        Canonical dataset — every file under 750 rows
│   ├── Meridian_Holdings_QuickBooks_Compact.xlsx
│   ├── README_COMPACT.md
│   └── csv/                             8 tabs, importable to Quadratic or QuickBooks
├── Meridian_Holdings_Master_Data.xlsx   Same data, one workbook, plus Read Me and Findings Key tabs
├── skills/
│   ├── ai-dof/                          The Claude Skill (source)
│   │   ├── SKILL.md
│   │   ├── references/                  CFO thinking, risk frameworks, communication, dashboard spec
│   │   ├── assets/dashboard_template.html
│   │   └── examples/worked_example.md
│   ├── ai-dof.skill                     Installable package
│   └── ai-dof-workspace/                Sample render used to validate the template
├── treasury/                            Treasury tearsheet — analytics, charts, templates
├── generate_treasury_data.py            Deterministic synthetic-data generator
├── data_compact/treasury/               Committed generated data (3 CSVs)
├── tests/                               pytest suite for the treasury analytics
├── specs/ and plans/                    Design spec and implementation plan
├── treasury-tearsheet-jul2026.html      Rendered tearsheet, self-contained
└── cfo-review-ai-dof-command-centre-jul2026.html   Live output from the first real run
```

## The dataset

Meridian Holdings Group — a fictional logistics holdco with five entities across two currencies, 24 months to June 2026, roughly $21M annual revenue.

| Entity | Currency | Business |
|---|---|---|
| MHG | USD | Holding company / shared services |
| MLG | USD | Freight brokerage & last mile |
| CFS | USD | Asset-based trucking (acquired Mar-2024) |
| NWC | EUR | EU forwarding, customs & TMS software |
| APX | USD | Warehousing & fulfillment (3PL) |

Journal entries balance exactly; the trial balance across invoices, journals and bank data ties to $0.06. Every file is under 750 rows so the same data loads into both Quadratic and the QuickBooks free tier without divergence.

**Sixteen issues are deliberately planted** — margin erosion masked by an offsetting segment, silent churn of a top-four customer, a bad debt reserve set inversely to risk, fragmented vendor spend hiding a top-three supplier, an intercompany imbalance, unbooked FX, revenue recognition errors, duplicate payments. The Findings Key tab in the master workbook lists all sixteen with the numbers to check against.

Note that `Journal Entries.Adjustment` and `Bank Data.ReviewNote` flag several planted items in plain text. Drop those two columns before using this to test anyone.

## The skill

`ai-dof` acts as an experienced CFO reviewing output that has already been analyzed elsewhere. It does not recompute, reconcile, or rebuild the source analysis — it interprets it.

Every finding it keeps must answer three questions: why this matters, sized in cash; what risk it creates; and what management should do, with an owner and a date. The deliverable is always a single self-contained HTML dashboard.

Install by opening `skills/ai-dof.skill` in Claude, or copy `skills/ai-dof/` into your skills directory.

The design splits judgment from presentation. `assets/dashboard_template.html` carries the entire stylesheet and rendering engine; the model fills a single `DATA` object and nothing else. That keeps the output visually consistent month to month, which matters when the same executive reads it repeatedly, and means charts are inline SVG with no CDN dependency — the file works offline, in email, and in print.

## The analytical layer

The Quadratic workbook `AI_DOF_Command_Centre` sits between the data and the skill, with six analytical tabs: Executive KPI Summary, AR Aging Dashboard, Customer Risk Ranking, Collection Forecast, Overdue Invoice Monitor, and CFO Alerts.

The included review (`cfo-review-ai-dof-command-centre-jul2026.html`) is the skill's first run against that workbook. Its headline finding is a modelling error in the collection forecast — the entire overdue recovery booked into a seven-day window — which is the kind of thing the analysis layer produces and only the judgment layer catches.

## Treasury & factor analysis

A fifth view applies quantitative portfolio analysis to the group's treasury: CAPM,
Fama-French 3- and 5-factor regressions, rolling factor betas, rolling Sharpe, an
underwater plot, and compliance against a stated investment policy. A second section
turns the same machinery on Meridian's own revenue, regressing monthly growth on
freight-rate, diesel and industrial-production factors.

The layout and stylesheet are ported from the Quant Guild Library's "Intro — Trading
Dashboard" teaching project. The page renders to a single self-contained HTML file with
no CDN dependency, embedded in the Streamlit app and committed as
`treasury-tearsheet-jul2026.html`.

**Three findings are planted, in the same spirit as the ledger's sixteen:**

1. **Mandate drift.** The portfolio rotates from defensive value into high-beta small-cap
   growth in FY2026. The full-period beta is 0.94 and looks compliant against the 1.00
   ceiling; only the 63-day rolling beta shows the breach, peaking at 1.45. An annual
   report would miss it.
2. **Drawdown past policy.** A six-week market selloff, amplified by the drifted beta,
   takes maximum drawdown to −14.7% against a 10% capital-preservation limit — on cash
   the group holds for operating liquidity, not for a risk premium.
3. **Alpha that was never there.** CAPM reports +2.79% annualized alpha. That is the SMB,
   HML and RMW premia, which a single market factor cannot see. Controlling for all five
   factors leaves −0.36% gross and −0.81% net of the 45bp fee.

The three findings are causally linked, which is the point: the drift is *why* the
drawdown breached, and the apparent alpha is what stopped anyone asking.

**Portfolio size is derived, not assumed.** There is no investments line in the ledger, so
the portfolio is a modelled overlay — but its size is justified against cash that actually
exists: closing cash of $6.14M at 30 Jun 2026, less a two-month operating buffer, giving
**$1.88M** of investable excess. Every breach is sized against that figure. Note the
implication, which the page states: at the conventional three-month buffer the group has
**no** investable excess at all.

Portfolio returns, the factor panel and the pre-2024 operating history are **MODELLED**
and generated deterministically by `generate_treasury_data.py`. The most recent 23 months
of monthly revenue growth are **actual** ledger figures from
`data_compact/csv/Invoices.csv`. The returns CSV uses the same `date,portfolio_return,SPY`
schema as the reference project, so the two files are interchangeable.

### Theme

A sidebar toggle switches the whole app between dark and light — the chrome, every Plotly
figure on all five pages, and the treasury tearsheet, which re-renders with a light palette
drawn from the navy/teal the other pages already use. The choice is mirrored into the URL
(`?theme=light`), so a particular view is shareable.

One honest limitation: `st.dataframe` renders cells to a canvas, so table interiors follow
Streamlit's own light/dark setting (Settings ▸ Choose app theme) rather than the toggle.

```bash
pip install -r requirements.txt
python3 generate_treasury_data.py --report   # regenerate and print realized stats
python3 -m pytest tests/ -v                  # 52 tests
streamlit run streamlit_app.py               # "Treasury & factors" in the sidebar
```

## Roadmap

- **Live QuickBooks connection.** Replace the static import with a dynamic pull so the analytical tabs refresh against the real ledger rather than a snapshot.
- **Scheduled review.** Run the skill on a monthly cadence once the connection is live.
- **Entity-level breakdown.** The current analytical tabs report consolidated only; several findings are entity-specific and get diluted at group level.

## Notes

Built with Claude in Cowork. The dataset is entirely synthetic — Meridian Holdings Group and every customer, vendor and transaction in it are fictional.
