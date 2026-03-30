# Serensa Calculation Quick Reference

## Core Formulas - All in One Place

### Stock Movement
```
stock_available        = opening_stock + stock_added
stock_consumed         = stock_available - closing_stock
computed_closing_stock = opening_stock + stock_added - buying_value - expired_value
final_closing_stock    = MAX(computed_closing_stock, 0)  // Never negative
```

### Revenue Breakdown
```
total_sales_value      = sales_value  (includes credit)
paid_sales             = sales_value - debts  (cash + mobile only)
cash_component         = cash_received
mobile_money           = MAX(paid_sales - cash_received, 0)
```

### Cost of Goods Sold (COGS)
```
IF buying_value > 0:
    effective_cogs     = buying_value  (explicit tracking)
    extra_waste_cost   = expired_value  (additional loss)
ELSE:
    effective_cogs     = stock_consumed  (estimated)
    extra_waste_cost   = 0  (waste already in stock consumed)
```

### Profitability
```
gross_profit           = sales_value - effective_cogs - extra_waste_cost
net_profit_or_loss     = gross_profit - expenses
```

---

## Decision Trees

### Should We Use buying_value or stock_consumed for COGS?

```
┌─ Is buying_value > 0 ?
│
├─ YES ─→ Use buying_value as COGS
│         Include expired_value as additional cost
│         (Explicit cost tracking mode)
│
└─ NO  ─→ Use stock_consumed as COGS
          Ignore expired_value (already in movement)
          (Estimated mode)
```

### How Do We Calculate Opening Stock?

```
┌─ Does entry exist for (shop, yesterday)?
│
├─ YES ─→ Use yesterday's closing_stock
│
├─ NO  ─→ Does any earlier entry exist?
│         ├─ YES ─→ Use latest earlier entry's closing_stock
│         ├─ NO  ─→ RETURN None (manual entry required)
│
```

### How Do We Handle Mobile Money With Overpayment?

```
┌─ Is cash_received >= paid_sales ?
│
├─ YES ─→ mobile_money = 0  (all payment via cash)
│
└─ NO  ─→ mobile_money = paid_sales - cash_received
```

---

## Validation Rules (Assertions)

### Stock Integrity
```
✓ stock_available >= stock_consumed
✓ closing_stock >= 0 (always)
✓ closing_stock <= stock_available
✓ stock_consumed = stock_available - closing_stock
```

### Revenue Integrity  
```
✓ paid_sales = sales_value - debts
✓ paid_sales = cash_received + mobile_money_received
✓ mobile_money_received >= 0
```

### Profit Integrity
```
✓ gross_profit = sales_value - effective_cogs - extra_waste_cost
✓ profit_or_loss = gross_profit - expenses
✓ profit_or_loss can be positive or negative
```

### Period Aggregation
```
✓ SUM(day1_profit + day2_profit + ...) = period_profit
✓ SUM(all daily_sales) = period_sales
✓ cumulative[n] >= cumulative[n-1]
```

---

## Worked Examples

### Example 1: Simple Day With Explicit COGS Tracking
```
INPUTS:
  opening_stock = 100 units
  stock_added = 50 units
  sales_value = 1,000 KES
  debts = 100 KES
  cash_received = 600 KES
  buying_value = 800 KES (explicit cost of goods sold)
  expired_value = 50 KES (waste)
  expenses = 150 KES
  closing_stock = 30 units

CALCULATIONS:
  stock_available      = 100 + 50 = 150 units ✓
  stock_consumed       = 150 - 30 = 120 units
  
  paid_sales           = 1,000 - 100 = 900 KES
  mobile_money         = MAX(900 - 600, 0) = 300 KES ✓
  
  effective_cogs       = 800 KES (buying_value > 0)
  extra_waste_cost     = 50 KES (included)
  
  gross_profit         = 1,000 - 800 - 50 = 150 KES
  profit_or_loss       = 150 - 150 = 0 KES (break-even)
```

### Example 2: Day Without Explicit COGS (Estimated Based on Stock)
```
INPUTS:
  opening_stock = 80 units
  stock_added = 40 units
  sales_value = 900 KES
  debts = 0 KES
  cash_received = 500 KES
  buying_value = 0 KES (not tracked)
  expired_value = 100 KES (ignored)
  expenses = 100 KES
  closing_stock = 50 units

CALCULATIONS:
  stock_available      = 80 + 40 = 120 units ✓
  stock_consumed       = 120 - 50 = 70 units
  
  paid_sales           = 900 - 0 = 900 KES
  mobile_money         = MAX(900 - 500, 0) = 400 KES ✓
  
  effective_cogs       = 70 units (stock_consumed, buying_value = 0)
  extra_waste_cost     = 0 KES (ignored, waste in stock consumed)
  
  gross_profit         = 900 - 70 - 0 = 830 KES
  profit_or_loss       = 830 - 100 = 730 KES
```

### Example 3: Negative Closing Stock Prevention
```
INPUTS:
  opening_stock = 50 units
  stock_added = 30 units
  buying_value = 120 units (more than available!)
  expired_value = 10 units
  
CALCULATION:
  computed_closing     = 50 + 30 - 120 - 10 = -50
  final_closing_stock  = MAX(-50, 0) = 0 ✓ (clamped to zero)
```

---

## Monthly Profit Calculation

```
For a given month:

1. Collect all entries from first day to last day
2. Deduplicate: Keep latest entry per (shop, date)
3. Calculate each entry's profit_or_loss:
   profit_or_loss = (sales_value - cogs - waste) - expenses
4. SUM all profit_or_loss values:
   monthly_profit = entry1.profit + entry2.profit + ... + entryN.profit

This is done for:
  - Overall (all shops)
  - Per-shop breakdown
```

---

## Data Quality Checklist

Before trusting report outputs, verify:

1. **No Duplicate Entries**
   - If multiple entries exist for same (shop, date)
   - System uses only the latest (highest updated_at)

2. **Opening Stock Continuity**  
   - Day N opening_stock = Day N-1 closing_stock
   - First entry either has manual opening or derived from history

3. **No Negative Values**
   - closing_stock >= 0
   - mobile_money >= 0

4. **Revenue Splits Are Consistent**
   - cash_received + mobile_money_received = paid_sales
   - paid_sales = sales_value - debts

5. **Stock Math Is Consistent**
   - stock_consumed = (opening + added) - closing
   - This must equal sum of buying_value + expired_value + waste

6. **Profit Calculation Path Is Consistent**
   - IF using explicit COGS: check expired_value is included
   - IF using estimated COGS: check expired_value is 0 or ignored

---

## Common Mistakes to Avoid

❌ **Mistake 1:** Treating stock and COGS as if they're always comparable
  - Stock tracked in units, COGS in KES
  - When buying_value=0, stock_consumed acts as proxy (units as cost)
  
✓ **Fix:** Explicitly check buying_value field before interpreting

---

❌ **Mistake 2:** Double-counting expenses or waste
  - If using stock_consumed as COGS, waste is already included
  - Don't add expired_value twice
  
✓ **Fix:** Only add expired_value when buying_value > 0

---

❌ **Mistake 3:** Allowing negative closing stock
  - Leads to invalid stock_consumed calculation
  
✓ **Fix:** Always clamp to 0: `MAX(computed, 0)`

---

❌ **Mistake 4:** Not deduplicating entries before aggregation
  - Multiple updates to same day create duplicates
  
✓ **Fix:** Keep only latest per (shop, date)

---

❌ **Mistake 5:** Forgetting about credit sales (debts)
  - paid_sales ≠ sales_value when debts exist
  
✓ **Fix:** Always calculate: paid_sales = sales_value - debts

---

## Testing Your Implementation

### Minimal Test
```python
# Setup
entry = DailyEntry(
    opening_stock=100,
    stock_added=50,
    sales_value=1000,
    debts=100,
    cash_received=500,
    buying_value=800,
    expired_value=50,
    expenses=150,
    closing_stock=???  # This is calculated
)

# Verify closing_stock is calculated correctly
# Expected: 100 + 50 - 800 - 50 = -700 → clamped to 0
assert entry.closing_stock == 0

# Verify profit is correct
# Gross: 1000 - 800 - 50 = 150
# Net: 150 - 150 = 0
assert entry.profit_or_loss == 0
```

---

## Formula Summary (Cheat Sheet)

| Calculation | Formula | Min | Max |
|---|---|---|---|
| stock_available | opening + added | 0 | ∞ |
| stock_consumed | available - closing | 0 | available |
| closing_stock | MAX(open + add - buy - exp, 0) | 0 | ∞ |
| paid_sales | sales - debts | 0 | sales |
| mobile_money | MAX(paid - cash, 0) | 0 | ∞ |
| effective_cogs | buying OR stock_consumed | 0 | ∞ |
| gross_profit | sales - cogs - waste | -∞ | ∞ |
| net_profit | gross - expenses | -∞ | ∞ |

---

## Calculation Flow Diagram

```
USER INPUT (Daily Entry)
    ↓
    ├─ opening_stock
    ├─ stock_added
    ├─ sales_value ──┐
    ├─ debts ────────┼─→ paid_sales = sales - debts
    ├─ cash_received ┤
    │                └─→ mobile_money = MAX(paid - cash, 0)
    ├─ buying_value ─┐
    ├─ expired_value ┼─→ COGS logic branch
    ├─ closing_stock ┤
    │                └─→ stock_consumed = (open + add) - close
    └─ expenses
    
    ↓
    
CALCULATED FIELDS (Per Entry)
    ├─ stock_available = open + added
    ├─ stock_consumed = avail - close
    ├─ paid_sales = sales - debts
    ├─ mobile_money = MAX(paid - cash, 0)
    ├─ effective_cogs = buying > 0 ? buying : stock_consumed
    ├─ extra_waste = buying > 0 ? expired : 0
    ├─ gross_profit = sales - cogs - waste
    └─ profit_or_loss = gross - expenses
    
    ↓
    
AGGREGATION (Per Period)
    ├─ Deduplicate by (shop, date) → keep latest
    ├─ Sum all fields across entries
    ├─ Calculate cumulative daily rollups
    └─ Generate reports
```

---

## Debugging Tips

**Problem:** Closing stock is negative
- ❌ Don't allow negative closing stock
- ✓ Always clamp to 0 before saving

**Problem:** Mobile money exceeds paid_sales
- ❌ Check your logic
- ✓ mobile_money = MAX(paid_sales - cash_received, 0)
- ✓ Max possible = paid_sales

**Problem:** Profit doesn't reconcile
- ❌ Check if you're mixing explicit vs estimated COGS
- ✓ If buying_value=0, set profit = sales - stock_consumed - expenses
- ✓ If buying_value>0, set profit = sales - buying_value - expired_value - expenses

**Problem:** Day-to-day stock doesn't flow
- ❌ Different shops or date gaps
- ✓ opening_stock of day N = closing_stock of day N-1 (same shop)
- ✓ If gap, use latest available entry's closing stock

