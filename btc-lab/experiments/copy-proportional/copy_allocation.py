"""Pure PAPER allocation rules. No orders, storage mutation or assumed inventory.

All amounts are integer micro-units. This is an independent proposed policy,
not a claim to reproduce Mitch's private implementation.
"""
from dataclasses import dataclass


def units(value):
    if type(value) is not int or value < 0:
        raise ValueError('Expected non-negative integer micro-units')
    return value


@dataclass(frozen=True)
class SalePlan:
    shares: int
    reason: str


def proportional_sale(*, copied_shares, source_before, source_sold,
                      inventory_verified, event_already_processed=False):
    """Scale a verified source position reduction; never infer missing holdings.

    source_before must be the source balance immediately BEFORE this event,
    for the same wallet/token, including prior holdings and all intervening
    fills/transfers. A post-trade API balance is not a valid substitute.
    Caller must persist the fill and event id atomically, and replan after
    every fill. This function alone provides no deduplication or execution.
    """
    units(copied_shares)
    units(source_sold)
    if event_already_processed:
        return SalePlan(0, 'EVENT_ALREADY_PROCESSED')
    if not inventory_verified or source_before is None:
        return SalePlan(0, 'SOURCE_INVENTORY_UNVERIFIED')
    units(source_before)
    if not source_before or source_sold > source_before:
        return SalePlan(0, 'SOURCE_INVENTORY_INCONSISTENT')
    if not copied_shares or not source_sold:
        return SalePlan(0, 'NOTHING_TO_SELL')
    quantity = copied_shares * source_sold // source_before
    return SalePlan(quantity, 'PROPORTIONAL_SELL' if quantity else 'ROUNDING_DUST')


def entry_capacity(*, open_cost, cash, day_gross_loss, week_gross_loss,
                   exposure_cap=5_000_000, day_cap=15_000_000,
                   week_cap=30_000_000):
    """All-in acquisition capacity, reserving full loss on existing positions.

    Several lots share the SAME wallet cap, rather than each receiving 5USD.
    Capacity includes entry fees; market minimum/FOK checks remain mandatory.
    Caller must recompute inside the ledger transaction before committing.
    """
    for value in (open_cost, cash, day_gross_loss, week_gross_loss,
                  exposure_cap, day_cap, week_cap):
        units(value)
    return max(0, min(cash, exposure_cap-open_cost,
                      day_cap-day_gross_loss-open_cost,
                      week_cap-week_gross_loss-open_cost))


def allocate_basis(*, total_shares, sold_shares, cost, entry_fee):
    """Allocate original acquisition basis without creating/removing cents.

    Return sold and retained (cost, entry_fee). Final sale consumes all dust.
    Sale proceeds and exit fee are additional execution inputs, not estimates.
    """
    for value in (total_shares, sold_shares, cost, entry_fee):
        units(value)
    if total_shares == 0 or sold_shares > total_shares:
        raise ValueError('Invalid sale quantity')
    sold_cost = cost * sold_shares // total_shares
    sold_fee = entry_fee * sold_shares // total_shares
    return (sold_cost, sold_fee), (cost-sold_cost, entry_fee-sold_fee)
