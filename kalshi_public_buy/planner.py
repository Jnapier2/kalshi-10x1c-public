from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Mapping

SCHEMA_VERSION = 'kalshi-buy-public-snapshot-v1'
CONTRACTS = 10
ECONOMIC_PRICE_CENTS = Decimal('1')
MAX_MARKET_DATA_AGE_SECONDS = Decimal('10')
TICKER_PATTERN = re.compile(r'^[A-Z0-9][A-Z0-9_.:-]{2,63}$')
ALLOWED_FIELDS = {
    'schema_version', 'round_id', 'ticker', 'side', 'market_status',
    'platform_status', 'market_data_age_seconds', 'price_grid_allows_one_cent',
    'fee_evidence_complete', 'balance_evidence_complete', 'scoped_balance_cents',
    'modeled_fee_cents', 'exchange_index', 'observed_exchange_indexes',
    'existing_open_order', 'position_contracts', 'book_would_cross',
    'prior_intent_ids', 'notes',
}


def _decimal(value: Any, field: str, errors: list[str]) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f'invalid_{field}')
        return Decimal('0')
    if not result.is_finite():
        errors.append(f'invalid_{field}')
        return Decimal('0')
    return result


def _intent_id(snapshot: Mapping[str, Any]) -> str:
    body = {
        'round_id': snapshot.get('round_id'),
        'ticker': snapshot.get('ticker'),
        'side': snapshot.get('side'),
        'exchange_index': snapshot.get('exchange_index'),
        'contracts': CONTRACTS,
        'economic_price_cents': str(ECONOMIC_PRICE_CENTS),
    }
    encoded = json.dumps(body, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return 'public-plan-' + hashlib.sha256(encoded).hexdigest()[:24]


def plan_buy(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    holds: list[str] = []
    quarantines: list[str] = []

    if not isinstance(snapshot, Mapping):
        return _result('INVALID', ['snapshot_not_object'], None)

    unknown = sorted(set(snapshot) - ALLOWED_FIELDS)
    if unknown:
        errors.extend(f'unsupported_field:{name}' for name in unknown)

    if snapshot.get('schema_version') != SCHEMA_VERSION:
        errors.append('unsupported_schema_version')

    round_id = snapshot.get('round_id')
    if not isinstance(round_id, str) or not round_id.strip():
        errors.append('invalid_round_id')

    ticker = snapshot.get('ticker')
    if not isinstance(ticker, str) or not TICKER_PATTERN.fullmatch(ticker):
        errors.append('invalid_ticker')

    side = snapshot.get('side')
    if side not in {'yes', 'no'}:
        errors.append('invalid_side')

    if snapshot.get('market_status') != 'open':
        holds.append('market_not_open')
    if snapshot.get('platform_status') != 'operational':
        holds.append('platform_not_operational')

    age = _decimal(snapshot.get('market_data_age_seconds'), 'market_data_age_seconds', errors)
    if age < 0 or age > MAX_MARKET_DATA_AGE_SECONDS:
        holds.append('market_data_stale')

    if snapshot.get('price_grid_allows_one_cent') is not True:
        holds.append('one_cent_price_not_supported')
    if snapshot.get('fee_evidence_complete') is not True:
        holds.append('fee_evidence_incomplete')
    if snapshot.get('balance_evidence_complete') is not True:
        holds.append('balance_evidence_incomplete')

    modeled_fee = _decimal(snapshot.get('modeled_fee_cents'), 'modeled_fee_cents', errors)
    balance = _decimal(snapshot.get('scoped_balance_cents'), 'scoped_balance_cents', errors)
    if modeled_fee < 0 or balance < 0:
        errors.append('negative_financial_value')
    required = Decimal(CONTRACTS) * ECONOMIC_PRICE_CENTS + modeled_fee
    if balance < required:
        holds.append('scoped_balance_insufficient')

    exchange_index = snapshot.get('exchange_index')
    if not isinstance(exchange_index, int) or isinstance(exchange_index, bool) or exchange_index < 0:
        errors.append('invalid_exchange_index')

    observed = snapshot.get('observed_exchange_indexes')
    if not isinstance(observed, list) or not observed or any(
        not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in observed
    ):
        errors.append('invalid_observed_exchange_indexes')
        observed_set: set[int] = set()
    else:
        observed_set = set(observed)
        if len(observed_set) > 1:
            quarantines.append('conflicting_observed_exchange_indexes')
        if isinstance(exchange_index, int) and exchange_index not in observed_set:
            quarantines.append('intended_observed_shard_mismatch')

    if snapshot.get('existing_open_order') is not False:
        holds.append('existing_open_order')

    position = snapshot.get('position_contracts')
    if not isinstance(position, int) or isinstance(position, bool) or position < 0:
        errors.append('invalid_position_contracts')
    elif position != 0:
        holds.append('existing_position')

    if snapshot.get('book_would_cross') is not False:
        holds.append('post_only_would_cross')

    prior_ids = snapshot.get('prior_intent_ids')
    if not isinstance(prior_ids, list) or any(not isinstance(item, str) for item in prior_ids):
        errors.append('invalid_prior_intent_ids')
        prior_ids = []

    intent_id = _intent_id(snapshot) if not errors else None
    if intent_id and intent_id in prior_ids:
        holds.append('duplicate_intent')

    if errors:
        return _result('INVALID', errors, intent_id)
    if quarantines:
        return _result('QUARANTINE', quarantines, intent_id)
    if holds:
        return _result('HOLD', holds, intent_id)

    return {
        **_result('PLAN', [], intent_id),
        'plan': {
            'ticker': ticker,
            'round_id': round_id,
            'side': side,
            'contracts': CONTRACTS,
            'economic_price_cents': str(ECONOMIC_PRICE_CENTS),
            'principal_cents': str(Decimal(CONTRACTS) * ECONOMIC_PRICE_CENTS),
            'modeled_fee_cents': str(modeled_fee),
            'exchange_index': exchange_index,
            'order_behavior': 'post-only planning evidence',
        },
    }


def _result(decision: str, reasons: list[str], intent_id: str | None) -> dict[str, Any]:
    return {
        'schema_version': 'kalshi-buy-public-plan-result-v1',
        'decision': decision,
        'reason_codes': sorted(set(reasons)),
        'intent_id': intent_id,
        'network_access': False,
        'credential_support': False,
        'live_write_capability': False,
        'write_authority': 'none',
    }
