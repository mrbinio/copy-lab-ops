"""Per-strategy entry switches. Existing positions still settle."""
import re

from .wallet_observer import SEED_WALLETS, PAPER_EXTRA

COPY_IDS = tuple('copy-' + wallet for wallet in SEED_WALLETS + PAPER_EXTRA)

# 9 Oct 2026: every own strategy lost after fees (about -73 USD on 206 trades
# across five accounts). They stay as an archive and settle what is open.
DEFAULT_PAUSED = {
    'early-v1': True,
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
# Newly discovered wallets are not in the seed list. Their pause switch is
# still per copy id, so observe and pause can block buys without a code change.
COPY_ID = re.compile(r'^copy-0x[0-9a-f]{40}$')


def _known(strategy):
    return strategy in TOGGLEABLE or bool(COPY_ID.fullmatch(strategy or ''))


def pauses(store):
    raw = store.get(KEY, {})
    out = {name: bool(DEFAULT_PAUSED.get(name, False)) for name in TOGGLEABLE}
    if isinstance(raw, dict):
        for name, value in raw.items():
            if _known(name):
                out[name] = bool(value)
    return out


def is_paused(store, strategy):
    return bool(pauses(store).get(strategy, False))


def set_paused(store, strategy, paused):
    if not _known(strategy):
        raise ValueError('unknown strategy')
    current = store.get(KEY, {})
    if not isinstance(current, dict):
        current = {}
    current[strategy] = bool(paused)
    store.set(KEY, current)
    return pauses(store)
