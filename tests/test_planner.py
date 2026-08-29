from __future__ import annotations

import copy
import unittest

from kalshi_public_buy.planner import plan_buy


def base_snapshot() -> dict:
    return {
        'schema_version': 'kalshi-buy-public-snapshot-v1',
        'round_id': 'R1',
        'ticker': 'TEST-MARKET-1',
        'side': 'yes',
        'market_status': 'open',
        'platform_status': 'operational',
        'market_data_age_seconds': 1,
        'price_grid_allows_one_cent': True,
        'fee_evidence_complete': True,
        'balance_evidence_complete': True,
        'scoped_balance_cents': 20,
        'modeled_fee_cents': 1,
        'exchange_index': 2,
        'observed_exchange_indexes': [2],
        'existing_open_order': False,
        'position_contracts': 0,
        'book_would_cross': False,
        'prior_intent_ids': [],
    }


class BuyPlannerTests(unittest.TestCase):
    def test_eligible_snapshot_emits_exact_public_plan(self) -> None:
        result = plan_buy(base_snapshot())
        self.assertEqual(result['decision'], 'PLAN')
        self.assertEqual(result['plan']['contracts'], 10)
        self.assertEqual(result['plan']['economic_price_cents'], '1')
        self.assertFalse(result['live_write_capability'])

    def test_stale_data_holds(self) -> None:
        snapshot = base_snapshot()
        snapshot['market_data_age_seconds'] = 11
        result = plan_buy(snapshot)
        self.assertEqual(result['decision'], 'HOLD')
        self.assertIn('market_data_stale', result['reason_codes'])

    def test_shard_conflict_quarantines_only_the_plan(self) -> None:
        snapshot = base_snapshot()
        snapshot['observed_exchange_indexes'] = [1, 2]
        result = plan_buy(snapshot)
        self.assertEqual(result['decision'], 'QUARANTINE')
        self.assertIn('conflicting_observed_exchange_indexes', result['reason_codes'])

    def test_duplicate_intent_holds(self) -> None:
        first = plan_buy(base_snapshot())
        snapshot = base_snapshot()
        snapshot['prior_intent_ids'] = [first['intent_id']]
        result = plan_buy(snapshot)
        self.assertEqual(result['decision'], 'HOLD')
        self.assertIn('duplicate_intent', result['reason_codes'])

    def test_intent_id_is_deterministic(self) -> None:
        one = plan_buy(base_snapshot())['intent_id']
        two = plan_buy(copy.deepcopy(base_snapshot()))['intent_id']
        self.assertEqual(one, two)

    def test_unknown_critical_input_fails_closed(self) -> None:
        snapshot = base_snapshot()
        snapshot['live'] = True
        result = plan_buy(snapshot)
        self.assertEqual(result['decision'], 'INVALID')
        self.assertIn('unsupported_field:live', result['reason_codes'])


if __name__ == '__main__':
    unittest.main()
