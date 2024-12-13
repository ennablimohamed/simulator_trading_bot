import dash
import dash_bootstrap_components as dbc
from dash import dcc, html, dash_table


def create_app(title):
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
    app.title = title
    return app

def create_div(id):
    return html.Div(id=id),


def create_card(id, header, color):
    dbc.Card([
        dbc.CardHeader(header),
        dbc.CardBody([
            html.H4(
                id={'type': id},
                className='card-title',
                children="Loading..."
            ),
        ])
    ], color=color, inverse=True)
