import asyncio
import json
import logging
import queue
import threading
import time
from decimal import Decimal

import requests
import websockets

from encoders.DecimalEncoder import DecimalEncoder
from traders.FundingRateTrader import FundingRateTrader
from traders.abstract_support_trader import AbstractSupportTrader
from traders.bollinger_original_reverse_mean_trader import BollingerOriginalReverseMeanTrader
from traders.bollinger_reverse_mean_trader import BollingerReverseMeanTrader


class TraderManager:

    def __init__(self, queues, websocket_url, trading_bot_data, traders_locks, traders, trader_updates_queue, symbols,
                 api_config):
        self.symbols = symbols
        self.websocket_url = websocket_url
        self.queues = queues
        self.trading_bot_data = trading_bot_data
        self.traders = traders
        self.order_queues = self.fill_order_queues()
        self.started = False
        self.threads = []
        self.stop_event = threading.Event()
        self.traders_locks = traders_locks
        self.trader_updates_queue = trader_updates_queue
        self.api_config = api_config

    def __add_websocket_handler(self, websocket_url):

        def run():
            asyncio.set_event_loop(asyncio.new_event_loop())
            loop = asyncio.get_event_loop()
            loop.run_until_complete(handler())

        async def handler():
            while True:
                try:
                    async with websockets.connect(websocket_url) as websocket:
                        logging.info(f'Connected to WebSocket {websocket_url}')
                        while True:
                            message = await websocket.recv()
                            if isinstance(message, bytes):
                                await websocket.pong(message)
                            else:
                                data = json.loads(message)
                                payload = data['data']
                                valid_message = False
                                s = payload['s']
                                if payload['e'] == 'trade':
                                    received_price = Decimal(payload['p'])
                                    threshold = Decimal('0.01')
                                    if self.trading_bot_data.last_price.get(s) is None:
                                        self.trading_bot_data.last_price[s] = received_price
                                    elif received_price != self.trading_bot_data.last_price[s] and (
                                            (received_price > (self.trading_bot_data.last_price[s] + threshold)) or (
                                            received_price < (self.trading_bot_data.last_price[s] - threshold))):
                                        self.trading_bot_data.last_price[s] = received_price
                                        valid_message = True
                                elif payload['e'] == 'depthUpdate':
                                    valid_message = True
                                if valid_message and self.queues is not None and len(self.queues) > 0:
                                    for q in self.queues[s]:
                                        print(f'queue size : {q.qsize()}')
                                        try:
                                            q.put_nowait(payload)
                                        except queue.Full:
                                            logging.warning("Queue full. Dropping message.")
                except (websockets.ConnectionClosedError, websockets.ConnectionClosed):
                    logging.error(f"Connection lost. Try to reconnect")
                    await asyncio.sleep(5)
                except Exception as e:
                    logging.error(f"Unexpected error occurred", exc_info=True)
                    await asyncio.sleep(5)

        threading.Thread(target=run, daemon=True).start()

    def start(self):
        logging.info('start : Starting Trade Manager')

        if self.started:
            return
        else:
            listen_key = self.create_listen_key()
            self.monitor_orders(listen_key=listen_key)
            for symbol in self.symbols:
                lower_symbol = symbol.lower()
                websocket_url = self.websocket_url + '/stream?streams=' + lower_symbol + '@depth@100ms/' + lower_symbol + '@trade'
                self.__add_websocket_handler(websocket_url)
            self.__init_traders_threads()
            for t in self.threads:
                t.join()

    def __init_traders_threads(self):
        t_save_traders = threading.Thread(
            target=self.save_trader,
            args=(self.trader_updates_queue, self.stop_event),
            daemon=True)
        t_save_traders.start()
        self.threads.append(t_save_traders)
        for trader in self.traders:
            if isinstance(trader, AbstractSupportTrader) or isinstance(trader, BollingerReverseMeanTrader) or isinstance(trader, BollingerOriginalReverseMeanTrader):
                t = threading.Thread(
                    target=self.process_strategy_messages,
                    args=(
                        trader, self.traders_locks[trader.trader_id], trader.queue,
                        self.stop_event),
                    daemon=True
                )
                t.start()
                self.threads.append(t)
                order_t = threading.Thread(
                    target=self.process_order_messages,
                    args=(
                        trader, self.traders_locks[trader.trader_id], trader.order_queue,
                        self.stop_event),
                    daemon=True
                )
                order_t.start()
                self.threads.append(order_t)
            elif isinstance(trader, FundingRateTrader):
                t = threading.Thread(
                    target=self.process_funding_rate_trader,
                    args=(
                        trader, self.stop_event),
                    daemon=True
                )
                t.start()
                self.threads.append(t)
            if isinstance(trader, BollingerReverseMeanTrader) or isinstance(trader, BollingerOriginalReverseMeanTrader):
                t = threading.Thread(
                    target=self.process_klines_update,
                    args=(
                        trader, self.stop_event),
                    daemon=True
                )
                t.start()
                self.threads.append(t)

    def process_funding_rate_trader(self, trader, stop_event):
        while True:
            trader.check_strategy()
            time.sleep(60)

    def process_order_messages(self, trader, lock, q, stop_event):
        while not stop_event.is_set():
            try:
                message = q.get(timeout=1)
                if message is None:
                    break
                with lock:
                    if message['e'] == 'executionReport':
                        trader.handle_order_monitoring(message)
                q.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Error processing message for {trader.symbol}: {e}", exc_info=True)
                q.task_done()

    def process_strategy_messages(self, trader, lock, q, stop_event):

        while not stop_event.is_set():
            try:
                message = q.get(timeout=1)
                if message is None:
                    break
                with lock:
                    if message['e'] == 'depthUpdate':
                        trader.handle_depth_message(message)
                    elif message['e'] == 'trade':
                        trader.handle_ticker_message(message)
                    elif message['e'] == 'executionReport':
                        trader.handle_order_monitoring(message)
                q.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Error processing message for {trader.symbol}: {e}", exc_info=True)
                q.task_done()

    def save_trader(self, q, stop_event):
        while not stop_event.is_set():
            try:
                trader_update = q.get(timeout=1)
                if trader_update is None:
                    break
                file_name = trader_update['file_name']
                content = trader_update['content']
                with open(file_name, 'w') as file:
                    json.dump(content, file, cls=DecimalEncoder)
                q.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Error saving trader update", exc_info=True)
                q.task_done()

    def save_files(self):
        for trader in self.traders:
            trader.update_file()

    def create_listen_key(self):

        url = self.api_config['trades']['base-url'] + '/api/v3/userDataStream'

        headers = {
            'X-MBX-APIKEY': self.api_config['credentials']['api-key']
        }

        response = requests.post(url, headers=headers)
        data = response.json()

        if response.status_code == 200:
            listen_key = data['listenKey']
            logging.info(f"Listen Key created : {listen_key}")
            return listen_key
        else:
            logging.error(f"Error while creating the listen key : {data}")
            return None

    def monitor_orders(self, listen_key):
        websocket_url = self.api_config['trades']['websocket-base-url'] + f"/ws/{listen_key}"

        def run():
            asyncio.set_event_loop(asyncio.new_event_loop())
            loop = asyncio.get_event_loop()
            loop.run_until_complete(handler())

        async def handler():
            while True:
                try:
                    async with websockets.connect(websocket_url) as websocket:
                        logging.info(f'Connected to WebSocket {websocket_url}')
                        while True:
                            message = await websocket.recv()
                            if isinstance(message, bytes):
                                await websocket.pong(message)
                            else:
                                data = json.loads(message)
                                for q in self.order_queues:
                                    print(f'queue size : {q.qsize()}')
                                    try:
                                        q.put_nowait(data)
                                    except queue.Full:
                                        logging.warning("Queue full. Dropping message.")
                except (websockets.ConnectionClosedError, websockets.ConnectionClosed):
                    logging.error(f"Connection lost. Try to reconnect")
                    await asyncio.sleep(5)
                except Exception as e:
                    logging.error(f"Unexpected error occurred", exc_info=True)
                    await asyncio.sleep(5)

        def keep_alive_listen_key(listen_key):
            """Maintenir le listenKey actif en le renouvelant toutes les 30 minutes."""
            url = self.api_config['trades']['base-url'] + '/api/v3/userDataStream'

            headers = {
                'X-MBX-APIKEY': self.api_config['credentials']['api-key']
            }

            params = {
                'listenKey': listen_key
            }

            while True:
                time.sleep(1800)
                response = requests.put(url, headers=headers, params=params)
                if response.status_code == 200:
                    logging.info("Listen Key renewed with success.")
                else:
                    logging.info(f"Error while renewing Listen Key : {response.json()}")

        monitor_orders_thread = threading.Thread(target=run, daemon=True)
        monitor_orders_thread.start()
        self.threads.append(monitor_orders_thread)
        renew_listen_key_thread = threading.Thread(target=keep_alive_listen_key, args=(listen_key,), daemon=True)
        renew_listen_key_thread.start()
        self.threads.append(renew_listen_key_thread)

    def fill_order_queues(self):
        order_queues = []
        for trader in self.traders:
            order_queues.append(trader.order_queue)
        return order_queues

    def process_klines_update(self, trader, stop_event):
        url = self.api_config['trades']['base-url'] + '/api/v3/klines'
        params = {
            'symbol': trader.symbol,
            'interval': '15m',
            'limit': 1000
        }
        while True:
            try:
                response = requests.get(url, params=params)
                trader.process_update(response.json())
            except Exception as e:
                logging.error('An error occureed while updqting klines')
            finally:
                time.sleep(60)
