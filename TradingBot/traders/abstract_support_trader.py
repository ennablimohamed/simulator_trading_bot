import queue
from abc import ABC
from decimal import Decimal

from traders.abstract_trader import AbstractTrader


class AbstractSupportTrader(AbstractTrader, ABC):

    def __init__(self, trader_id, symbol, capital, trade_capital_percentage, order_book, name, trader_updates_queue, target_volume, respected_gap_value):
        super().__init__(trader_id=trader_id, symbol=symbol, capital=capital, trade_capital_percentage=trade_capital_percentage, name=name, trader_updates_queue=trader_updates_queue)
        self.order_book = order_book
        self.support = {'value': None, 'volume': None, 'index': None}
        self.resistance = None
        self.respected_gap_value = Decimal(respected_gap_value)
        self.target_volume = Decimal(target_volume)
        self.volume_threshold = Decimal('0.7') * self.target_volume
        self.queue = queue.Queue(maxsize=1000)
        self.order_queue = queue.Queue(maxsize=1000)

    def compute_support(self):
        if self.order_book['bids'] is not None:
            for price, qty in reversed(self.order_book['bids'].items()):
                if qty >= Decimal('0.7') * self.target_volume:
                    return price, qty
        return None, None

    def compute_resistance(self):
        for price, qty in self.order_book['asks'].items():
            if qty >= Decimal('0.7') * self.target_volume:
                return price
        return None

    def handle_depth_message(self, message):
        self.update_support(message)
        self.update_resistance(message)
        self.handle_trading_logic()

    def update_resistance(self, message):
        potential_resistance = self.resistance
        for ask in message['a']:
            price, qty = Decimal(ask[0]), Decimal(ask[1])
            if qty == Decimal('0'):
                if price == self.resistance:
                    self.resistance = None
                if price in self.order_book['asks']:
                    self.order_book['asks'].pop(price, None)
            else:
                self.order_book['asks'][price] = qty
                if self.resistance is not None and price < potential_resistance and qty >= self.volume_threshold:
                    potential_resistance = price
        while len(self.order_book['asks']) > 5000:
            self.order_book['asks'].popitem(-1)
        if self.resistance is None:
            self.resistance = self.compute_resistance()
        else:
            self.resistance = potential_resistance

    def update_support(self, message):
        potential_support = self.support['value'] if self.support is not None else None
        potential_volume = self.support['volume'] if self.support is not None else None
        for bid in message['b']:
            price, qty = Decimal(bid[0]), Decimal(bid[1])
            if qty == Decimal('0'):
                if price == self.support:
                    self.reset_support()
                if price in self.order_book['bids']:
                    self.order_book['bids'].pop(price, None)
            else:
                self.order_book['bids'][price] = qty
                if self.support is not None and potential_support is not None and price > potential_support and qty >= self.volume_threshold:
                    potential_support = price
                    potential_volume = qty
        if self.support['value'] is None or (
                potential_support is not None and self.order_book['bids'].get(potential_support) is None):
            support, volume = self.compute_support()
            self.support['value'] = support
            self.support['volume'] = volume
        else:
            self.support['value'] = potential_support
            self.support['volume'] = potential_volume
        self.support['index'] = len(self.order_book['bids']) - self.order_book['bids'].index(
            self.support['value']) + 1 if self.support['value'] is not None else None
        while len(self.order_book['bids']) > 5000:
            self.order_book['bids'].popitem(0)

    def reset_support(self):
        self.support = {'value': None, 'volume': None, 'index': None}
