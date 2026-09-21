import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode

BASE_URL = "https://data-api.binance.vision/api/v3"

MIN_VOLUME = 5_000_000
CANDLE_LIMIT = 100
SIGNAL_THRESHOLD = 85


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

    ema = sum(values[:period]) / period
    multiplier = 2 / (period + 1)

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
        avg_gain = (
            (avg_gain * (period - 1)) + gains[i]
        ) / period

        avg_loss = (
            (avg_loss * (period - 1)) + losses[i]
        ) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def calculate_macd(values):
    ema12 = calculate_ema(values, 12)
    ema26 = calculate_ema(values, 26)

    if ema12 is None or ema26 is None:
        return None

    return ema12 - ema26


def calculate_atr(candles, period=14):
    if len(candles) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(candles)):
        high = float(candles[i][2])
        low = float(candles[i][3])
        previous_close = float(candles[i - 1][4])

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        true_ranges.append(tr)

    return sum(true_ranges[-period:]) / period


def get_market_structure(candles):
    recent = candles[-20:]

    highs = [float(candle[2]) for candle in recent]
    lows = [float(candle[3]) for candle in recent]

    resistance = max(highs)
    support = min(lows)

    return support, resistance


def analyze_coin(symbol):
    candles = get_klines(symbol)

    if len(candles) < 50:
        return None

    closes = [float(candle[4]) for candle in candles]
    volumes = [float(candle[5]) for candle in candles]

    current_price = closes[-1]

    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)

    rsi = calculate_rsi(closes, 14)

    macd = calculate_macd(closes)

    atr = calculate_atr(candles, 14)

    average_volume = sum(volumes[-20:]) / 20

    current_volume = volumes[-1]

    if average_volume > 0:
        volume_ratio = current_volume / average_volume
    else:
        volume_ratio = 0

    support, resistance = get_market_structure(candles)

    return {
        "symbol": symbol,
        "price": current_price,
        "ema20": ema20,
        "ema50": ema50,
        "rsi": rsi,
        "macd": macd,
        "atr": atr,
        "volume_ratio": volume_ratio,
        "support": support,
        "resistance": resistance
    }


def calculate_signal(result):

    price = result["price"]
    ema20 = result["ema20"]
    ema50 = result["ema50"]
    rsi = result["rsi"]
    macd = result["macd"]
    atr = result["atr"]
    volume_ratio = result["volume_ratio"]
    support = result["support"]
    resistance = result["resistance"]

    long_score = 0
    short_score = 0

    # -------------------------
    # TREND
    # -------------------------

    if price > ema20 > ema50:
        long_score += 25

    if price < ema20 < ema50:
        short_score += 25

    # -------------------------
    # RSI
    # -------------------------

    if 50 <= rsi <= 68:
        long_score += 15

    if 32 <= rsi <= 50:
        short_score += 15

    # Avoid extreme overbought/oversold entries
    if rsi > 75:
        long_score -= 10

    if rsi < 25:
        short_score -= 10

    # -------------------------
    # MACD
    # -------------------------

    if macd > 0:
        long_score += 15

    if macd < 0:
        short_score += 15

    # -------------------------
    # VOLUME
    # -------------------------

    if volume_ratio >= 1.5:
        long_score += 15
        short_score += 15

    elif volume_ratio >= 1.2:
        long_score += 10
        short_score += 10

    # -------------------------
    # MARKET STRUCTURE
    # -------------------------

    structure_range = resistance - support

    if structure_range > 0:

        position = (price - support) / structure_range

        # Price in lower/middle area
        if position < 0.60:
            long_score += 15

        # Price in upper/middle area
        if position > 0.40:
            short_score += 15

    # -------------------------
    # BREAKOUT / BREAKDOWN
    # -------------------------

    if price > resistance:
        long_score += 15

    if price < support:
        short_score += 15

    # Limit score
    long_score = max(0, min(100, long_score))
    short_score = max(0, min(100, short_score))

    # -------------------------
    # SELECT DIRECTION
    # -------------------------

    if long_score >= SIGNAL_THRESHOLD and long_score > short_score:

        entry = price

        stop_loss = entry - (atr * 1.5)

        risk = entry - stop_loss

        tp1 = entry + (risk * 1.0)
        tp2 = entry + (risk * 2.0)
        tp3 = entry + (risk * 3.0)

        return {
            "symbol": result["symbol"],
            "direction": "LONG",
            "score": long_score,
            "entry": entry,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "risk_reward": "1:3"
        }

    if short_score >= SIGNAL_THRESHOLD and short_score > long_score:

        entry = price

        stop_loss = entry + (atr * 1.5)

        risk = stop_loss - entry

        tp1 = entry - (risk * 1.0)
        tp2 = entry - (risk * 2.0)
        tp3 = entry - (risk * 3.0)

        return {
            "symbol": result["symbol"],
            "direction": "SHORT",
            "score": short_score,
            "entry": entry,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "risk_reward": "1:3"
        }

    return None


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
            price_change = float(
                coin["priceChangePercent"]
            )

            volume = float(
                coin["quoteVolume"]
            )

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


def format_price(price):

    if price >= 1000:
        return f"{price:,.2f}"

    if price >= 1:
        return f"{price:,.4f}"

    if price >= 0.01:
        return f"{price:,.6f}"

    return f"{price:,.8f}"


def main():

    print("=" * 65)
    print("BINANCE SQUARE AI AGENT")
    print("SIGNAL ENGINE")
    print("=" * 65)

    top_coins = get_top_coins()

    symbols = [
        "BTCUSDT",
        "ETHUSDT"
    ]

    for coin in top_coins:
        symbols.append(coin["symbol"])

    print("\nCOINS SELECTED:")
    print("-" * 65)

    for symbol in symbols:
        print(symbol)

    print("\nSIGNAL ANALYSIS")
    print("-" * 65)

    signals_found = 0
    analyzed = 0

    for symbol in symbols:

        try:

            result = analyze_coin(symbol)

            if result is None:
                print(f"{symbol}: Not enough data")
                continue

            analyzed += 1

            signal = calculate_signal(result)

            if signal:

                signals_found += 1

                print("\n" + "🚨" * 8)
                print(f"SIGNAL FOUND: {signal['symbol']}")
                print("🚨" * 8)

                print(
                    f"Direction: {signal['direction']}"
                )

                print(
                    f"Signal Score: "
                    f"{signal['score']}/100"
                )

                print(
                    f"Entry: "
                    f"${format_price(signal['entry'])}"
                )

                print(
                    f"Stop Loss: "
                    f"${format_price(signal['stop_loss'])}"
                )

                print(
                    f"TP1: "
                    f"${format_price(signal['tp1'])}"
                )

                print(
                    f"TP2: "
                    f"${format_price(signal['tp2'])}"
                )

                print(
                    f"TP3: "
                    f"${format_price(signal['tp3'])}"
                )

                print(
                    f"Risk/Reward: "
                    f"{signal['risk_reward']}"
                )

            else:

                print(
                    f"{symbol}: "
                    f"NO VALID SIGNAL"
                )

        except Exception as error:

            print(
                f"{symbol}: "
                f"Analysis failed - {error}"
            )

    print("\n" + "=" * 65)

    print(
        f"Coins analyzed: "
        f"{analyzed}/{len(symbols)}"
    )

    print(
        f"Valid signals: "
        f"{signals_found}"
    )

    if signals_found == 0:
        print("STATUS: NO TRADE SETUP")
        print("No post should be created.")

    else:
        print("STATUS: SIGNAL(S) FOUND")

    print("SIGNAL ENGINE: ONLINE")
    print("=" * 65)


if __name__ == "__main__":
    main()