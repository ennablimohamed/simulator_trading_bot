import logging
import queue
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

import pandas as pd
from binance.spot import Spot

from date.date_util import get_current_date, compute_duration_until_now
from traders.abstract_trader import AbstractTrader





class BollingerReverseMeanTrader(AbstractTrader):

    def __init__(self, trader_id, symbol, capital, trade_capital_percentage, api_config):
        super().__init__(trader_id,
                         symbol,
                         capital,
                         trade_capital_percentage,
                         name='BollingerReverseMeanTrader',
                         trader_updates_queue=None)
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
                'reserved_amount': 0}
        self.stop_loss_percentage = Decimal('0.05')
        self.api_config = api_config
        # Initialize Binance client with API keys from environment variables
        api_key = api_config['credentials']['api-key']  # os.getenv('BINANCE_API_KEY')
        api_secret = api_config['credentials']['secret']  # os.getenv('BINANCE_API_SECRET')
        self.client = Spot(api_key=api_key, api_secret=api_secret, base_url=api_config['trades']['base-url'])
        self.reserved_amount = Decimal(self.trading_data['reserved_amount'])
        self.fees_to_cover = Decimal(self.trading_data['fees_to_cover'])
        self.free_slots = self.trading_data['free_slots']
        self.current_orders = []
        self.order_queue = queue.Queue(maxsize=1000)
        self.queue = queue.Queue(maxsize=1000)
        self.synchronize_orders()

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

    def process_update(self, data):
        klines = self.compute_klines(data)
        bollinger_data = self.calculate_bollinger_bands(klines, window=20, num_std=2)
        conditions_satisfied = self.check_bollinger_conditions(bollinger_data)
        if conditions_satisfied:
            print('condition satisfied')
        if conditions_satisfied and len(self.current_orders) == 0:
            if self.free_slots == 0:
                print('Buying fees')
                self.buy_fees()
            print('Buying order')
            self.buy_order()

    def compute_klines(self, data):
        columns = [
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'trades',
            'taker_base_vol', 'taker_quote_vol', 'ignore'
        ]
        data = pd.DataFrame(data, columns=columns)

        # Convert relevant columns to numeric
        for col in ['open', 'high', 'low', 'close', 'volume']:
            data[col] = pd.to_numeric(data[col])

        # Use timestamp as datetime index
        data['timestamp'] = pd.to_datetime(data['timestamp'], unit='ms')
        data.set_index('timestamp', inplace=True)

        return data[['open', 'high', 'low', 'close', 'volume']]

    def check_bollinger_conditions(self, data: pd.DataFrame) -> bool:
        """
        Checks if the following conditions are met on the last 3 candles:
        1. The first candle opens above the lower Bollinger band and closes below it.
        2. The second candle opens below the lower Bollinger band and closes above it.
        3. The third candle opens at or above the close of the second candle and closes above the close of the second candle.
        :param data: DataFrame containing Bollinger Bands and candlestick data.
        :return: True if all conditions are met, otherwise False.
        """
        # Get the last 3 candlesticks
        last_3 = data.tail(3)

        if len(last_3) < 3:
            return False  # Not enough data to evaluate conditions

        # Assign the 3 candles to variables
        candle1, candle2, candle3 = last_3.iloc[0], last_3.iloc[1], last_3.iloc[2]

        # Condition 1: First candle
        condition1 = (
                candle1['open'] > candle1['Lower_Band'] > candle1['close']
        )

        # Condition 2: Second candle
        condition2 = (
                candle2['open'] < candle2['Lower_Band'] < candle2['close']
        )

        # Condition 3: Third candle
        condition3 = (
                candle3['open'] >= candle2['close'] and
                candle3['close'] > candle2['close']
        )

        # Return True if all conditions are met
        return condition1 and condition2 and condition3

    def calculate_bollinger_bands(self, data: pd.DataFrame, window: int = 20, num_std: int = 2):
        """
        Calculates Bollinger Bands for a given DataFrame.
        :param data: DataFrame containing 'close' prices.
        :param window: Window size for moving average.
        :param num_std: Number of standard deviations for bands.
        :return: DataFrame with Bollinger Bands.
        """
        data['MA'] = data['close'].rolling(window=window).mean()
        data['STD'] = data['close'].rolling(window=window).std()
        data['Upper_Band'] = data['MA'] + (data['STD'] * num_std)
        data['Lower_Band'] = data['MA'] - (data['STD'] * num_std)
        return data

    def update_file(self):
        self.trading_data['currentOrders'] = self.current_orders
        self.trading_data['capital'] = self.capital
        self.trading_data['tradeHistory'] = self.trade_history
        self.trading_data['creation_date'] = self.creation_date
        self.trading_data['fees_to_cover'] = self.fees_to_cover
        self.trading_data['free_slots'] = self.free_slots
        self.trading_data['reserved_amount'] = self.reserved_amount
        self.save_trading_data()

    def update_capital(self, action, total):

        if action == 'buy':
            self.capital -= total
        elif action == 'sell':
            self.capital += total

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
        if 'support' in order:
            order['support'] = Decimal(order['support'])
        if 'support_volume' in order:
            order['support_volume'] = Decimal(order['support_volume'])
        if 'capital' in order:
            order['capital'] = Decimal(order['capital'])
        if 'detected_price' in order:
            order['detected_price'] = Decimal(order['detected_price'])
        if 'buy_commission' in order:
            order['buy_commission'] = Decimal(order['buy_commission'])

    def handle_trading_logic(self):
        pass

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

    # Extract order details

    def buy_order(self):
        try:
            quantity = Decimal('0.0001')
            order = self.client.new_order(
                symbol=self.symbol,
                side='BUY',
                type='MARKET',
                quantity=str(quantity)
            )
            order_id = order['orderId']
            order_reserved_amount = self.current_price * quantity
            new_order = {
                'id': order_id,
                'opened_at': get_current_date(),
                'detected_price': self.current_price,
                'status': 'buy_in_progress',
                'secured': False,
                'reserved_amount': order_reserved_amount
            }
            self.free_slots -= 1
            self.reserved_amount += order_reserved_amount
            self.current_orders.append(new_order)
            self.update_file()
        except Exception as e:
            logging.error(f"Error placing buy order: {e}")

    def handle_order_monitoring(self, message):
        for order in self.current_orders:
            if order['id'] == message['i'] or order.get('sale_order_id', None) == message['i']:
                status = message['X']
                if status == 'FILLED':
                    if message['S'] == 'BUY':
                        self.update_buy_order(message, order)

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

    def handle_depth_message(self, message):
        pass