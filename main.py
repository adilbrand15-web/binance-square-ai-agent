import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode

BASE_URL = "https://data-api.binance.vision/api/v3"

MIN_VOLUME = 5_000_000
CANDLE_LIMIT = 100


def api_request(endpoint, params=None):
    url = f"{BASE_URL}/{endpoint}"

    if params:
        url += "?" + urlencode(params)

    request = Request(
        url,
        headers={"User-Agent": "Binance-Square-AI-Agent/1.0"}
    )

    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())


def get_market_data():
    return api_request("ticker/24hr")


def get_klines(symbol):
    return api_request(
        "klines",
        {
            "symbol": symbol,
            "interval": "1h",
            "limit": CANDLE_LIMIT
        }
    )


def calculate_ema(values, period):
    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)

    ema = sum(values[:period]) / period

    for price in values[period:]:
        ema = (price - ema) * multiplier + ema

    return ema


def calculate_rsi(values, period=14):
    if len(values) <= period:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def calculate_macd(values):
    ema12 = calculate_ema(values, 12)
    ema26 = calculate_ema(values, 26)

    if ema12 is None or ema26 is None:
        return None, None

    macd = ema12 - ema26

    # For this first version we calculate the current MACD
    # and use it as the main momentum measurement.
    return macd, None


def analyze_coin(symbol):
    candles = get_klines(symbol)

    closes = [float(candle[4]) for candle in candles]
    volumes = [float(candle[5]) for candle in candles]

    if len(closes) < 50:
        return None

    current_price = closes[-1]

    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    rsi = calculate_rsi(closes, 14)
    macd, macd_signal = calculate_macd(closes)

    average_volume = sum(volumes[-20:]) / 20
    current_volume = volumes[-1]

    if average_volume > 0:
        volume_ratio = current_volume / average_volume
    else:
        volume_ratio = 0

    return {
        "symbol": symbol,
        "price": current_price,
        "ema20": ema20,
        "ema50": ema50,
        "rsi": rsi,
        "macd": macd,
        "volume_ratio": volume_ratio
    }


def get_top_coins():
    data = get_market_data()

    filtered = []

    excluded_words = [
        "UPUSDT",
        "DOWNUSDT",
        "BULLUSDT",
        "BEARUSDT"
    ]

    for coin in data:
        symbol = coin["symbol"]

        if not symbol.endswith("USDT"):
            continue

        if symbol in ["BTCUSDT", "ETHUSDT"]:
            continue

        if any(word in symbol for word in excluded_words):
            continue

        try:
            price_change = float(coin["priceChangePercent"])
            volume = float(coin["quoteVolume"])
        except (ValueError, KeyError):
            continue

        if volume < MIN_VOLUME:
            continue

        filtered.append({
            "symbol": symbol,
            "change": price_change,
            "volume": volume
        })

    filtered.sort(
        key=lambda x: x["change"],
        reverse=True
    )

    return filtered[:10]


def main():

    print("=" * 60)
    print("BINANCE SQUARE AI AGENT")
    print("TECHNICAL ANALYSIS ENGINE")
    print("=" * 60)

    top_coins = get_top_coins()

    symbols = ["BTCUSDT", "ETHUSDT"]

    for coin in top_coins:
        symbols.append(coin["symbol"])

    print("\nCOINS SELECTED FOR ANALYSIS:")
    print("-" * 60)

    for symbol in symbols:
        print(symbol)

    print("\n1H TECHNICAL ANALYSIS")
    print("-" * 60)

    successful = 0

    for symbol in symbols:

        try:
            result = analyze_coin(symbol)

            if result is None:
                print(f"{symbol}: Not enough candle data")
                continue

            successful += 1

            print(f"\n{symbol}")
            print(f"Price: ${result['price']:,.6f}")
            print(f"EMA 20: ${result['ema20']:,.6f}")
            print(f"EMA 50: ${result['ema50']:,.6f}")
            print(f"RSI 14: {result['rsi']:.2f}")
            print(f"MACD: {result['macd']:.6f}")
            print(f"Volume Ratio: {result['volume_ratio']:.2f}x")

        except Exception as error:
            print(f"{symbol}: Analysis failed - {error}")

    print("\n" + "=" * 60)
    print(f"Technical analysis completed: {successful}/{len(symbols)}")
    print("TECHNICAL ENGINE: ONLINE")
    print("=" * 60)


if __name__ == "__main__":
    main()