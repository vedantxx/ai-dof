# Dashboard Specification

How to fill `assets/dashboard_template.html`.

## How the template works

The template is one file containing a `DATA` object, a stylesheet, and a render engine. Copy it, replace the `DATA` object, save it as `cfo-review-<company>-<period>.html`. Do not modify the CSS or the render functions.

The reason for this split is that design consistency is part of what makes a recurring CFO review credible - the reader learns where to look. Your contribution is judgment, which lives entirely in `DATA`.

Every section hides itself when its key is empty (`[]`, `""`, or `null`). Leave sections empty when the source data does not support them. An honest gap is better than filler, and the dashboard still reads correctly with three sections or with eleven.

Severity is always one of `"critical" | "high" | "medium" | "low"`, plus `"ok"` for an all-clear state. These map to colour throughout. Use them consistently with the definitions in `risk_frameworks.md`.

Numbers in text fields are strings, formatted as you want them read (`"$1.1M"`, `"64 days"`, `"-13.3 pts"`). Numbers in chart fields (`buckets[].amount`, `forecast.series[].expected`, `concentration.items[].pct`) must be raw numbers - the charts scale from them.

## Schema

### `meta`
`company`, `subtitle` (optional), `period`, `asOf`, `currency`, `preparedFor`, `preparedBy`.

Take these from the source. Do not convert currency or restate periods.

### `headline` - Executive Summary
- `posture` - overall state, drives the banner colour
- `verdict` - one sentence, the most important thing in the pack
- `summary` - 2-4 paragraphs
- `callouts` - 2-4 `{label, value}` chips (optional)

This is the section most people will actually read. Someone should be able to run a meeting from it alone. Lead with what is wrong and what it costs; do not open with scope or methodology.

> Weak verdict: "This review examines financial performance for the quarter."
>
> Strong verdict: "Group margin looks flat, but one segment has lost 13 points in two years and only a temporary offset elsewhere is hiding it."

### `kpis` - Executive KPI Summary
Array of `{label, value, delta, trend, good, severity, note}`.

- `trend` - `"up" | "down" | "flat"`, controls the arrow
- `good` - `true` if that direction is favourable. Revenue up is good; DSO up is not. Getting this wrong is the fastest way to look automated.
- `note` - one line of interpretation, not a restatement

4-8 cards. Choose the metrics a CEO would ask about first, not everything available.

### `ar` - A/R Overview and Aging Analysis
- `total`, `current`, `overdue`, `dso`, `dsoPrior`, `dsoTarget` - display strings
- `commentary` - what the position means for cash
- `buckets` - `[{label, amount (number), count, severity}]`, ordered current to oldest
- `agingCommentary` - what the shape of the book says

Severity per bucket should reflect actual risk, not just age. Assign `critical` to any bucket you would expect to impair.

### `concentration` (optional)
- `items` - `[{name, pct (number), note}]`, ranked descending
- `threshold` - number; draws a reference line, bars at or above it turn red
- `commentary`

Works for customer, vendor, segment, or entity concentration. Say which in the commentary.

### `customerRisk` - Customer Risk Rankings
Array of `{rank, name, exposure, revenuePct, daysPastDue, tier, drivers, action}`.

`drivers` is where the judgment goes - what makes this customer risky beyond the age of the balance. Behaviour change, volume decline, disputes, communication breakdown. `action` is specific and owned.

5-8 rows, ordered by exposure-weighted risk rather than balance size.

### `collections` - Collection Priorities
Array of `{priority, customer, amount, age, likelihood, owner, dueBy, action}`.

Ordered by recoverable cash per unit of effort, not by size. See the prioritization ordering in `risk_frameworks.md`. `likelihood` is a plain word - `"High"`, `"Moderate"`, `"Low"`, `"Doubtful"`.

### `forecast` - Cash Collection Forecast
- `horizon` - e.g. `"Next 13 weeks"`
- `series` - `[{label, expected (number), atRisk (number)}]`
- `totals` - `{expected, atRisk}` display strings
- `commentary` - what it assumes
- `accuracyNote` - how the last few forecasts performed

The `accuracyNote` matters more than the chart. A forecast with no track record is a hope; saying so is what a CFO adds.

### `alerts` - CFO Alerts
Array of `{severity, title, finding, risk, action, owner, timing}`.

The three-field structure enforces the decision framework: what it shows, what it threatens, what to do. One line each. Cap at 6 - alerts stop working when there are too many.

### `risks` - Key Business Risks
Array of `{title, category, severity, likelihood, impact, description, mitigation}`.

Structural and forward-looking, as distinct from alerts, which are immediate. `category` comes from the risk table in `risk_frameworks.md`. A risk without a `mitigation` is an observation, not a risk. Cap at 6.

### `actions` - Recommended Actions
Array of `{rank, action, rationale, owner, timing, impact, effort, tradeoff}`.

- `action` - imperative sentence, specific enough to assign
- `impact` - expected effect, quantified where possible
- `tradeoff` - optional but strongly encouraged; costless recommendations read as unconsidered

Cap at 7, ranked. Leadership executes three to five things at a time.

### `nextSteps`
Array of `{when, item, owner}`. What happens before the next review, including the information you asked for and did not get.

### `dataNotes`
Array of strings. What was not available and what decision it blocks. Almost always non-empty - naming the limits of the analysis is part of the job, and it protects every other judgment on the page.

## Quality checks before delivering

- Does the executive summary alone let someone run the meeting?
- Does every alert, risk, and action have an owner and a date?
- Is anything stated that was not in the source and not labelled as derived or inferred?
- Are severities consistent with `risk_frameworks.md`, or did they drift?
- Is `good` set correctly on every KPI?
- Does any section restate a number without adding meaning? Cut it.
- Are the priority lists capped at 5-7?
- Would you put this in front of a board without apologizing for it?

## Delivery

Save to the user's working folder as `cfo-review-<company>-<period>.html`, then present the file. Give a two or three sentence summary in chat - the headline finding and the top action. Do not restate the dashboard in the message; the point of the artifact is that the reader opens it.
