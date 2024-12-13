import copy
import logging
import os
import queue
import signal
import threading
from collections import deque
from decimal import Decimal
from logging.handlers import RotatingFileHandler

from config.config_util import load_current_config
from exchange.binance_helper import initialize_order_book
from traders.FundingRateTrader import FundingRateTrader
from traders.SecuredCapitalTrader import SecuredCapitalTrader
from traders.TraderManager import TraderManager
from traders.abstract_support_trader import AbstractSupportTrader
from traders.bollinger_original_reverse_mean_trader import BollingerOriginalReverseMeanTrader
from traders.bollinger_reverse_mean_trader import BollingerReverseMeanTrader
from traders.min_max_secured_capital_trader import MinMaxSecuredCapitalTrader
from traders.min_max_trader import MinMaxTrader
from traders.real_secured_capital_trader import RealSecuredCapitalTrader
from trading_bot_data import TradingBotData
from ui.app_manager import AppManager
from ui.traders.MinMaxSupportTraderTabManager import MinMaxSupportTraderTabManager

trading_bot_data = None
trader_manager = None
app_manager = None
app = None
traders_locks = {}


def stop_handler(sig, frame):
    global trader_manager
    trader_manager.save_files()


def init_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    handler = RotatingFileHandler('trading_bot.log', maxBytes=5 * 1024 * 1024,
                                  backupCount=5)  # 5MB par fichier, 5 fichiers de sauvegarde
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    os.environ['DASH_DEBUG'] = '0'


def init_data():
    global trading_bot_data
    logging.info('Initializing order book...')
    trading_bot_data = TradingBotData()


def init_order_book(config, symbol):
    base_url = config['api']['base-url']
    trading_config = config['trading']
    order_book_config = trading_config['order-book']
    order_book_limit = order_book_config['limit']
    return initialize_order_book(base_url=base_url, symbol=symbol, limit=order_book_limit)


def init_app():
    global app, app_manager, trading_bot_data
    app_manager = AppManager('Trading Bot Simulator', trading_bot_data)
    app = app_manager.create_app()
    threading.Thread(target=app.run_server, kwargs={'debug': False, 'use_reloader': False, 'port': 8065}).start()


def init_trader(config, trader_id, trader_config, capital, trade_capital_percentage, trader_update_queue):
    global trading_bot_data
    trader_type = trader_config['type']
    symbol = trader_config['symbol']
    order_book_data = init_order_book(config, symbol)
    if trader_type == 'SecuredCapitalTrader':
        order_book = copy.deepcopy(order_book_data)
        target_volume = trader_config['target-volume']
        respected_gap_value = trader_config['respected-gap-value']
        return SecuredCapitalTrader(
            trader_id=trader_id,
            symbol=symbol,
            capital=capital,
            trade_capital_percentage=trade_capital_percentage,
            order_book=order_book,
            trader_updates_queue=trader_update_queue,
            target_volume=target_volume,
            respected_gap_value=respected_gap_value
        )
    elif trader_type == 'RealSecuredCapitalTrader':
        order_book = copy.deepcopy(order_book_data)
        target_volume = trader_config['target-volume']
        respected_gap_value = trader_config['respected-gap-value']
        return RealSecuredCapitalTrader(
            trader_id=trader_id,
            symbol=symbol,
            capital=capital,
            trade_capital_percentage=trade_capital_percentage,
            order_book=order_book,
            trader_updates_queue=trader_update_queue,
            target_volume=target_volume,
            respected_gap_value=respected_gap_value,
            api_config=config['api']
        )
    elif trader_type == 'MinMaxSecuredCapitalTrader':
        order_book = copy.deepcopy(order_book_data)
        target_volume = trader_config['target-volume']
        respected_gap_value = trader_config['respected-gap-value']
        return MinMaxSecuredCapitalTrader(
            trader_id=trader_id,
            symbol=symbol,
            capital=capital,
            trade_capital_percentage=trade_capital_percentage,
            order_book=order_book,
            trader_updates_queue=trader_update_queue,
            target_volume=target_volume,
            respected_gap_value=respected_gap_value,
            api_config=config['api']
        )
    elif trader_type == 'MinMaxTrader':
        order_book = copy.deepcopy(order_book_data)
        target_volume = trader_config['target-volume']
        respected_gap_value = trader_config['respected-gap-value']
        return MinMaxTrader(
            trader_id=trader_id,
            symbol=symbol,
            capital=capital,
            trade_capital_percentage=trade_capital_percentage,
            order_book=order_book,
            trader_updates_queue=trader_update_queue,
            target_volume=target_volume,
            respected_gap_value=respected_gap_value,
            api_config=config['api']
        )
    elif trader_type == 'FundingRateTrader':
        return FundingRateTrader(
            trader_id=trader_id,
            symbol=symbol,
            capital=capital,
            trade_capital_percentage=trade_capital_percentage,
            trader_updates_queue=trader_update_queue)
    elif trader_type == 'BollingerReverseMeanTrader':
        return BollingerReverseMeanTrader(
            trader_id=trader_id,
            symbol=symbol,
            capital=capital,
            trade_capital_percentage=100,
            api_config=config['api'])
    elif trader_type == 'BollingerOriginalReverseMeanTrader':
        return BollingerOriginalReverseMeanTrader(
            trader_id=trader_id,
            symbol=symbol,
            capital=capital,
            trade_capital_percentage=100,
            api_config=config['api'])
    return None


def init_traders(config):
    global trading_bot_data, trader_manager, traders_locks
    trading_config = config['trading']
    capital = Decimal(trading_config['capital'])
    websocket_base_url = config['api']['websocket-base-url']
    trade_capital_percentage = Decimal(trading_config['trade-capital-percentage'])

    support_active_traders = trading_config['traders']
    queues = {}
    traders = []
    trading_bot_data.traders = {}
    trader_update_queue = queue.Queue(maxsize=1000)
    symbols = []
    for trader_entry in support_active_traders:
        trader_id, trader_config = next(iter(trader_entry.items()))
        trading_bot_data.analytics_data[trader_id] = {'potential_profit_loss_history': deque(maxlen=1000),
                                                      'total_profit_loss_history': deque(maxlen=1000)}
        traders_locks[trader_id] = threading.Lock()
        trader = init_trader(config, trader_id, trader_config, capital, trade_capital_percentage, trader_update_queue)
        traders.append(trader)
        trading_bot_data.traders[trader_id] = {'instance': trader, 'lock': traders_locks[trader_id]}
        if isinstance(trader, AbstractSupportTrader) or isinstance(trader, BollingerReverseMeanTrader) or isinstance(trader, BollingerOriginalReverseMeanTrader):
            if queues.get(trader.symbol):
                queues[trader.symbol].append(trader.queue)
            else:
                queues[trader.symbol] = [trader.queue]
        if trader.symbol not in symbols:
            symbols.append(trader.symbol)
    trader_manager = TraderManager(
        queues=queues,
        websocket_url=websocket_base_url,
        trading_bot_data=trading_bot_data,
        traders_locks=traders_locks,
        traders=traders,
        trader_updates_queue=trader_update_queue,
        symbols=symbols,
        api_config=config['api']
    )


def start():
    global trader_manager
    try:
        init_logger()
        logging.info('Loading config from environment...')
        config = load_current_config()
        logging.info('Initializing data...')
        init_data()
        logging.info('Initializing traders')
        init_traders(config)
        logging.info('Initializing app')
        init_app()
        trader_manager.start()
    except Exception as e:
        logging.error("start : An error occured")


signal.signal(signal.SIGINT, stop_handler)
signal.signal(signal.SIGTERM, stop_handler)
if __name__ == '__main__':
    start()
