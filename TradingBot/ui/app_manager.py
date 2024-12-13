import logging
from datetime import datetime

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objs as go

from traders.FundingRateTrader import FundingRateTrader
from traders.abstract_support_trader import AbstractSupportTrader
from traders.bollinger_original_reverse_mean_trader import BollingerOriginalReverseMeanTrader
from traders.bollinger_reverse_mean_trader import BollingerReverseMeanTrader
from traders.min_max_secured_capital_trader import MinMaxSecuredCapitalTrader
from traders.min_max_trader import MinMaxTrader
from ui.traders.BollingerTraderTabManager import BollingerTraderTabManager
from ui.traders.FundingRateTabManager import FundingRateTabManager
from ui.traders.MinMaxSupportTraderTabManager import MinMaxSupportTraderTabManager
from ui.traders.MinMaxTraderManager import MinMaxTraderTabManager
from ui.traders.SupportTraderTabManager import SupportTraderTabManager

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])


class AppManager:
    def __init__(self, app_name, trading_bot_data):
        self.app_name = app_name
        self.app = None
        self.trading_bot_data = trading_bot_data
        self.colors = ['blue', 'red', 'green', 'yellow', 'purple', 'orange']
        self.tab_content_generator = {}
        self.supportTraderTabManager = SupportTraderTabManager(app=app, trading_bot_data=trading_bot_data)
        self.min_max_supportTraderTabManager = MinMaxSupportTraderTabManager(app=app, trading_bot_data=trading_bot_data)
        self.fundingRateTabManager = FundingRateTabManager(app=app, trading_bot_data=trading_bot_data)
        self.bollingerReverseMeanManager = BollingerTraderTabManager(app=app, trading_bot_data=trading_bot_data)
        self.min_max_trader_manager = MinMaxTraderTabManager(app=app, trading_bot_data=trading_bot_data)

        for trader_id, data in trading_bot_data.traders.items():
            if isinstance(data['instance'], MinMaxSecuredCapitalTrader):
                self.tab_content_generator[trader_id] = self.min_max_supportTraderTabManager
            elif isinstance(data['instance'], MinMaxTrader):
                self.tab_content_generator[trader_id] = self.min_max_trader_manager
            elif isinstance(data['instance'], AbstractSupportTrader):
                self.tab_content_generator[trader_id] = self.supportTraderTabManager
            elif isinstance(data['instance'], FundingRateTrader):
                self.tab_content_generator[trader_id] = self.fundingRateTabManager
            elif isinstance(data['instance'], BollingerReverseMeanTrader) or isinstance(data['instance'], BollingerOriginalReverseMeanTrader):
                self.tab_content_generator[trader_id] = self.bollingerReverseMeanManager

    def create_app(self):
        global app
        self.app = app
        app.title = 'TRADER BOT V2'
        self.init_layout()
        self.add_callbacks()
        return self.app

    def add_callbacks(self):

        self.app.callback(Output('tab-content', 'children'),
                          [Input('tabs', 'value')])(lambda tab: self.__handle_selected_tab(tab))

        self.app.callback([Output('potential-profit-loss-chart', 'figure'),
                           Output('total-profit-loss-chart', 'figure')],
                          [Input('analytics-interval', 'n_intervals')])(lambda n: self._update_analytics_content(n))
    def init_layout(self):
        tabs = [dcc.Tab(label="Analytics", value='analytics')]
        trader_names = self.trading_bot_data.traders.keys()
        for trader_name in trader_names:
            tabs.append(dcc.Tab(label=trader_name, value=trader_name))

        self.app.layout = html.Div([
            dcc.Tabs(
                id='tabs',
                value='analytics',
                children=tabs
            ),
            html.Div(id='tab-content')
        ])

    def __handle_selected_tab(self, tab):
        """
        Met à jour le contenu de l'onglet en fonction de l'onglet sélectionné.
        """
        if tab == 'analytics':
            return self.generate_analytics_layout()
        return self.generate_trader_tab_content(tab)

    def generate_analytics_layout(self):
        """
        Génère le layout pour l'onglet Analytics avec un composant Interval.
        """
        return html.Div([
            dcc.Interval(
                id='analytics-interval',
                interval=5000,  # 5 secondes en millisecondes
                n_intervals=0
            ),
            html.Div([
                dbc.Row([
                    dbc.Col([
                        dcc.Graph(id='potential-profit-loss-chart')
                    ], width=12)
                ]),
                dbc.Row([
                    dbc.Col([
                        dcc.Graph(id='total-profit-loss-chart')
                    ], width=12)
                ])
            ])
        ])

    def _update_analytics_content(self, n):

        try:
            # Graphiques pour les stratégies principales
            fig_potential_profit_loss = go.Figure()
            fig_total_profit_loss = go.Figure()

            color_index = 0
            timestamp = datetime.now()

            # Mettre à jour les graphiques pour les stratégies principales
            for trader_name, trader_data in self.trading_bot_data.traders.items():
                trader = trader_data['instance']
                lock = trader_data['lock']

                with lock:
                    analytics = trader.compute_analytics()
                    strategy_name = trader.trader_id

                potential_history = self.trading_bot_data.analytics_data[trader_name]['potential_profit_loss_history']
                potential_history.append(
                    {
                        'timestamp': timestamp,
                        'profit_loss': analytics['potential_profit_loss']
                    }
                )
                total_history = self.trading_bot_data.analytics_data[trader_name]['total_profit_loss_history']
                total_history.append(
                    {
                        'timestamp': timestamp,
                        'profit_loss': analytics['total_profit_loss']
                    }
                )

                y_list = [entry['profit_loss'] for entry in potential_history]
                x_list = [entry['timestamp'] for entry in potential_history]
                fig_potential_profit_loss.add_trace(go.Scatter(
                    x=x_list,
                    y=y_list,
                    mode='lines',
                    name=f'Potential profit loss {strategy_name}',
                    line=dict(color=self.colors[color_index])
                ))
                y_list = [entry['profit_loss'] for entry in total_history]
                x_list = [entry['timestamp'] for entry in total_history]
                fig_total_profit_loss.add_trace(go.Scatter(
                    x=x_list,
                    y=y_list,
                    mode='lines',
                    name=f'Total profit loss {strategy_name}',
                    line=dict(color=self.colors[color_index])
                ))
                color_index += 1

            fig_potential_profit_loss.update_layout(
                title="Potential Profit/Loss per Strategy",
                yaxis_title='Profit/Loss (USDT)',
                xaxis_title='Time',
                xaxis_rangeslider_visible=False,
                height=400
            )
            fig_total_profit_loss.update_layout(
                title="Total Profit/Loss per Strategy",
                yaxis_title='Profit/Loss (USDT)',
                xaxis_title='Time',
                xaxis_rangeslider_visible=False,
                height=400
            )

            return fig_potential_profit_loss, fig_total_profit_loss
        except Exception as e:
            logging.error(f"Error in update_analytics_content: {e}", exc_info=True)
            return [html.Div([html.P("An error occurred while generating analytics data.")])] * 5

    def generate_trader_tab_content(self, trader_name):

        trader = self.trading_bot_data.traders[trader_name]['instance']
        tab_content_generator = self.tab_content_generator[trader_name]
        return tab_content_generator.generate_trader_tab_content(trader_name, trader.symbol)


