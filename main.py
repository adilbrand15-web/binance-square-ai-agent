import json
import os
import subprocess
from urllib.request import urlopen, Request
from urllib.parse import urlencode

from database import initialize_database
from database import save_signal
from database import mark_signal_selected
from database import mark_signal_published
from database import mark_chart_saved
from database import get_signal
from database import get_all_signals

from chart_generator import generate_chart
from ai_writer import generate_ai_post


BASE_URL = "https://data-api.binance.vision/api/v3"

MIN_VOLUME = 5_000_000

CANDLE_LIMIT = 100

SIGNAL_THRESHOLD = 85


# =========================================================
# BINANCE PUBLIC API
# =========================================================

def api_request(endpoint, params=None):

    url = f"{BASE_URL}/{endpoint}"

    if params:
        url += "?" + urlencode(params)

    request = Request(
        url,
        headers={
            "User-Agent": "Binance-Square-AI-Agent/1.0"
        }
    )

    with urlopen(request, timeout=20) as response:
        return json.loads(
            response.read().decode()
        )


# =========================================================
# MARKET DATA
# =========================================================

def get_market_data():

    return api_request("ticker/24hr")


def get_klines(symbol, interval):

    return api_request(
        "klines",
        {
            "symbol": symbol,
            "interval": interval,
            "limit": CANDLE_LIMIT
        }
    )


# =========================================================
# INDICATORS
# =========================================================

def calculate_ema(values, period):

    if len(values) < period:
        return None

    ema = sum(values[:period]) / period

    multiplier = 2 / (period + 1)

    for price in values[period:]:

        ema = (
            (price - ema) * multiplier
        ) + ema

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

    avg_gain = sum(
        gains[:period]
    ) / period

    avg_loss = sum(
        losses[:period]
    ) / period

    for i in range(
        period,
        len(gains)
    ):

        avg_gain = (
            (
                avg_gain * (period - 1)
            )
            + gains[i]
        ) / period

        avg_loss = (
            (
                avg_loss * (period - 1)
            )
            + losses[i]
        ) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (
        100 / (1 + rs)
    )


def calculate_macd(values):

    ema12 = calculate_ema(
        values,
        12
    )

    ema26 = calculate_ema(
        values,
        26
    )

    if ema12 is None or ema26 is None:
        return None

    return ema12 - ema26


def calculate_atr(candles, period=14):

    if len(candles) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(candles)):

        high = float(
            candles[i][2]
        )

        low = float(
            candles[i][3]
        )

        previous_close = float(
            candles[i - 1][4]
        )

        true_range = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        true_ranges.append(
            true_range
        )

    return sum(
        true_ranges[-period:]
    ) / period


# =========================================================
# TIMEFRAME ANALYSIS
# =========================================================

def analyze_timeframe(symbol, interval):

    candles = get_klines(
        symbol,
        interval
    )

    if len(candles) < 50:
        return None

    closes = [
        float(candle[4])
        for candle in candles
    ]

    volumes = [
        float(candle[5])
        for candle in candles
    ]

    current_price = closes[-1]

    ema20 = calculate_ema(
        closes,
        20
    )

    ema50 = calculate_ema(
        closes,
        50
    )

    rsi = calculate_rsi(
        closes,
        14
    )

    macd = calculate_macd(
        closes
    )

    atr = calculate_atr(
        candles,
        14
    )

    average_volume = (
        sum(volumes[-20:]) / 20
    )

    current_volume = volumes[-1]

    if average_volume > 0:

        volume_ratio = (
            current_volume /
            average_volume
        )

    else:

        volume_ratio = 0

    recent = candles[-20:]

    highs = [
        float(candle[2])
        for candle in recent
    ]

    lows = [
        float(candle[3])
        for candle in recent
    ]

    support = min(lows)

    resistance = max(highs)

    return {
        "interval": interval,
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


# =========================================================
# TIMEFRAME DIRECTION
# =========================================================

def get_direction(data):

    if data is None:
        return "NEUTRAL"

    price = data["price"]

    ema20 = data["ema20"]

    ema50 = data["ema50"]

    rsi = data["rsi"]

    macd = data["macd"]

    bullish_points = 0

    bearish_points = 0

    if price > ema20:
        bullish_points += 1

    if price > ema50:
        bullish_points += 1

    if ema20 > ema50:
        bullish_points += 1

    if price < ema20:
        bearish_points += 1

    if price < ema50:
        bearish_points += 1

    if ema20 < ema50:
        bearish_points += 1

    if rsi >= 50:
        bullish_points += 1

    if rsi <= 50:
        bearish_points += 1

    if macd > 0:
        bullish_points += 1

    if macd < 0:
        bearish_points += 1

    if bullish_points >= 4:
        return "BULLISH"

    if bearish_points >= 4:
        return "BEARISH"

    return "NEUTRAL"


# =========================================================
# ENTRY CONFIRMATION
# =========================================================

def get_entry_confirmation(data, direction):

    if data is None:
        return False

    price = data["price"]

    ema20 = data["ema20"]

    ema50 = data["ema50"]

    rsi = data["rsi"]

    macd = data["macd"]

    volume_ratio = data["volume_ratio"]

    if direction == "LONG":

        confirmations = 0

        if price > ema20:
            confirmations += 1

        if ema20 > ema50:
            confirmations += 1

        if 45 <= rsi <= 70:
            confirmations += 1

        if macd > 0:
            confirmations += 1

        if volume_ratio >= 1.2:
            confirmations += 1

        return confirmations >= 4

    if direction == "SHORT":

        confirmations = 0

        if price < ema20:
            confirmations += 1

        if ema20 < ema50:
            confirmations += 1

        if 30 <= rsi <= 55:
            confirmations += 1

        if macd < 0:
            confirmations += 1

        if volume_ratio >= 1.2:
            confirmations += 1

        return confirmations >= 4

    return False


# =========================================================
# SIGNAL QUALITY FILTER
# =========================================================

def check_entry_quality(
    entry,
    stop_loss,
    direction,
    tf15m
):

    if tf15m is None:
        return False, "15M data unavailable"

    support = tf15m["support"]

    resistance = tf15m["resistance"]

    if direction == "LONG":

        if resistance <= entry:
            return False, "Entry already above resistance"

        distance_to_resistance = (
            resistance - entry
        )

        risk = abs(
            entry - stop_loss
        )

        if risk <= 0:
            return False, "Invalid risk"

        if distance_to_resistance < risk:
            return (
                False,
                "Resistance too close to entry"
            )

    elif direction == "SHORT":

        if support >= entry:
            return False, "Entry already below support"

        distance_to_support = (
            entry - support
        )

        risk = abs(
            stop_loss - entry
        )

        if risk <= 0:
            return False, "Invalid risk"

        if distance_to_support < risk:
            return (
                False,
                "Support too close to entry"
            )

    else:

        return False, "Invalid direction"

    return True, "Entry quality passed"


# =========================================================
# OVEREXTENSION & VOLATILITY FILTER
# =========================================================

def check_overextension(
    entry,
    direction,
    tf15m
):

    if tf15m is None:
        return False, "15M data unavailable"

    ema20 = tf15m["ema20"]

    atr = tf15m["atr"]

    rsi = tf15m["rsi"]

    volume_ratio = tf15m["volume_ratio"]

    if ema20 is None or atr is None or atr <= 0:
        return False, "Indicator data unavailable"

    atr_percent = (
        atr / entry
    ) * 100

    if atr_percent > 4:
        return (
            False,
            "Extreme 15M volatility"
        )

    if direction == "LONG":

        extension = (
            entry - ema20
        )

        if extension > (atr * 1.5):

            return (
                False,
                "LONG entry overextended"
            )

        if rsi >= 75:

            return (
                False,
                "LONG RSI too high"
            )

        if (
            volume_ratio >= 5
            and rsi >= 70
        ):

            return (
                False,
                "Possible LONG pump/exhaustion"
            )

    if direction == "SHORT":

        extension = (
            ema20 - entry
        )

        if extension > (atr * 1.5):

            return (
                False,
                "SHORT entry overextended"
            )

        if rsi <= 25:

            return (
                False,
                "SHORT RSI too low"
            )

        if (
            volume_ratio >= 5
            and rsi <= 30
        ):

            return (
                False,
                "Possible SHORT dump/exhaustion"
            )

    return True, "Overextension filter passed"


# =========================================================
# BTC MARKET CONTEXT FILTER
# =========================================================

def check_btc_context(
    symbol,
    direction,
    btc_4h_direction,
    btc_1h_direction
):

    if symbol in ["BTCUSDT", "ETHUSDT"]:

        return True, "BTC context filter skipped"

    if direction == "LONG":

        if (
            btc_4h_direction == "BEARISH"
            and btc_1h_direction == "BEARISH"
        ):

            return (
                False,
                "BTC market context strongly bearish"
            )

    if direction == "SHORT":

        if (
            btc_4h_direction == "BULLISH"
            and btc_1h_direction == "BULLISH"
        ):

            return (
                False,
                "BTC market context strongly bullish"
            )

    return True, "BTC market context passed"


# =========================================================
# MULTI-TIMEFRAME SIGNAL
# =========================================================

def generate_signal(
    symbol,
    btc_4h_direction=None,
    btc_1h_direction=None
):

    print(
        f"\nAnalyzing {symbol}"
    )

    tf4h = analyze_timeframe(
        symbol,
        "4h"
    )

    tf1h = analyze_timeframe(
        symbol,
        "1h"
    )

    tf15m = analyze_timeframe(
        symbol,
        "15m"
    )

    tf1m = analyze_timeframe(
        symbol,
        "1m"
    )

    if not all([
        tf4h,
        tf1h,
        tf15m,
        tf1m
    ]):

        print(
            f"{symbol}: "
            "Incomplete timeframe data"
        )

        return None

    direction4h = get_direction(
        tf4h
    )

    direction1h = get_direction(
        tf1h
    )

    direction15m = get_direction(
        tf15m
    )

    direction1m = get_direction(
        tf1m
    )

    print(
        f"4H  : {direction4h}"
    )

    print(
        f"1H  : {direction1h}"
    )

    print(
        f"15M : {direction15m}"
    )

    print(
        f"1M  : {direction1m}"
    )

    long_score = 0

    if direction4h == "BULLISH":
        long_score += 30

    if direction1h == "BULLISH":
        long_score += 25

    if direction15m == "BULLISH":
        long_score += 20

    if direction1m == "BULLISH":
        long_score += 10

    if get_entry_confirmation(
        tf15m,
        "LONG"
    ):

        long_score += 10

    if get_entry_confirmation(
        tf1m,
        "LONG"
    ):

        long_score += 5

    short_score = 0

    if direction4h == "BEARISH":
        short_score += 30

    if direction1h == "BEARISH":
        short_score += 25

    if direction15m == "BEARISH":
        short_score += 20

    if direction1m == "BEARISH":
        short_score += 10

    if get_entry_confirmation(
        tf15m,
        "SHORT"
    ):

        short_score += 10

    if get_entry_confirmation(
        tf1m,
        "SHORT"
    ):

        short_score += 5

    direction = None

    score = 0

    if (
        long_score >= SIGNAL_THRESHOLD
        and long_score > short_score
    ):

        direction = "LONG"

        score = long_score

    elif (
        short_score >= SIGNAL_THRESHOLD
        and short_score > long_score
    ):

        direction = "SHORT"

        score = short_score

    else:

        print(
            f"{symbol}: "
            "NO MULTI-TIMEFRAME SIGNAL"
        )

        return None

    entry = tf1m["price"]

    atr = tf15m["atr"]

    if atr is None or atr <= 0:

        print(
            f"{symbol}: "
            "ATR unavailable"
        )

        return None

    if direction == "LONG":

        stop_loss = (
            entry -
            (atr * 1.5)
        )

        risk = (
            entry -
            stop_loss
        )

        tp1 = entry + risk

        tp2 = entry + (risk * 2)

        tp3 = entry + (risk * 3)

    else:

        stop_loss = (
            entry +
            (atr * 1.5)
        )

        risk = (
            stop_loss -
            entry
        )

        tp1 = entry - risk

        tp2 = entry - (risk * 2)

        tp3 = entry - (risk * 3)

    quality_passed, quality_reason = check_entry_quality(
        entry,
        stop_loss,
        direction,
        tf15m
    )

    if not quality_passed:

        print(
            f"{symbol}: "
            f"REJECTED - {quality_reason}"
        )

        return None

    extension_passed, extension_reason = check_overextension(
        entry,
        direction,
        tf15m
    )

    if not extension_passed:

        print(
            f"{symbol}: "
            f"REJECTED - {extension_reason}"
        )

        return None

    btc_context_passed, btc_context_reason = check_btc_context(
        symbol,
        direction,
        btc_4h_direction,
        btc_1h_direction
    )

    if not btc_context_passed:

        print(
            f"{symbol}: "
            f"REJECTED - {btc_context_reason}"
        )

        return None

    # =====================================================
    # RSI
    # Use 15M RSI as the main entry/confirmation RSI
    # =====================================================

    rsi = tf15m.get("rsi")

    return {
        "symbol": symbol,
        "direction": direction,
        "score": score,
        "entry": entry,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "risk_reward": "1:3",
        "4h": direction4h,
        "1h": direction1h,
        "15m": direction15m,
        "1m": direction1m,
        "rsi": rsi
    }

# =========================================================
# DYNAMIC TOP 10
# =========================================================

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

        if symbol in [
            "BTCUSDT",
            "ETHUSDT"
        ]:
            continue

        if any(
            word in symbol
            for word in excluded_words
        ):
            continue

        try:

            price_change = float(
                coin["priceChangePercent"]
            )

            volume = float(
                coin["quoteVolume"]
            )

        except (
            ValueError,
            KeyError
        ):

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


# =========================================================
# PRICE FORMAT
# =========================================================

def format_price(price):

    if price >= 1000:
        return f"{price:,.2f}"

    if price >= 1:
        return f"{price:,.4f}"

    if price >= 0.01:
        return f"{price:,.6f}"

    return f"{price:,.8f}"


# =========================================================
# BINANCE SQUARE PUBLISHER
# =========================================================

def publish_to_square(
    ai_post,
    chart_path
):

    print(
        "\n" + "=" * 70
    )

    print(
        "BINANCE SQUARE PUBLISHER"
    )

    print(
        "=" * 70
    )

    if not ai_post:

        print(
            "PUBLISH FAILED: AI post is empty"
        )

        return None

    if not chart_path:

        print(
            "PUBLISH FAILED: Chart path is empty"
        )

        return None

    if not os.path.isfile(chart_path):

        print(
            f"PUBLISH FAILED: Chart not found: {chart_path}"
        )

        return None

    api_key = os.environ.get(
        "BINANCE_SQUARE_OPENAPI_KEY"
    )

    if not api_key:

        print(
            "PUBLISH FAILED: "
            "BINANCE_SQUARE_OPENAPI_KEY not set"
        )

        return None

    skill_dir = os.path.join(
        "binance-skills-hub",
        "skills",
        "binance",
        "square-post"
    )

    publisher = os.path.join(
        skill_dir,
        "scripts",
        "post-image.mjs"
    )

    if not os.path.isfile(publisher):

        print(
            f"PUBLISH FAILED: "
            f"Publisher not found: {publisher}"
        )

        return None

    absolute_publisher = os.path.abspath(
        publisher
    )

    print(
        "Publisher:"
    )

    print(
        absolute_publisher
    )

    print(
        "Chart:"
    )

    print(
        chart_path
    )

    print(
        "Sending selected signal to Binance Square..."
    )

    environment = os.environ.copy()

    environment[
        "BINANCE_SQUARE_OPENAPI_KEY"
    ] = api_key

    try:

        result = subprocess.run(
            [
                "node",
                absolute_publisher,
                "--text",
                ai_post,
                "--images",
                os.path.abspath(chart_path)
            ],
            cwd=skill_dir,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120
        )

    except subprocess.TimeoutExpired:

        print(
            "PUBLISH FAILED: "
            "Publisher timed out after 120 seconds"
        )

        return None

    except Exception as error:

        print(
            "PUBLISH FAILED:"
        )

        print(
            str(error)
        )

        return None

    output = (
        result.stdout
        + "\n"
        + result.stderr
    ).strip()

    print(
        "\nPUBLISHER OUTPUT:"
    )

    print(
        output
    )

    if result.returncode != 0:

        print(
            "\nBINANCE SQUARE PUBLISH: FAILED"
        )

        return None

    post_id = None

    post_link = None

    for line in output.splitlines():

        clean_line = line.strip()

        if clean_line.startswith("ID:"):

            post_id = clean_line.split(
                "ID:",
                1
            )[1].strip()

        if clean_line.startswith("Link:"):

            post_link = clean_line.split(
                "Link:",
                1
            )[1].strip()

    print(
        "\nBINANCE SQUARE PUBLISH: SUCCESS"
    )

    if post_id:

        print(
            f"POST ID: {post_id}"
        )

    if post_link:

        print(
            f"POST LINK: {post_link}"
        )

    return {
        "id": post_id,
        "link": post_link,
        "output": output
    }

# =========================================================
# MAIN
# =========================================================

def main():

    initialize_database()

    print("=" * 70)

    print(
        "BINANCE SQUARE AI AGENT"
    )

    print(
        "MULTI-TIMEFRAME SIGNAL ENGINE"
    )

    print("=" * 70)

    print(
        "\nTIMEFRAMES:"
    )

    print(
        "4H  = Higher-Timeframe Trend"
    )

    print(
        "1H  = Main Market Setup"
    )

    print(
        "15M = Entry Confirmation"
    )

    print(
        "1M  = Precise Entry Trigger"
    )

    top_coins = get_top_coins()

    symbols = [
        "BTCUSDT",
        "ETHUSDT"
    ]

    btc_4h_data = analyze_timeframe(
        "BTCUSDT",
        "4h"
    )

    btc_1h_data = analyze_timeframe(
        "BTCUSDT",
        "1h"
    )

    btc_4h_direction = get_direction(
        btc_4h_data
    )

    btc_1h_direction = get_direction(
        btc_1h_data
    )

    print(
        "\nBTC MARKET CONTEXT:"
    )

    print(
        f"BTC 4H: {btc_4h_direction}"
    )

    print(
        f"BTC 1H: {btc_1h_direction}"
    )

    for coin in top_coins:

        symbols.append(
            coin["symbol"]
        )

    print(
        "\nCOINS SELECTED:"
    )

    print("-" * 70)

    for symbol in symbols:

        print(symbol)

    print(
        "\nMULTI-TIMEFRAME ANALYSIS"
    )

    print("-" * 70)

    analyzed = 0

    signals_found = 0

    valid_signals = []

    for symbol in symbols:

        try:

            signal = generate_signal(
                symbol,
                btc_4h_direction,
                btc_1h_direction
            )

            analyzed += 1

            if signal:

                signals_found += 1

                valid_signals.append(signal)

                signal_id = save_signal(signal)

                signal["database_id"] = signal_id

                print(
                    f"Signal saved to database: ID {signal_id}"
                )

                print(
                    "\n" + "🚨" * 10
                )

                print(
                    f"SIGNAL FOUND: "
                    f"{signal['symbol']}"
                )

                print(
                    "🚨" * 10
                )

                print(
                    f"Direction: "
                    f"{signal['direction']}"
                )

                print(
                    f"Final Score: "
                    f"{signal['score']}/100"
                )

                print(
                    f"4H: "
                    f"{signal['4h']}"
                )

                print(
                    f"1H: "
                    f"{signal['1h']}"
                )

                print(
                    f"15M: "
                    f"{signal['15m']}"
                )

                print(
                    f"1M: "
                    f"{signal['1m']}"
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
                    "NO VALID MULTI-TIMEFRAME SIGNAL"
                )

        except Exception as error:

            print(
                f"{symbol}: "
                f"Analysis failed - {error}"
            )

    # =====================================================
    # SELECT BEST SIGNAL
    # =====================================================

    if valid_signals:

        selected_signal = max(
            valid_signals,
            key=lambda x: x["score"]
        )

        mark_signal_selected(
            selected_signal["database_id"]
        )

        print(
            "\n" + "=" * 70
        )

        print(
            "GENERATING SELECTED SIGNAL CHART"
        )

        print(
            "=" * 70
        )

        chart_path = generate_chart(
            selected_signal
        )
        if chart_path:
            mark_chart_saved(
                selected_signal["database_id"]
            )
        if chart_path:

            print(
                f"CHART GENERATED: "
                f"{chart_path}"
            )

        else:

            print(
                "CHART GENERATION FAILED"
            )

        print(
            "=" * 70
        )

        print(
            "SELECTED SIGNAL"
        )

        print(
            "=" * 70
        )

        print(
            f"Selected Coin: "
            f"{selected_signal['symbol']}"
        )

        print(
            f"Direction: "
            f"{selected_signal['direction']}"
        )

        print(
            f"Score: "
            f"{selected_signal['score']}/100"
        )

        print(
            "Selection Status: SELECTED"
        )

        print(
            "=" * 70
        )

        # =================================================
        # AI POST
        # =================================================

        print(
            "\n" + "=" * 70
        )

        print(
            "GENERATING AI SIGNAL POST"
        )

        print(
            "=" * 70
        )

        ai_post = generate_ai_post(
            selected_signal
        )

        if ai_post:

            print(
                "AI POST GENERATED"
            )

            print(
                "-" * 70
            )

            print(
                ai_post
            )

            print(
                "-" * 70
            )

            selected_signal[
                "ai_post"
            ] = ai_post

        else:

            print(
                "AI POST GENERATION FAILED"
            )

        print(
            "=" * 70
        )

        # =================================================
        # BINANCE SQUARE PUBLISH
        # =================================================

        if ai_post and chart_path:

            publish_result = publish_to_square(
                ai_post,
                chart_path
            )

            if publish_result:

                # Save Square post information
                # to the selected signal in memory
                selected_signal[
                    "square_post_id"
                ] = publish_result.get("id")

                selected_signal[
                    "square_post_link"
                ] = publish_result.get("link")

                # Save publication status,
                # Post ID and Post Link permanently
                # into SQLite database
                mark_signal_published(
                    selected_signal["database_id"],
                    publish_result.get("id"),
                    publish_result.get("link")
                )

                # =================================================
                # DATABASE VERIFICATION
                # =================================================

                saved_signal = get_signal(
                    selected_signal["database_id"]
                )

                if saved_signal:

                    print(
                        "\nDATABASE VERIFICATION"
                    )

                    print(
                        f"Signal ID: {saved_signal['id']}"
                    )

                    print(
                        f"Selected: {saved_signal['selected']}"
                    )

                    print(
                        f"Chart Saved: {saved_signal['chart_saved']}"
                    )

                    print(
                        f"Published: {saved_signal['published']}"
                    )

                    print(
                        f"Post ID: {saved_signal['post_id']}"
                    )

                    print(
                        f"Post Link: {saved_signal['post_link']}"
                    )

                else:

                    print(
                        "\nDATABASE VERIFICATION FAILED"
                    )

                    print(
                        "Signal record could not be found."
                    )

                print(
                    "\nDATABASE: "
                    "SIGNAL MARKED AS PUBLISHED"
                )

                print(
                    f"POST ID: "
                    f"{publish_result.get('id')}"
                )

                print(
                    f"POST LINK: "
                    f"{publish_result.get('link')}"
                )

        else:

            print(
                "\nBINANCE SQUARE PUBLISH SKIPPED"
            )

            print(
                "Reason: AI post or chart unavailable"
            )

    print(
        "\n" + "=" * 70
    )

    print(
        f"Coins analyzed: "
        f"{analyzed}/{len(symbols)}"
    )

    print(
        f"Valid signals: "
        f"{signals_found}"
    )

# =================================================
# SIGNAL HISTORY
# =================================================

all_signals = get_all_signals()

print(
    "\n========================================"
)

print(
    "SIGNAL HISTORY"
)

print(
    "========================================"
)

if not all_signals:

    print(
        "No saved signals found."
    )

else:

    print(
        f"Total saved signals: {len(all_signals)}"
    )

    print(
        "----------------------------------------"
    )

    for signal in all_signals:

        print(
            f"ID: {signal[0]} | "
            f"{signal[1]} | "
            f"{signal[2]} | "
            f"Score: {signal[3]} | "
            f"Entry: {signal[8]} | "
            f"SL: {signal[9]} | "
            f"TP1: {signal[10]} | "
            f"TP2: {signal[11]} | "
            f"TP3: {signal[12]} | "
            f"Selected: {signal[16]} | "
            f"Published: {signal[15]}"
        )

print(
    "========================================"
)

if signals_found == 0:

    print(
        "STATUS: "
        "NO TRADE SETUP"
    )

    print(
        "No post should be created."
    )

else:

    print(
        "STATUS: "
        "MULTI-TIMEFRAME SIGNAL(S) FOUND"
    )

print(
    "MULTI-TIMEFRAME ENGINE: ONLINE"
)

print(
    "=" * 70
)


if __name__ == "__main__":
    main()