import time
import uuid
from abc import ABC
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
import pandas as pd

import requests
from date.date_util import get_current_date
from traders.abstract_trader import AbstractTrader


class FundingRateTrader(AbstractTrader):

    def handle_trading_logic(self):
        pass

    def __init__(self, trader_id, symbol, capital, trade_capital_percentage, trader_updates_queue):
        super().__init__(
            trader_id=trader_id,
            symbol=symbol,
            capital=capital,
            trade_capital_percentage=trade_capital_percentage,
            name="Funding Rate Trader",
            trader_updates_queue=trader_updates_queue)
        self.current_orders = []
        self.funding_rate_threshold = Decimal('-0.5')
        self.funding_rate = Decimal('0')
        self.creation_date = datetime.utcnow().strftime("%d/%m/%YT%H:%M")
        self.trading_data = {
            'currentOrders': [],
            'capital': self.capital,
            'tradeHistory': [],
            'creation_date': self.creation_date
        }

    def get_price_data(self, interval='1m', limit=100):
        url = "https://fapi.binance.com/fapi/v1/klines"
        params = {
            "symbol": self.symbol,
            "interval": interval,
            "limit": limit
        }
        response = requests.get(url, params=params)
        data = response.json()

        # Construire un DataFrame pour les prix de clôture
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', '_', '_', '_', '_', '_', '_'
        ])
        df['close'] = df['close'].astype(float)
        return df

    def compute_bollinger_bands(self, data, period=20, std_dev=2):
        # Calculer la moyenne mobile simple (SMA) et l'écart type
        data['middle_band'] = data['close'].rolling(window=period).mean()
        data['std_dev'] = data['close'].rolling(window=period).std()

        # Calculer les bandes supérieure et inférieure de Bollinger
        data['upper_band'] = data['middle_band'] + (std_dev * data['std_dev'])
        data['lower_band'] = data['middle_band'] - (std_dev * data['std_dev'])
        return data

    def start(self):
        self.check_strategy()
        time.sleep(60)

    def place_buy_order(self):
        order_size = self.calculate_order_size()
        if order_size > Decimal('0'):
            base_cost = self.current_price * order_size
            buy_fee = base_cost * self.trading_fee_percentage
            cost = base_cost + buy_fee
            new_order = {
                'id': str(uuid.uuid4()),
                'cost': cost,
                'opened_at': get_current_date(),
                'buy_price': self.current_price,
                'quantity': order_size,
                'buy_fee': buy_fee,
                'status': 'open',
            }
            self.current_orders.append(new_order)
            self.update_capital_after_trade('buy', self.current_price, order_size)
            self.update_file()

    def check_strategy(self):
        funding_rate = self.get_funding_rate()
        self.funding_rate = funding_rate
        print(f"Funding rate: {funding_rate}")
        self.current_price = self.get_futures_price()
        if funding_rate >= self.funding_rate_threshold:
            data = self.get_price_data()
            data = self.compute_bollinger_bands(data)

            if (data['close'].iloc[-2] < data['lower_band'].iloc[-2]) and (
                    data['close'].iloc[-1] > data['lower_band'].iloc[-1]):
                self.place_buy_order()

    def get_futures_price(self):
        url = "https://fapi.binance.com/fapi/v1/ticker/price"
        params = {"symbol": self.symbol}
        response = requests.get(url, params=params)
        data = response.json()
        return float(data['price'])

    def get_funding_rate(self):
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        params = {"symbol": self.symbol}
        response = requests.get(url, params=params)
        data = response.json()
        return Decimal(data["lastFundingRate"]) * 100

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
        buy_fee = order['buy_fee']
        sell_fee = current_price * self.trading_fee_percentage * order['quantity']
        potential_profit_loss = (current_price - order['buy_price']) * order['quantity'] - buy_fee - sell_fee
        return potential_profit_loss

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

    def compute_potential_total_profit_loss(self):
        total_profit_loss = Decimal('0')
        # Add realized profit/loss from trade history
        for trade in self.trade_history:
            total_profit_loss += trade['profit']
        # Add unrealized profit/loss from open trades
        for trade in self.current_orders:
            potential_profit_loss = self.compute_potential_profit_loss(trade)
            if potential_profit_loss is not None:
                total_profit_loss += potential_profit_loss
        return total_profit_loss

    def compute_daily_profits(self):
        daily_profits = defaultdict(Decimal)  # Initialisation avec valeur par défaut de 0.0 pour chaque clé

        for order in self.trade_history:
            day = datetime.strptime(order['closed_at'], "%d/%m/%YT%H:%M").date()
            day = day.strftime("%d/%m/%Y")
            daily_profits[day] += order['profit']
        if len(daily_profits) == 0:
            return {datetime.now().date(): 0}
        # Convertir le defaultdict en dictionnaire classique pour le retour
        return dict(daily_profits)

    def update_file(self):
        self.trading_data['currentOrders'] = self.current_orders
        self.trading_data['capital'] = self.capital
        self.trading_data['tradeHistory'] = self.trade_history
        self.trading_data['creation_date'] = self.creation_date
        self.save_trading_data()
