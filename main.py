import json
from urllib.request import urlopen, Request

BINANCE_API = "https://api.binance.com/api/v3/ticker/price"


def get_price(symbol):
    url = f"{BINANCE_API}?symbol={symbol}"

    request = Request(
        url,
        headers={"User-Agent": "Binance-Square-AI-Agent/1.0"}
    )

    with urlopen(request, timeout=10) as response:
        data = json.loads(response.read().decode())

    return float(data["price"])


def main():
    print("=" * 45)
    print("BINANCE SQUARE AI AGENT")
    print("MARKET SCANNER")
    print("=" * 45)

    btc = get_price("BTCUSDT")
    eth = get_price("ETHUSDT")

    print(f"BTC/USDT: ${btc:,.2f}")
    print(f"ETH/USDT: ${eth:,.2f}")

    print("=" * 45)
    print("Market data connection: ONLINE")
    print("=" * 45)


if __name__ == "__main__":
    main()