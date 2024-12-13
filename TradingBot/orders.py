from binance.spot import Spot
import os
from datetime import datetime

# Vos clés API Binance (assurez-vous qu'elles sont sécurisées)
api_key = '07yFPJlYHoqXWlpvGcoTwOMLrrLUIyWKHyLz4C9pBJ348RVbQy5Xf0ZEhOXJDwIi'
api_secret = 'TZMK5IgyGlxliTsMnt1wds3eNBC8FtugGWfj6BylF1QAdVC9Ltz7I3pWMlTAO1AR'

# Vérifier que les clés API sont définies
if not api_key or not api_secret:
    print("Erreur : Les clés API ne sont pas définies. Veuillez définir les variables d'environnement BINANCE_API_KEY et BINANCE_API_SECRET.")
    exit(1)

# Créer un client Spot
client = Spot(api_key=api_key, api_secret=api_secret, base_url='https://testnet.binance.vision')

def main():
    # Vous pouvez spécifier le symbole si vous le souhaitez, par exemple 'BTCUSDT'
    symbol = 'BTCUSDT'  # Laisser vide pour tous les symboles

    try:
        # Récupérer tous les ordres
        if symbol:
            orders = client.get_orders(symbol=symbol)
        else:
            # Si aucun symbole n'est spécifié, récupérer les ordres pour tous les symboles
            exchange_info = client.exchange_info()
            symbols = [s['symbol'] for s in exchange_info['symbols']]
            orders = []
            for sym in symbols:
                sym_orders = client.get_orders(symbol=sym)
                orders.extend(sym_orders)
    except Exception as e:
        print(f"Une erreur est survenue lors de la récupération des ordres : {e}")
        return

    if not orders:
        print("Aucun ordre trouvé.")
        return

    for order in orders:
        side = order['side']  # 'BUY' ou 'SELL'
        print(f"Symbole : {order['symbol']}")
        print(f"ID de l'ordre : {order['orderId']}")
        print(f"Côté : {side}")
        print(f"Type d'ordre : {order['type']}")
        print(f"Prix : {order['price']}")
        print(f"Quantité : {order['origQty']}")
        print(f"Quantité exécutée : {order['executedQty']}")
        print(f"Statut : {order['status']}")
        # Convertir le timestamp en date lisible
        time_value = datetime.fromtimestamp(order['time'] / 1000)
        print(f"Temps : {time_value.strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 40)

if __name__ == "__main__":
    main()
