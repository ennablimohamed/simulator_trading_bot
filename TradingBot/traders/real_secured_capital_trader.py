import logging
from datetime import datetime
import time
from decimal import Decimal

from binance.spot import Spot

from date.date_util import get_current_date, compute_duration_until_now
from traders.abstract_multi_trade_trader import AbstractMultiTradeTrader


class RealSecuredCapitalTrader(AbstractMultiTradeTrader):

    def __init__(self, trader_id, symbol, capital, trade_capital_percentage, order_book,
                 trader_updates_queue, target_volume, respected_gap_value, api_config):
        super().__init__(trader_id,
                         symbol,
                         capital,
                         trade_capital_percentage,
                         order_book,
                         name='RealSecuredCapitalTrader',
                         trader_updates_queue=trader_updates_queue,
                         target_volume=target_volume,
                         respected_gap_value=respected_gap_value)
        self.stop_loss_percentage = Decimal('0.05')
        self.api_config = api_config
        # Initialize Binance client with API keys from environment variables
        api_key = api_config['credentials']['api-key']  # os.getenv('BINANCE_API_KEY')
        api_secret = api_config['credentials']['secret']  # os.getenv('BINANCE_API_SECRET')
        self.client = Spot(api_key=api_key, api_secret=api_secret, base_url=api_config['trades']['base-url'])
        self.exchange_info = self.client.exchange_info(symbol=self.symbol)
        self.min_order_value = self.extract_min_order_value(self.exchange_info['symbols'][0]['filters'])
        self.reserved_amount = Decimal(self.trading_data['reserved_amount'])
        self.fees_to_cover = Decimal(self.trading_data['fees_to_cover'])
        self.free_slots = self.trading_data['free_slots']
        self.synchronize_orders()

    def handle_trading_logic(self):
        if self.current_price:
            for order in self.current_orders[:]:
                if order['status'] != "buy_in_progress" and order['status'] != "sale_in_progress":
                    self.update_order(order)

        if self.can_buy():
            order_size = self.calculate_order_size()
            if order_size > Decimal('0'):
                if self.free_slots == 0:
                    self.buy_fees()
                self.buy_order(order_size)
                logging.info(
                    f"{self.name} : Open buy order for {self.symbol} "
                    f"at {self.current_price} with quantity {order_size}")

    def can_buy(self):
        current_support = self.support['value']
        if self.current_price:
            return (self.current_price and
                    self.capital - self.reserved_amount >= 100 and
                    not self.limit_reached() and
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
        try:
            quantity = Decimal('0.00010000')
            # Place a market buy order using Binance API
            order = self.client.new_order(symbol=self.symbol,
                                          side='buy',
                                          type='LIMIT',
                                          quantity=str(quantity),
                                          timeInForce='GTC',
                                          price=str(self.current_price))

            # Extract order details
            order_id = order['orderId']
            order_reserved_amount = self.current_price * quantity
            new_order = {
                'id': order_id,
                'opened_at': get_current_date(),
                'detected_price': self.current_price,
                'status': 'buy_in_progress',
                'secured': False,
                'support': self.support['value'],
                'support_volume': self.support['volume'],
                'support_index': self.support['index'],
                'reserved_amount': order_reserved_amount
            }
            self.free_slots -= 1
            self.reserved_amount += order_reserved_amount
            self.current_orders.append(new_order)
            self.update_file()

        except Exception as e:
            logging.error(f"Error placing buy order: {e}")

    def update_order(self, order):
        if order['status'] != 'buy_in_progress' and order['status'] != 'sale_in_progress':
            if self.current_price and self.current_price > order['max_price']:
                if order.get('secured', False):
                    self.update_stop_loss(order)
                order['max_price'] = self.current_price

            if not order.get('secured', False):
                self.update_secured(order)
            if self.current_price <= order['stop_loss_price']:
                self.sell_trade(order)

    def update_stop_loss(self, order):
        order['stop_loss_price'] = ((self.current_price - order['max_price']) * Decimal('0.5')) + order['max_price']

    def update_secured(self, order):
        if self.current_price:
            potential_profit = self.compute_potential_profit_loss(order)
            total_fees = self.fees_to_cover + (self.current_price * self.trading_fee_percentage * Decimal('0.0001'))
            if potential_profit >= total_fees:
                # Capital secured
                order['secured'] = True
                # Adjust the stop-loss to follow the maximum price with trailing stop
                order['stop_loss_price'] = order['max_price']
                logging.info(
                    f"{self.name} : Securing capital for order at {order['buy_price']} with stop loss {order['stop_loss_price']}")

    def sell_trade(self, order):
        try:
            # Place a market sell order using Binance API
            sale_order = self.client.new_order(symbol=self.symbol,
                                               side='SELL',
                                               type='LIMIT',
                                               quantity=str('0.00010000'),
                                               timeInForce='GTC',
                                               price=str(self.current_price))

            order['status'] = 'sale_in_progress'
            order['sale_order_id'] = sale_order['orderId']
            self.update_file()
        except Exception as e:
            logging.error(f"Error when selling order {order['id']}: {e}")

    def update_file(self):
        self.trading_data['currentOrders'] = self.current_orders
        self.trading_data['capital'] = self.capital
        self.trading_data['tradeHistory'] = self.trade_history
        self.trading_data['creation_date'] = self.creation_date
        self.trading_data['fees_to_cover'] = self.fees_to_cover
        self.trading_data['free_slots'] = self.free_slots
        self.trading_data['reserved_amount'] = self.reserved_amount
        self.save_trading_data()

    def extract_min_order_value(self, filters):
        for filter in filters:
            if filter['filterType'] == 'NOTIONAL':
                return float(filter['minNotional'])
        return -1

    def respected_gap(self):
        # Vérifie si le gap est respecté pour tous les trades
        for order in self.current_orders:
            if order['status'] != 'buy_in_progress' and self.current_price >= order['detected_price'] or (
                    order['detected_price'] - self.current_price) < self.respected_gap_value:
                return False
        return True

    def handle_order_monitoring(self, message):
        for order in self.current_orders:
            if order['id'] == message['i'] or order.get('sale_order_id', None) == message['i']:
                status = message['X']
                if status == 'FILLED':
                    if message['S'] == 'BUY':
                        self.update_buy_order(message, order)
                    elif message['S'] == 'SELL':
                        self.update_sale_order(message, order)

        print('handle_order_monitoring executed')

    def update_buy_order(self, message, order):
        order['cost'] = Decimal(message['Z'])
        order['buy_commission'] = Decimal(message['n'])
        order['quantity'] = Decimal(message['z'])
        order['buy_price'] = order['cost'] / Decimal(message['z'])
        order['buy_fee'] = order['buy_commission'] * order['buy_price']

        order['max_price'] = order['buy_price']
        order['stop_loss_price'] = order['buy_price'] * (Decimal('1') - self.stop_loss_percentage)
        order['secured'] = False
        order['status'] = 'open'
        self.reserved_amount -= order['reserved_amount']
        self.update_capital('buy', order['cost'])
        self.update_file()

    def update_sale_order(self, message, order):

        order['sailed_quantity'] = Decimal(message['z'])
        order['closed_at'] = get_current_date()
        order['sale_price'] = Decimal(message['L'])
        start_datetime = datetime.strptime(order['opened_at'], "%d/%m/%YT%H:%M")
        order['duration'] = compute_duration_until_now(start_datetime)
        order['sale_timestamp'] = time.time()
        order['sale_fee'] = Decimal(message['Z']) * self.trading_fee_percentage
        order['profit'] = Decimal(message['Z']) - order['cost'] - order['sale_fee'] - self.fees_to_cover
        order['cumulative_coin_quantity'] = order['quantity'] - Decimal('0.0001')
        order['status'] = 'closed'
        self.update_capital(action='sell', total=Decimal(message['Z']) - order['sale_fee'])
        self.trade_history.append(order)
        self.current_orders.remove(order)
        self.update_file()

    def update_capital(self, action, total):

        if action == 'buy':
            self.capital -= total
        elif action == 'sell':
            self.capital += total

    def limit_reached(self):
        return len(self.current_orders) >= 10

    def compute_potential_profit_loss(self, order, current_price=None):
        if not order:
            return Decimal('0')
        if current_price is None:
            if self.current_price is None:
                return None
            current_price = self.current_price
        total_sale = current_price * Decimal('0.0001')
        sale_fee = total_sale * self.trading_fee_percentage
        potential_profit_loss = total_sale - order['cost'] - sale_fee - self.fees_to_cover
        return potential_profit_loss

    def buy_fees(self):
        try:
            quantity = Decimal('0.0000001') * Decimal('1000')
            order = self.client.new_order(
                symbol=self.symbol,
                side='BUY',
                type='MARKET',
                quantity=str(quantity)
            )

            fills = order.get('fills', [])
            total_cost = Decimal('0')
            for fill in fills:
                price = Decimal(fill['price'])
                qty = Decimal(fill['qty'])
                total_cost += price * qty
            self.free_slots = 999
            self.fees_to_cover = total_cost / self.free_slots
            logging.info(f'fees to cover {self.fees_to_cover}')
            self.capital -= total_cost
            self.update_file()
            logging.info('Fees bought')
        except Exception as e:
            logging.error(f"Error placing buy order: {e}")

    def synchronize_orders(self):

        for order in self.current_orders:
            if order['status'] == 'sale_in_progress':
                remote_order = self.client.get_order(symbol=self.symbol, orderId=order['id'])
                if remote_order['status'] == 'FILLED':
                    order['sailed_quantity'] = Decimal(remote_order['executedQty'])
                    order['closed_at'] = get_current_date()
                    order['sale_price'] = Decimal(remote_order['price'])
                    start_datetime = datetime.strptime(order['opened_at'], "%d/%m/%YT%H:%M")
                    order['duration'] = compute_duration_until_now(start_datetime)
                    order['sale_timestamp'] = time.time()
                    order['sale_fee'] = Decimal(remote_order['cummulativeQuoteQty']) * self.trading_fee_percentage
                    order['profit'] = Decimal(remote_order['cummulativeQuoteQty']) - order['cost'] - order[
                        'sale_fee'] - self.fees_to_cover
                    order['status'] = 'closed'
                    self.update_capital(action='sell',
                                        total=Decimal(remote_order['cummulativeQuoteQty']) - order['sale_fee'])
                    self.trade_history.append(order)
                    self.current_orders.remove(order)
                    self.update_file()

