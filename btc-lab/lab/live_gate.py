"""One switch for real orders. It is in code, not in a config file.

A config value alone cannot turn on real money. Turning this on is a code
change, a review and a deploy, after the PAPER test of the same path passed.
"""
LIVE_ORDERS_ALLOWED = True   # Damian's go, 19 Oct 2026: Mitch live mirror only (data/mitch_live.json limits)


class LiveOrdersDisabled(RuntimeError):
    pass


# The old generic CLOB path (clob_order.py, config clob_live) stays shut: only
# the Mitch live mirror may send real orders.
OLD_CLOB_ALLOWED = False


def require_old_clob():
    if OLD_CLOB_ALLOWED is not True:
        raise LiveOrdersDisabled('the old CLOB order path is disabled in code (live_gate.OLD_CLOB_ALLOWED)')


def require_live():
    if LIVE_ORDERS_ALLOWED is not True:
        raise LiveOrdersDisabled('real orders are disabled in code (live_gate.LIVE_ORDERS_ALLOWED)')
