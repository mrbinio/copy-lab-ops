"""Per-strategy entry switches. Existing positions still settle."""
from .wallet_observer import SEED_WALLETS, PAPER_EXTRA

COPY_IDS = tuple('copy-' + wallet for wallet in SEED_WALLETS + PAPER_EXTRA)

DEFAULT_PAUSED = {
    'mid-window-v1': True,
    'mid-window-v2': True,
    'value-v1': True,
    'value-surface-paper-v1': True,
    'eth-mid-window-v1': True,
    'late-v1': True,
    # Paper copy: only 4096b159 has made money. The other three stay off
    # until a 30-day window on our markets says otherwise.
    'copy-0xeda9247a2b3c99a9e0bf46cdac6e1974365cf589': True,
    'copy-0x943cea746e701823b6902a6f4eaeed58207e77c2': True,
    'copy-0xeebde7a0e019a63e6b476eb425505b7b3e6eba30': True,
}

TOGGLEABLE = (
    'early-v1',
    'mid-window-v1',
    'mid-window-v2',
    'value-v1',
    'value-surface-paper-v1',
    'eth-mid-window-v1',
) + COPY_IDS
KEY = 'strategy_pauses'


def pauses(store):
    raw = store.get(KEY, {})
    out = {name: bool(DEFAULT_PAUSED.get(name, False)) for name in TOGGLEABLE}
    if isinstance(raw, dict):
        for name, value in raw.items():
            if name in TOGGLEABLE:
                out[name] = bool(value)
    return out


def is_paused(store, strategy):
    return bool(pauses(store).get(strategy, False))


def set_paused(store, strategy, paused):
    if strategy not in TOGGLEABLE:
        raise ValueError('unknown strategy')
    current = store.get(KEY, {})
    if not isinstance(current, dict):
        current = {}
    current[strategy] = bool(paused)
    store.set(KEY, current)
    return pauses(store)
