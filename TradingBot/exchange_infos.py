import requests


def get_symbol_info(symbol):
    """
    Récupère les informations de trading pour une paire spécifique.
    """
    url = "https://api.binance.com/api/v3/exchangeInfo"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        for s in data['symbols']:
            if s['symbol'] == symbol:
                return s
    else:
        print(f"Erreur: Impossible de récupérer les informations ({response.status_code})")
        return None


def extract_minimums_and_steps(symbol_info):
    """
    Extrait les quantités minimales, les tailles de pas (step size) et la valeur minimale en USDT.
    """
    min_qty = None
    step_size = None
    min_notional = None

    for f in symbol_info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            min_qty = float(f['minQty'])  # Quantité minimale
            step_size = float(f['stepSize'])  # Taille de pas
        if f['filterType'] == 'NOTIONAL':
            min_notional = float(f['minNotional'])  # Valeur minimale d'une transaction

    return min_qty, step_size, min_notional


def main():
    # Paire cible
    symbol = "BTCUSDT"

    # Récupération des informations pour la paire
    symbol_info = get_symbol_info(symbol)
    if symbol_info:
        min_qty, step_size, min_notional = extract_minimums_and_steps(symbol_info)
        print(f"Pour la paire {symbol}:")
        print(f" - Quantité minimale à acheter ou vendre: {min_qty:.8f}")
        print(f" - Step size (taille de pas): {step_size:.8f}")
        print(f" - Valeur minimale d'une transaction (en USDT): {min_notional:.8f}")
    else:
        print(f"Impossible de récupérer les informations pour la paire {symbol}.")


if __name__ == "__main__":
    main()
