import json
from urllib.request import urlopen, Request

BINANCE_API = "https://data-api.binance.vision/api/v3/ticker/24hr"


def get_market_data():
    request = Request(
        BINANCE_API,
        headers={"User-Agent": "Binance-Square-AI-Agent/1.0"}
    )

    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())


def main():
    print("=" * 55)
    print("BINANCE SQUARE AI AGENT")
    print("DYNAMIC TOP GAINERS SCANNER")
    print("=" * 55)

    data = get_market_data()

    # Only USDT trading pairs
    usdt_pairs = [
        coin for coin in data
        if coin["symbol"].endswith("USDT")
    ]

    # Coins/pairs we don't want in the altcoin scanner
    excluded_words = [
        "UPUSDT",
        "DOWNUSDT",
        "BULLUSDT",
        "BEARUSDT"
    ]

    filtered = []

    for coin in usdt_pairs:
        symbol = coin["symbol"]

        if symbol in ["BTCUSDT", "ETHUSDT"]:
            continue

        if any(word in symbol for word in excluded_words):
            continue

        try:
            price_change = float(coin["priceChangePercent"])
            volume = float(coin["quoteVolume"])
        except (ValueError, KeyError):
            continue

        # Minimum 24h volume: $5 million
        if volume < 5_000_000:
            continue

        filtered.append({
            "symbol": symbol,
            "change": price_change,
            "volume": volume,
            "price": float(coin["lastPrice"])
        })

    # Sort by 24h percentage gain
    filtered.sort(
        key=lambda x: x["change"],
        reverse=True
    )

    top_10 = filtered[:10]

    print("\nTOP 10 DYNAMIC GAINERS")
    print("-" * 55)

    for index, coin in enumerate(top_10, start=1):
        print(
            f"{index}. {coin['symbol']}"
            f" | +{coin['change']:.2f}%"
            f" | Volume: ${coin['volume']:,.0f}"
            f" | Price: ${coin['price']}"
        )

    print("-" * 55)
    print(f"Coins scanned: {len(filtered)}")
    print("Scanner status: ONLINE")
    print("=" * 55)


if __name__ == "__main__":
    main()