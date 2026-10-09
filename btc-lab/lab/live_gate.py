"""One switch for real orders. It is in code, not in a config file.

A config value alone cannot turn on real money. Turning this on is a code
change, a review and a deploy, after the PAPER test of the same path passed.
"""
LIVE_ORDERS_ALLOWED = False


class LiveOrdersDisabled(RuntimeError):
    pass


def require_live():
    if LIVE_ORDERS_ALLOWED is not True:
        raise LiveOrdersDisabled('real orders are disabled in code (live_gate.LIVE_ORDERS_ALLOWED)')
