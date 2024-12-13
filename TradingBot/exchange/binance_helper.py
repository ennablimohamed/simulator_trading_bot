import logging
from decimal import Decimal

import requests
from sortedcontainers import SortedDict

DEPTH_SUFFIX = '/api/v3/depth'


def initialize_order_book(base_url, symbol, limit=1000):
    params = {
        'symbol': symbol,
        'limit': limit
    }
    try:
        url = base_url + DEPTH_SUFFIX
        response = requests.get(url, params=params)
        if response.status_code == 200:
            depth = response.json()
            order_book = {'bids': SortedDict({Decimal(bid[0]): Decimal(bid[1]) for bid in depth['bids']}),
                          'asks': SortedDict({Decimal(ask[0]): Decimal(ask[1]) for ask in depth['asks']})}
            return order_book
        else:
            logging.error(f"Error fetching order book for {symbol}: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logging.error("Error occurred when initializing_order_book")
        return None
