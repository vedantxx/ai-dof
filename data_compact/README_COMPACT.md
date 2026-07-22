# Meridian Holdings Group — QuickBooks import set (under 750 rows/file)

Rebuilt to fit the free-tier row cap. Every file is comfortably under 750 rows. Full 24 months and all 5 entities retained; transaction detail is coarser.

| File | Rows |
|---|---|
| Entities.csv | 5 |
| Chart_of_Accounts.csv | 87 |
| Customers.csv | 34 |
| Vendors.csv | 36 |
| Products_and_Services.csv | 22 |
| Invoices.csv | 642 |
| Journal_Entries.csv | 724 |
| Bank_Data.csv | 703 |

`Meridian_Holdings_QuickBooks_Compact.xlsx` holds all eight as tabs. Trial balance ties to $0.06.

## What changed vs. the full set

**Invoices are monthly consolidated bills.** One invoice per customer per month (24 customers) or per quarter (10 customers), one service line each. This is how contract logistics actually bills, and it collapses 2,158 invoices + 4,033 lines into 642 self-contained rows. Average invoice ~$67k.

**Expenses split by nature, not lumped into journal entries.**

- **Journal Entries** carry accruals and adjustments only — monthly direct-cost accrual per entity (4 cost buckets), quarterly intercompany fees, quarterly fuel-surcharge reclass, semi-annual depreciation, annual bad debt, monthly FX revaluation, plus the planted adjustments.
- **Bank Data** carries operating cash — customer receipts, payroll, and four monthly opex payments per entity (occupancy, insurance, technology, and a rotating category), plus quarterly AP runs and note payments.

That split is standard QBO practice and keeps both files under the cap without losing the monthly signal.

**Chart of accounts trimmed 115 → 87.** Payroll accounts consolidated into a single *Salaries, Wages & Benefits* line. Unused subaccounts removed.

**Customers 85 → 34, vendors 73 → 36, items 45 → 22.** All the ones carrying findings survived, including the three Fuel Express name variants and the two Apex Staffing / Cloudspan variants.

## What did NOT change

All twelve planted findings are intact and land at roughly the same magnitude:

- Cascade gross margin 31.9% → 25.3% → 18.6%, masked at consolidated level by Apex improving
- Top 4 customers = 28.9% of revenue; Global Retail Partners goes quiet after March 2026
- Cascade days-to-pay 45 → 64 while every other entity holds flat
- Fuel Express $3.50M once you merge the three spellings
- $100,370 intercompany imbalance; 5 months of missing FX revaluation
- $312k miscoded, $390k capitalizable-but-expensed, $834k of prepays booked straight to revenue

Full detail and magnitudes in `../data/FINDINGS_KEY.md` — the numbers there are from the full set, so a few differ by a percent or two. `../data/` is the original 16.7k-row version; it won't import to QuickBooks but it's fine for Quadratic if you ever want the denser file.

## Scale

Consolidated revenue: $9.5M (H2 2024) → $21.2M (FY2025) → $12.2M (H1 2026).
