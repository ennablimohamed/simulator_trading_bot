import json
import logging
from datetime import datetime
from decimal import Decimal

import dash
from dash import dcc, html, dash_table, Output, Input, MATCH
import dash_bootstrap_components as dbc
import plotly.graph_objs as go

from date.date_util import compute_duration_until_now
from traders.abstract_multi_trade_trader import AbstractMultiTradeTrader


class MinMaxSupportTraderTabManager:

    def __init__(self, app, trading_bot_data):
        self.app = app
        self.trading_bot_data = trading_bot_data
        self.app.callback(
            [
                Output({'type': 'min-max-support-box', 'index': MATCH}, 'children'),
                Output({'type': 'min-max-price-box', 'index': MATCH}, 'children'),
                Output({'type': 'min-max-resistance-box', 'index': MATCH}, 'children'),
                Output({'type': 'min-max-daily-profit', 'index': MATCH}, 'figure'),
                Output({'type': 'min-max-buy-orders-table', 'index': MATCH}, 'data'),
                Output({'type': 'min-max-trade-history-table', 'index': MATCH}, 'data'),
                Output({'type': 'min-max-potential-profit-loss-box', 'index': MATCH}, 'children'),
                Output({'type': 'min-max-script-runtime', 'index': MATCH}, 'children'),
                Output({'type': 'min-max-capital-box', 'index': MATCH}, 'children'),
                Output({'type': 'min-max-free-slots-box', 'index': MATCH}, 'children'),
                Output({'type': 'min-max-total-profit-loss-box', 'index': MATCH}, 'children'),
                Output({'type': 'min-max-min-price-box', 'index': MATCH}, 'children'),
                Output({'type': 'min-max-mid-price-box', 'index': MATCH}, 'children'),
                Output({'type': 'min-max-max-price-box', 'index': MATCH}, 'children'),

            ],
            [Input({'type': 'min-max-interval-component', 'index': MATCH}, 'n_intervals')]
        )(lambda n: self.update_trader_tab_content_layout(n))

    def generate_trader_tab_content(self, trader_name, symbol):
        return html.Div([
            html.H1(f"SUPPORT TRADER - {trader_name} {symbol}",
                    style={'textAlign': 'center', 'marginBottom': '30px'}),
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Execution time"),
                        dbc.CardBody([
                            html.H4(
                                id={'type': 'min-max-script-runtime', 'index': trader_name},
                                className='card-title',
                                children="Loading..."
                            ),
                        ])
                    ], color="dark", inverse=True)
                ], width=2),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Available capital"),
                        dbc.CardBody([
                            html.H4(id={'type': 'min-max-capital-box', 'index': trader_name}, className='card-title',
                                    children="Loading..."),
                        ])
                    ], color="orange", inverse=True)
                ], width=2),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Free slots"),
                        dbc.CardBody([
                            html.H4(id={'type': 'min-max-free-slots-box', 'index': trader_name}, className='card-title',
                                    children="Loading..."),
                        ])
                    ], color="#4287f5", inverse=True)
                ], width=2),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Potential Profit/Loss"),
                        dbc.CardBody([
                            html.H4(id={'type': 'min-max-potential-profit-loss-box', 'index': trader_name}, className='card-title',
                                    children="Loading..."),
                        ])
                    ], color="#4287f5", inverse=True)
                ], width=2),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Total Profit/Loss"),
                        dbc.CardBody([
                            html.H4(id={'type': 'min-max-total-profit-loss-box', 'index': trader_name}, className='card-title',
                                    children="Loading..."),
                        ])
                    ], color="#4287f5", inverse=True)
                ], width=2)
            ], justify='center', style={'marginBottom': '30px'}),
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Support"),
                        dbc.CardBody([
                            html.H4(id={'type': 'min-max-support-box', 'index': trader_name}, className='card-title',
                                    children="Loading..."),
                        ])
                    ], color="green", inverse=True)
                ], width=2),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Min Price"),
                        dbc.CardBody([
                            html.H4(id={'type': 'min-max-min-price-box', 'index': trader_name}, className='card-title',
                                    children="Loading..."),
                        ])
                    ], color="blue", inverse=True)
                ], width=2),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Mid Price"),
                        dbc.CardBody([
                            html.H4(id={'type': 'min-max-mid-price-box', 'index': trader_name}, className='card-title',
                                    children="Loading..."),
                        ])
                    ], color="blue", inverse=True)
                ], width=2),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Current Price"),
                        dbc.CardBody([
                            html.H4(id={'type': 'min-max-price-box', 'index': trader_name}, className='card-title',
                                    children="Loading..."),
                        ])
                    ], color="blue", inverse=True)
                ], width=2),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Max Price"),
                        dbc.CardBody([
                            html.H4(id={'type': 'min-max-max-price-box', 'index': trader_name}, className='card-title',
                                    children="Loading..."),
                        ])
                    ], color="blue", inverse=True)
                ], width=2),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Resistance"),
                        dbc.CardBody([
                            html.H4(id={'type': 'min-max-resistance-box', 'index': trader_name}, className='card-title',
                                    children="Loading..."),
                        ])
                    ], color="red", inverse=True)
                ], width=2)
            ], justify='center', style={'marginBottom': '15px'}),
            # Buy Orders Table
            dbc.Row([
                dbc.Col([
                    dcc.Graph(id={'type': 'min-max-daily-profit', 'index': trader_name})
                ], width=12)
            ]),
            html.Div([
                html.H4("Buy Orders"),
                dash_table.DataTable(
                    id={'type': 'min-max-buy-orders-table', 'index': trader_name},
                    columns=[
                        {'name': '#', 'id': 'id'},
                        {'name': 'Opened at', 'id': 'opened_at'},
                        {'name': 'Status', 'id': 'status'},
                        {'name': 'Support', 'id': 'support'},
                        {'name': 'Support-Volume', 'id': 'support_volume'},
                        {'name': 'Support-Index', 'id': 'support_index'},
                        {'name': 'Cost', 'id': 'cost'},
                        {'name': 'Buy-Price', 'id': 'buy_price'},
                        {'name': 'Quantity', 'id': 'quantity'},
                        {'name': 'Buy-Commission', 'id': 'buy_commission'},
                        {'name': 'Buy-Fee', 'id': 'buy_fee'},  # Nouvelle colonne pour les frais d'achat
                        {'name': 'Stop-Loss', 'id': 'stop_loss'},
                        {'name': 'Potential Profit/Loss', 'id': 'potential_profit_loss'},
                        {'name': 'Secured', 'id': 'secured'},
                    ],
                    data=[],
                    style_table={'overflowX': 'auto'},
                    style_cell={'textAlign': 'left'},
                    page_size=10
                )
            ]),
            # Trade History Table
            html.Div([
                html.H4("Trade History"),
                dash_table.DataTable(
                    id={'type': 'min-max-trade-history-table', 'index': trader_name},
                    columns=[
                        {'name': '#', 'id': 'id'},
                        {'name': 'Opened at', 'id': 'opened_at'},
                        {'name': 'Closed at', 'id': 'closed_at'},
                        {'name': 'Duration', 'id': 'duration'},
                        {'name': 'Profit', 'id': 'profit'},
                        {'name': 'Support', 'id': 'support'},
                        {'name': 'Support-Volume', 'id': 'support_volume'},
                        {'name': 'Support-Index', 'id': 'support_index'},
                        {'name': 'Cost', 'id': 'cost'},
                        {'name': 'Buy-Price', 'id': 'buy_price'},
                        {'name': 'Quantity', 'id': 'quantity'},
                        {'name': 'Buy-Fee', 'id': 'buy_fee'},  # Nouvelle colonne pour les frais d'achat
                        {'name': 'Stop-Loss', 'id': 'stop_loss'},
                        {'name': 'Secured', 'id': 'secured'},
                        {'name': 'Sale Price', 'id': 'sale_price'},
                        {'name': 'Sailed Quantity', 'id': 'sailed_quantity'},
                        {'name': 'Sale Fee', 'id': 'sale_fee'},

                    ],
                    data=[],
                    style_table={'overflowX': 'auto'},
                    style_cell={'textAlign': 'left'},
                    page_size=10
                )
            ]),
            dcc.Interval(id={'type': 'min-max-interval-component', 'index': trader_name}, interval=1000, n_intervals=0)
        ])

    def update_trader_tab_content_layout(self, n):
        try:
            fig_daily_profit = go.Figure()
            ctx = dash.callback_context
            if not ctx.triggered:
                return dash.no_update
            index = ctx.triggered[0]['prop_id'].split('.')[0]
            index = json.loads(index)
            strategy = index['index']

            trader_data = self.trading_bot_data.traders[strategy]
            trader = trader_data['instance']
            lock = trader_data['lock']
            min_price = None
            mid_price = None
            max_price = None
            with lock:
                min_price = trader.min_price
                mid_price = trader.mid_price
                max_price = trader.max_price
                daily_profit_dico = trader.compute_daily_profits()
                x_list = list(daily_profit_dico.keys())
                y_list = list(daily_profit_dico.values())
                fig_daily_profit.add_trace(go.Scatter(
                    x=x_list,
                    y=y_list,
                    mode='lines',
                    name=f'Daily profit',
                    line=dict(color='blue')
                ))
                buy_orders_data = []
                free_slots = 0
                if isinstance(trader, AbstractMultiTradeTrader):
                    free_slots = trader.free_slots
                    for order in trader.current_orders:
                        buy_fee = order.get('buy_fee')
                        buy_fee_formatted = f"{buy_fee:.2f}" if buy_fee is not None else None
                        if order['status'] != 'buy_in_progress':
                            profit = trader.compute_potential_profit_loss(order)
                        else:
                            profit = None
                        buy_orders_data.append({
                            'id': order['id'],
                            'opened_at': order['opened_at'],
                            'support': order['support'],
                            'status': order['status'],
                            'support_volume': order['support_volume'],
                            'buy_commission': order['buy_commission'] if order.get('buy_commission') else 'N/A',
                            'support_index': order['support_index'],
                            'cost': f"{order.get('cost', -1):.2f}" if order['status'] != 'buy_in_progress' else None,
                            'buy_price': f"{order.get('buy_price', -1):.2f}" if order['status'] != 'buy_in_progress' else None,
                            'quantity': f"{order.get('quantity', -1)}" if order['status'] != 'buy_in_progress' else None,
                            'buy_fee': buy_fee_formatted,
                            'stop_loss': f"{order.get('stop_loss_price', 0):.2f}" if order['status'] != 'buy_in_progress' else None,
                            'secured': order['secured'] if order.get('secured') else 'N/A' ,
                            'potential_profit_loss': f"{profit:.8f}" if profit is not None else None
                        })


                trade_history_data = []
                total_profit_loss = Decimal('0')
                for trade in trader.trade_history:
                    buy_fee = trade.get('buy_fee')
                    buy_fee_formatted = f"{buy_fee:.2f}" if buy_fee is not None else None
                    trade_history_data.append(
                        {
                            'id': trade['id'],
                            'opened_at': trade['opened_at'],
                            'support': trade['support'],
                            'support_volume': trade['support_volume'],
                            'support_index': trade['support_index'],
                            'cost': f"{trade.get('cost', -1):.2f}",
                            'buy_price': f"{trade['buy_price']:.2f}",
                            'quantity': f"{trade['quantity']}",
                            'buy_fee': buy_fee_formatted,
                            'stop_loss': f"{trade.get('stop_loss_price', 0):.2f}",
                            'secured': trade['secured'] if trade.get('secured') else 'N/A',
                            'closed_at': trade['closed_at'],
                            'sale_price': f"{trade['sale_price']:.8f}",
                            'sale_fee': f"{trade.get('sale_fee', 0):.8f}",
                            'profit': f"{trade['profit']:.8f}",
                            'sailed_quantity': trade['sailed_quantity'],
                            'duration': trade['duration']
                        })
                    total_profit_loss += trade['profit']
                creation_date = datetime.strptime(trader.creation_date, "%d/%m/%YT%H:%M")
                script_run_time = compute_duration_until_now(creation_date)

                # Formater les valeurs de support, prix actuel et résistance
                support = f"{trader.support['value']:.2f}" if trader.support['value'] else "Loading..."
                current_price = f"{trader.current_price:.2f}" if trader.current_price else "Loading..."
                resistance = f"{trader.resistance:.2f}" if trader.resistance else "Loading..."

                # Capital restant
                capital = f"{trader.capital:.2f} USDT"
                total_potential_profit_loss = f"{trader.compute_potential_total_profit_loss():.8f} USDT"
                total_profit_loss_value = f"{total_profit_loss:.8f} USDT"
                fig_daily_profit.update_layout(
                    title="Daily Profit",
                    yaxis_title='Profit/Loss (USDT)',
                    xaxis_title='Date',
                    xaxis_rangeslider_visible=False,
                    height=400
                )

            return (
                support,
                current_price,
                resistance,
                fig_daily_profit,
                buy_orders_data,
                trade_history_data,
                total_potential_profit_loss,
                script_run_time,
                capital,
                free_slots,
                total_profit_loss_value,
                min_price,
                mid_price,
                max_price
            )
        except Exception as e:
            logging.error(f"Error in update_layout: {e}", exc_info=True)
            return (
                "Erreur",
                "Erreur",
                "Erreur",
                [],
                [],
                "Erreur",
                "",
                "Erreur",
            )