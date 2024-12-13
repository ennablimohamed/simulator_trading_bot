import time
from abc import ABC
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from date.date_util import get_current_date, compute_duration_until_now
from traders.abstract_support_trader import AbstractSupportTrader


class AbstractMultiTradeTrader(AbstractSupportTrader, ABC):

    def __init__(self, trader_id, symbol, capital, trade_capital_percentage, order_book, name, trader_updates_queue,
                 target_volume, respected_gap_value):
        self.current_orders = []
        super().__init__(trader_id, symbol, capital, trade_capital_percentage, order_book, name,
                         trader_updates_queue=trader_updates_queue,
                         target_volume=target_volume, respected_gap_value=respected_gap_value)
        if self.trading_data is None:
            self.creation_date = datetime.utcnow().strftime("%d/%m/%YT%H:%M")
            self.trading_data = {
                'currentOrders': [],
                'capital': self.capital,
                'tradeHistory': [],
                'losses_to_cover': Decimal('0'),
                'creation_date': self.creation_date,
                'fees_to_cover': Decimal('0'),
                'free_slots': 0,
                'reserved_amount': 0
            }

    def init_data(self):
        self.current_orders = self.trading_data['currentOrders']
        for order in self.current_orders:
            self.to_decimal(order)
        self.capital = Decimal(self.trading_data['capital'])
        self.trade_history = self.trading_data['tradeHistory']
        self.creation_date = self.trading_data['creation_date']
        for order in self.trade_history:
            self.to_decimal(order)
            if 'sailed_quantity' in order:
                order['sailed_quantity'] = Decimal(order['sailed_quantity'])
            if 'sale_price' in order:
                order['sale_price'] = Decimal(order['sale_price'])
            if 'sale_fee' in order:
                order['sale_fee'] = Decimal(order['sale_fee'])
            if 'profit' in order:
                order['profit'] = Decimal(order['profit'])

    def compute_potential_profit_loss(self, order, current_price=None):
        if not order:
            return Decimal('0')
        if current_price is None:
            if self.current_price is None:
                return None
            current_price = self.current_price
        buy_fee = order['buy_fee']
        sell_fee = current_price * self.trading_fee_percentage * order['quantity']
        potential_profit_loss = (current_price - order['buy_price']) * order['quantity'] - buy_fee - sell_fee
        return potential_profit_loss

    def respected_gap(self):
        # Vérifie si le gap est respecté pour tous les trades
        for order in self.current_orders:
            if self.current_price >= order['buy_price'] or (
                    order['buy_price'] - self.current_price) < self.respected_gap_value:
                return False
        return True

    def is_price_in_buy_orders(self, price):
        for order in self.current_orders:
            if order['status'] != 'buy_in_progress':
                if abs(order['buy_price'] - price) < Decimal('0.01') or order['buy_price'] <= price:
                    return True
        return False

    def to_decimal(self, order):
        if 'cost' in order:
            order['cost'] = Decimal(order['cost'])
        if 'buy_price' in order:
            order['buy_price'] = Decimal(order['buy_price'])
        if 'quantity' in order:
            order['quantity'] = Decimal(order['quantity'])
        if 'buy_fee' in order:
            order['buy_fee'] = Decimal(order['buy_fee'])
        if 'max_price' in order:
            order['max_price'] = Decimal(order['max_price'])
        if 'stop_loss_price' in order:
            order['stop_loss_price'] = Decimal(order['stop_loss_price'])
        if 'support' in order and order['support'] is not None:
            order['support'] = Decimal(order['support'])
        if 'support_volume' in order and order['support_volume'] is not None:
            order['support_volume'] = Decimal(order['support_volume'])
        if 'capital' in order:
            order['capital'] = Decimal(order['capital'])
        if 'detected_price' in order:
            order['detected_price'] = Decimal(order['detected_price'])
        if 'buy_commission' in order:
            order['buy_commission'] = Decimal(order['buy_commission'])

    def compute_potential_total_profit_loss(self):
        total_profit_loss = Decimal('0')
        # Add realized profit/loss from trade history
        for trade in self.trade_history:
            total_profit_loss += trade['profit']
        # Add unrealized profit/loss from open trades
        for trade in self.current_orders:
            if trade['status'] != 'buy_in_progress':
                potential_profit_loss = self.compute_potential_profit_loss(trade)
                if potential_profit_loss is not None:
                    total_profit_loss += potential_profit_loss
        return total_profit_loss

    def compute_daily_profits(self):
        daily_profits = defaultdict(Decimal)  # Initialisation avec valeur par défaut de 0.0 pour chaque clé

        # Collecte des profits par jour
        for order in self.trade_history:
            day = datetime.strptime(order['closed_at'], "%d/%m/%YT%H:%M").date()
            day_str = day.strftime("%d/%m/%Y")
            daily_profits[day_str] += order['profit']

        # Ordonner les jours et calculer les cumuls progressifs
        sorted_days = sorted(daily_profits.keys(), key=lambda d: datetime.strptime(d, "%d/%m/%Y"))
        cumulative_profits = {}
        cumulative_total = Decimal(0)

        for day in sorted_days:
            cumulative_total += daily_profits[day]
            cumulative_profits[day] = cumulative_total

        if len(cumulative_profits) == 0:
            return {datetime.now().date().strftime("%d/%m/%Y"): Decimal(0)}

        return cumulative_profits
