# EXPERIMENT-MID-WINDOW-V2.md — frozen forward PAPER specification, 2026-09-30

This is a preregistered research variant of mid-window-v1, based on independent
audit findings (44 v1 trades). Parameters are frozen; do not optimize on forward
data. A new $500 virtual account is created. No live capital is used.

## Changes from v1

| Parameter | v1 | v2 | Rationale |
|-----------|----|----|-----------|
| Entry window | 180–420s (3–7 min) | 180–300s (3–5 min) | Late entries (>220s elapsed) showed ~40% WR vs ~73% early |
| Ask range | 0.50–0.80 | 0.50–0.70 | Better EV at lower prices; 80c requires >82% probability |
| Z-score threshold | ≥1.0 | ≥1.5 | Stronger filter: fewer trades, higher quality signals |
| Take profit | 10% net | 15% net | Breakeven WR drops from 50% to ~40% |
| Stop loss | 10% net (protected) | 10% net | Unchanged |
| Max spread | 3.0c | 2.5c | Tighter execution quality |

## Acceptance criteria (precommitted)

- Minimum 100 trades on new account before evaluation
- Positive net PnL after deducting worst-case 20% slippage estimate
- Expectancy > $0.10/trade after all fees and slippage
- Max drawdown < 8% of peak equity
- Not dominated by a few large wins (remove top 3 wins, still positive or inconclusive)

## What this is NOT

- Not a copy of Mitch's v8 algorithm
- Not a calibrated probability model
- Not evidence of profitability
- Not optimized on forward data (parameters frozen at specification time)

## Risk policies

- Risk policy: `btc-mid-v2-stop10` (10% net stop, protective sale until 900s)
- Same budget/day/week/drawdown limits as other baseline accounts
- Independent $500 virtual account, not shared with v1

## Comparison rules

Compare v2 only over its own forward period (from first recorded decision).
Do not mix with v1 lifetime totals. A difference vs v1 confounds timing,
parameters, and market conditions; it does not prove v2 is optimal.
