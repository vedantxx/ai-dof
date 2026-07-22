# Worked Example

A full pass from raw input to filled `DATA`, showing where judgment enters.

## The input

The user pastes output from an upstream analysis workflow:

```
MERIDIAN HOLDINGS - FINANCE REVIEW OUTPUT (24 months to Jun-2026)
Consolidated revenue: FY2025 $21.2M (+8.4% YoY)
Consolidated gross margin: 34.1% (PY 34.4%)

By entity, gross margin:
  Meridian Logistics   29.2% -> 28.9%
  Cascade Freight      31.9% -> 18.6%
  Northwind Cargo      47.7% -> 45.5%
  Apex Warehousing     42.0% -> 45.4%

Avg days to pay: MLG 41->47, CFS 45->64, NWC 38->49, APX 34->35
A/R total $4.98M. Current $1.88M. 1-30 $1.27M. 31-60 $0.47M.
  61-90 $0.20M. 90+ $1.16M (18 invoices).
Bad debt provision: CFS 0.09% of revenue, all others 0.32%.
Top 4 customers = 28.9% of revenue.
Largest customer (Vantage Consumer Brands, 10.3%) - billings fell
  $155k/mo to $15k/mo over 5 months. No cancellation recorded.
Vendor spend: 3 name variants of "Fuel Express" total $3.50M combined.
Intercompany: Due From $1,285,108 vs Due To $1,184,739.
FX revaluation missing 5 of 24 months.
```

Analysis is complete. Nothing here needs recomputing.

## The reasoning

**What is the story?** Group results look calm and are not. One entity is failing on two dimensions at once - margin and collections - and the consolidated view is hiding it.

**Rank by cash and consequence.**

1. *Cascade margin, 13 points.* Largest earnings impact, compounding, and masked. Top.
2. *Vantage churn.* 10.3% of revenue effectively gone; the forecast almost certainly still contains it. Cash and revenue, near-term, high confidence.
3. *Cascade receivables plus under-reserving.* 19 days of slippage and the lowest provision rate in the group sits on the worst book. Cash plus an earnings overstatement.
4. *Aged receivables.* $1.16M over 90 days across 18 invoices - larger than the two buckets beneath it, which is the wrong shape.
5. *Vendor fragmentation.* $3.50M under three spellings. Not a loss, a missed negotiation. Real money, no urgency.
6. *Control items.* Intercompany $100k out, five months of FX unbooked. Small individually; together they say the pack carries an error bar.

**Second-order questions.** Cascade's margin and its DSO are both deteriorating while its three sister entities are flat. Two problems at one entity and none elsewhere rules out a shared cause. Either Cascade bought volume with price and terms, or its customer base is under stress. That distinction changes the entire remedy - one is a pricing decision, the other is a credit decision - and the input does not settle it. That goes in `dataNotes`.

**What is missing.** Cascade's fuel spend split between rate and volume. Customer-level aging for Cascade. Whether Vantage has formally terminated.

## The filled `DATA` (abridged)

```js
const DATA = {
  meta: {
    company: "Meridian Holdings Group",
    subtitle: "Consolidated - 4 operating entities",
    period: "24 months to June 2026",
    asOf: "30 June 2026", currency: "USD",
    preparedFor: "CEO and Board", preparedBy: "Office of the CFO"
  },

  headline: {
    posture: "high",
    verdict: "Group margin looks flat, but Cascade has lost 13 points in two years and only a temporary improvement at Apex is hiding it.",
    summary: [
      "Consolidated gross margin moved 0.3 points, which reads as a stable year and is not one. Cascade Freight has gone from 31.9% to 18.6% while Apex improved enough to offset it at group level. That offset will not repeat - margin improvements plateau, deteriorations compound - so on current trends the consolidated number falls sharply next year with no prior warning in the reporting.",
      "Separately, the largest customer at 10.3% of revenue has cut billings by 90% over five months with no cancellation on file. Nobody escalated it. The forecast almost certainly still assumes this revenue.",
      "Cascade is also the worst collector in the group - 45 to 64 days - and carries the lowest bad debt provision at 0.09% against 0.32% everywhere else. The provision is being set by habit rather than by risk, which means reported earnings at that entity are overstated."
    ],
    callouts: [
      { label: "Revenue at risk", value: "$2.2M" },
      { label: "Cash tied up",    value: "~$1.1M" },
      { label: "Actions this week", value: "3" }
    ]
  },

  kpis: [
    { label: "Revenue (FY2025)", value: "$21.2M", delta: "+8.4% YoY", trend: "up", good: true,
      severity: "ok", note: "Growth intact, but concentrated in entities with the thinnest margins." },
    { label: "Gross margin", value: "34.1%", delta: "-0.3 pts", trend: "down", good: false,
      severity: "high", note: "Stable only in aggregate. Segment view is the one that matters." },
    { label: "Cascade margin", value: "18.6%", delta: "-13.3 pts", trend: "down", good: false,
      severity: "critical", note: "Two-year decline, still moving. The single largest earnings issue." },
    { label: "Group DSO", value: "52 days", delta: "+11 days", trend: "up", good: false,
      severity: "high", note: "Driven almost entirely by Cascade at 64 days." }
  ],

  ar: {
    total: "$4.98M", current: "$1.88M", overdue: "$3.10M",
    dso: "52 days", dsoPrior: "41 days", dsoTarget: "40 days",
    commentary: "Roughly $1.1M more cash sits with customers than two years ago, concentrated at one entity. At current burn that is close to a month of operating expense.",
    buckets: [
      { label: "Current", amount: 1884000, count: 28, severity: "ok" },
      { label: "1-30",    amount: 1270000, count: 13, severity: "low" },
      { label: "31-60",   amount:  469000, count:  3, severity: "medium" },
      { label: "61-90",   amount:  201000, count:  2, severity: "high" },
      { label: "90+",     amount: 1158000, count: 18, severity: "critical" }
    ],
    agingCommentary: "The shape is wrong. The 90+ bucket is larger than 31-60 and 61-90 combined, which happens when nothing is ever written off rather than when collections are slow. $1.16M across 18 invoices against a group provision well below that - the write-off has been incurred, it just has not been recognized."
  },

  alerts: [
    { severity: "critical",
      title: "Largest customer has effectively churned without anyone recording it",
      finding: "Vantage Consumer Brands, 10.3% of revenue, fell from $155k to $15k monthly over five months. No cancellation on file.",
      risk: "About $2.2M of annualised revenue, almost certainly still in the forecast. A decline this size running five months unflagged suggests the same blind spot applies to other accounts.",
      action: "CEO to make direct executive contact this week. Rerun the forecast with this account at zero and report what breaks.",
      owner: "CEO", timing: "This week" },

    { severity: "high",
      title: "Bad debt provision is set inversely to risk",
      finding: "Cascade reserves 0.09% of revenue against 0.32% at every other entity, while carrying the group's worst aging.",
      risk: "Earnings at Cascade are overstated. $1.16M sits beyond 90 days against a provision materially below it.",
      action: "Reset provisioning to a risk-based rate and book the catch-up in this period rather than spreading it.",
      owner: "Controller", timing: "Before close" }
  ],

  actions: [
    { rank: 1,
      action: "Move board and management reporting to segment margin. Retire the consolidated headline.",
      rationale: "The consolidated figure concealed a 13-point decline for two years. It will conceal the next one.",
      owner: "CFO", timing: "Next reporting cycle",
      impact: "Restores visibility on roughly 25% of group revenue", effort: "Low" },

    { rank: 2,
      action: "Split Cascade's fuel and purchased transport spend between rate and volume, and bring pricing recommendations to the next review.",
      rationale: "Cost per unit and mix shift call for completely different remedies. Acting before knowing which risks fixing the wrong thing.",
      owner: "CFO with Cascade GM", timing: "30 days",
      impact: "Determines the path back to roughly 6 points of the 13 lost", effort: "Medium",
      tradeoff: "Repricing to recover margin will cost volume at an entity already losing share." }
  ],

  dataNotes: [
    "Cascade's fuel spend is not split between rate and volume, so the margin decline cannot yet be attributed to input cost versus pricing. This blocks the pricing decision.",
    "No customer-level aging for Cascade, so it is not possible to tell whether the DSO slippage is broad or concentrated in a few distressed accounts. The two have different remedies.",
    "Whether Vantage has formally terminated is not stated. Treated here as churn based on the billing pattern."
  ]
};
```

## What to notice

**Nothing was recalculated.** Every figure appears exactly as supplied. The `$1.1M` and `$2.2M` are derived - simple arithmetic on given inputs - and are described as approximate.

**The most important finding was not in the input.** The input reported four margin figures. The finding is that the consolidated number hides them, and that the offset is temporary. That inference is the entire value of the review.

**Uncertainty is stated, not hidden.** The Cascade diagnosis stops at the point the data stops supporting it, and the missing input is named in `dataNotes` with the decision it blocks.

**The trade-off is named.** Recovering margin costs volume. Saying so is what makes the recommendation credible.

**A whole section was omitted.** No `forecast` was supplied and none was invented. The section simply does not render.
