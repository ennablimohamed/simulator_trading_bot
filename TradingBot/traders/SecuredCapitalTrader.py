import logging
import uuid
from datetime import datetime
import time
from decimal import Decimal

from date.date_util import get_current_date, compute_duration_until_now
from traders.abstract_multi_trade_trader import AbstractMultiTradeTrader


def limit_reached():
    return False


class SecuredCapitalTrader(AbstractMultiTradeTrader):

    def __init__(self,trader_id, symbol, capital, trade_capital_percentage, order_book, trader_updates_queue, target_volume, respected_gap_value):
        super().__init__(trader_id,
                         symbol,
                         capital,
                         trade_capital_percentage,
                         order_book,
                         name='SecuredCapitalTrader',
                         trader_updates_queue=trader_updates_queue,
                         target_volume=target_volume,
                         respected_gap_value=respected_gap_value)
        self.stop_loss_percentage = Decimal('0.05')

    def handle_trading_logic(self):
        if self.current_price:
            for order in self.current_orders[:]:
                self.update_order(order)

        if self.can_buy():
            order_size = self.calculate_order_size()
            if order_size > Decimal('0'):
                self.buy_order(order_size)
                logging.info(
                    f"{self.name} : Open buy order for {self.symbol} "
                    f"at {self.current_price} with quantity {order_size}")



    def can_buy(self):
        current_support = self.support['value']
        if self.current_price:
            return (self.current_price and
                    self.capital >= 100 and
                    not limit_reached() and
                    self.respected_gap() and
                    current_support and current_support <= self.current_price <= current_support * Decimal('1.001')
                    and not self.is_price_in_buy_orders(self.current_price))
        return False

    def compute_analytics(self):
        analytics = {}
        total_profit_loss = Decimal('0')
        for trade in self.trade_history:
            total_profit_loss += trade['profit']
        analytics['total_profit_loss'] = total_profit_loss
        for trade in self.current_orders:
            potential_profit_loss = self.compute_potential_profit_loss(trade)
            if potential_profit_loss is not None:
                total_profit_loss += potential_profit_loss
        analytics['potential_profit_loss'] = total_profit_loss
        return analytics

    def buy_order(self, order_size):
        base_cost = self.current_price * order_size
        buy_fee = base_cost * self.trading_fee_percentage
        stop_loss_price = self.current_price * (Decimal('1') - self.stop_loss_percentage)
        cost = base_cost + buy_fee
        new_order = {
            'id': str(uuid.uuid4()),
            'cost': cost,
            'opened_at': get_current_date(),
            'buy_price': self.current_price,
            'quantity': order_size,
            'buy_fee': buy_fee,
            'status': 'open',
            'secured': False,
            'max_price': self.current_price,  # Pour le trailing stop-loss
            'stop_loss_price': stop_loss_price,
            'support': self.support['value'],
            'support_volume': self.support['volume'],
            'support_index': self.support['index']
        }
        self.current_orders.append(new_order)
        self.update_capital_after_trade('buy', self.current_price, order_size)
        self.update_file()

    def update_order(self, order):
        if self.current_price and self.current_price > order['max_price']:
            if order.get('secured', False):
                self.update_stop_loss(order)
            order['max_price'] = self.current_price

        if not order.get('secured', False):
            self.update_secured(order)

        if self.current_price <= order['stop_loss_price']:
            self.sell_trade(order)
            self.update_capital_after_trade(action='sell', order_price=self.current_price, quantity=order['quantity'])
            self.trade_history.append(order)
            logging.info(
                f"{self.name} : Successfull sale for order {order['id']} with profit/loss {order['profit']}")
            self.current_orders.remove(order)
            self.update_file()

    def update_stop_loss(self, order):
        order['stop_loss_price'] = ((self.current_price - order['max_price']) * Decimal('0.5')) + order[
            'max_price']

    def update_secured(self, order):
        if self.current_price:

            potential_profit = self.compute_potential_profit_loss(order)
            total_fees = order['buy_fee'] + (self.current_price * self.trading_fee_percentage * order['quantity'])
            if potential_profit >= total_fees:
                # Capital sécurisé
                order['secured'] = True
                # Ajuster le stop-loss pour suivre le prix maximum avec le trailing stop
                order['stop_loss_price'] = order['max_price']
                logging.info(
                    f"{self.name} : Securing capital pour l'ordre à {order['buy_price']} avec stopLoss {order['stop_loss_price']}")

    def sell_trade(self, order):
        try:
            order['sailed_quantity'] = order['quantity']
            order['sale_price'] = self.current_price
            order['closed_at'] = get_current_date()
            start_datetime = datetime.strptime(order['opened_at'], "%d/%m/%YT%H:%M")
            order['duration'] = compute_duration_until_now(start_datetime)
            order['sale_timestamp'] = time.time()

            sale_fee = self.current_price * order['quantity'] * self.trading_fee_percentage
            order['sale_fee'] = sale_fee
            order['profit'] = self.compute_potential_profit_loss(order)
        except Exception as e:
            logging.error(f"Error when selling order {order['id']}")

    def update_file(self):
        self.trading_data['currentOrders'] = self.current_orders
        self.trading_data['capital'] = self.capital
        self.trading_data['tradeHistory'] = self.trade_history
        self.trading_data['creation_date'] = self.creation_date
        self.save_trading_data()
