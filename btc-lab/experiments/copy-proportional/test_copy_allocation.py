import unittest
from copy_allocation import proportional_sale, entry_capacity, allocate_basis


class AllocationTests(unittest.TestCase):
    def sale(self, **overrides):
        args = dict(copied_shares=10_000_000, source_before=100_000_000,
                    source_sold=25_000_000, inventory_verified=True)
        return proportional_sale(**(args | overrides))

    def test_quarter_sale_does_not_close_full_position(self):
        self.assertEqual(self.sale().shares, 2_500_000)

    def test_final_sale_closes_remaining_position(self):
        self.assertEqual(self.sale(copied_shares=7_500_000,
            source_before=75_000_000, source_sold=75_000_000).shares, 7_500_000)

    def test_unknown_or_unverified_inventory_is_not_assumed(self):
        for change in (dict(source_before=None), dict(inventory_verified=False)):
            self.assertEqual(self.sale(**change).reason, 'SOURCE_INVENTORY_UNVERIFIED')

    def test_out_of_order_or_incomplete_inventory_is_rejected(self):
        self.assertEqual(self.sale(source_before=10).reason, 'SOURCE_INVENTORY_INCONSISTENT')

    def test_duplicate_event_produces_no_second_sale(self):
        self.assertEqual(self.sale(event_already_processed=True).shares, 0)

    def test_no_float_money_or_negative_quantities(self):
        for quantity in (-1, .5, True):
            with self.assertRaises(ValueError):
                self.sale(source_sold=quantity)

    def test_capacity_is_shared_across_positions(self):
        self.assertEqual(entry_capacity(open_cost=3_000_000, cash=500_000_000,
            day_gross_loss=0, week_gross_loss=0), 2_000_000)

    def test_existing_exposure_reserved_against_loss_limits(self):
        self.assertEqual(entry_capacity(open_cost=3_000_000, cash=500_000_000,
            day_gross_loss=12_000_000, week_gross_loss=12_000_000), 0)

    def test_cash_and_week_cap_cannot_be_exceeded(self):
        self.assertEqual(entry_capacity(open_cost=1_000_000, cash=500_000_000,
            day_gross_loss=0, week_gross_loss=28_000_000), 1_000_000)
        self.assertEqual(entry_capacity(open_cost=0, cash=5,
            day_gross_loss=0, week_gross_loss=0), 5)

    def test_repeated_partial_sales_preserve_all_basis(self):
        shares, cost, fee = 13, 101, 7
        cost_sum = fee_sum = 0
        for quantity in (3, 4, 6):
            sold, retained = allocate_basis(total_shares=shares,
                sold_shares=quantity, cost=cost, entry_fee=fee)
            cost_sum += sold[0]
            fee_sum += sold[1]
            cost, fee = retained
            shares -= quantity
        self.assertEqual((cost_sum, fee_sum, shares, cost, fee), (101, 7, 0, 0, 0))

    def test_partial_realized_and_remaining_basis_reconcile(self):
        sold, remaining = allocate_basis(total_shares=10_000_000,
            sold_shares=2_500_000, cost=4_800_000, entry_fee=200_000)
        proceeds, exit_fee = 1_500_000, 20_000
        realized = proceeds-exit_fee-sum(sold)
        cash = 500_000_000-5_000_000+proceeds-exit_fee
        self.assertEqual(cash+sum(remaining), 500_000_000+realized)


if __name__ == '__main__':
    unittest.main()
