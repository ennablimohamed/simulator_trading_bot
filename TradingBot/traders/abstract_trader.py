import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal, ROUND_DOWN

from encoders.DecimalEncoder import DecimalEncoder

BINANCE_ORDER_BOOK_URL = "https://api.binance.com/api/v3/depth"


class AbstractTrader(ABC):

    def __init__(self, trader_id, symbol, capital, trade_capital_percentage, name, trader_updates_queue):
        self.trader_id = trader_id
        self.symbol = symbol
        self.current_price = None
        self.trade_history = []
        self.capital = capital
        self.trade_capital_percentage = trade_capital_percentage
        self.trading_fee_percentage = Decimal('0.001')
        self.trading_data = None
        self.name = name
        self.file_name = 'data/' + self.trader_id.replace(' ', '_') + '_trader.json'
        self.load_or_create_trading_file()
        self.trader_updates_queue = trader_updates_queue

    def calculate_order_size(self):

        trade_value = self.capital * self.trade_capital_percentage
        if self.current_price and self.current_price > Decimal('0'):
            size = (trade_value / self.current_price).quantize(Decimal('0.00001'), rounding=ROUND_DOWN)
            return size
        return Decimal('0')

    def update_capital_after_trade(self, action, order_price, quantity):

        if action == 'buy':
            total_cost = (order_price * quantity) * (Decimal('1') + self.trading_fee_percentage)
            self.capital -= total_cost
        elif action == 'sell':
            total_revenue = (order_price * quantity) * (Decimal('1') - self.trading_fee_percentage)
            self.capital += total_revenue

    def handle_ticker_message(self, message):
        last_price = Decimal(message['p'])
        if last_price != self.current_price:
            self.current_price = last_price
            self.handle_trading_logic()

    @abstractmethod
    def handle_trading_logic(self):
        pass

    @abstractmethod
    def init_data(self):
        pass

    @abstractmethod
    def compute_analytics(self):
        pass

    @abstractmethod
    def compute_potential_profit_loss(self, order):
        pass

    def load_or_create_trading_file(self):
        if os.path.exists(self.file_name):
            with open(self.file_name, 'r') as file:
                self.trading_data = json.load(file, parse_float=Decimal)
                self.init_data()

    def save_trading_data(self):
        message = {'file_name': self.file_name, 'content': self.trading_data}
        self.trader_updates_queue.put_nowait(message)
