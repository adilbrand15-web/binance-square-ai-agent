import json
import os
from datetime import datetime, timezone
from urllib.request import urlopen, Request

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


BINANCE_BASE_URL = "https://data-api.binance.vision/api/v3"


def get_json(url):
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def get_klines(symbol, interval="1h", limit=100):

    url = (
        f"{BINANCE_BASE_URL}/klines"
        f"?symbol={symbol}"
        f"&interval={interval}"
        f"&limit={limit}"
    )

    return get_json(url)


def get_24h_data(symbol):

    url = (
        f"{BINANCE_BASE_URL}/ticker/24hr"
        f"?symbol={symbol}"
    )

    return get_json(url)


def calculate_rsi(closes, period=14):

    if len(closes) <= period:
        return 50.0

    gains = []
    losses = []

    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]

        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        average_gain = (
            (average_gain * (period - 1)) + gains[i]
        ) / period

        average_loss = (
            (average_loss * (period - 1)) + losses[i]
        ) / period

    if average_loss == 0:
        return 100.0

    rs = average_gain / average_loss

    return 100 - (100 / (1 + rs))


def format_price(price):

    if price >= 100:
        return f"{price:.2f}"

    if price >= 1:
        return f"{price:.4f}"

    return f"{price:.6f}"


def generate_chart(signal):

    symbol = signal["symbol"]

    direction = signal["direction"]

    entry = float(signal["entry"])
    stop_loss = float(signal["stop_loss"])

    tp1 = float(signal["tp1"])
    tp2 = float(signal["tp2"])
    tp3 = float(signal["tp3"])

    score = signal["score"]

    print("=" * 70)
    print("CHART GENERATOR")
    print("=" * 70)

    print(f"Symbol: {symbol}")
    print(f"Direction: {direction}")
    print(f"Score: {score}/100")

    # ---------------------------------------------------------
    # MARKET DATA
    # ---------------------------------------------------------

    klines = get_klines(
        symbol,
        interval="1h",
        limit=100
    )

    market_24h = get_24h_data(symbol)

    closes = [
        float(kline[4])
        for kline in klines
    ]

    volumes = [
        float(kline[5])
        for kline in klines
    ]

    opens = [
        float(kline[1])
        for kline in klines
    ]

    highs = [
        float(kline[2])
        for kline in klines
    ]

    lows = [
        float(kline[3])
        for kline in klines
    ]

    rsi = calculate_rsi(closes)

    current_price = float(
        market_24h["lastPrice"]
    )

    change_24h = float(
        market_24h["priceChangePercent"]
    )

    # ---------------------------------------------------------
    # SUPPORT / RESISTANCE
    # ---------------------------------------------------------

    recent_highs = highs[-30:]
    recent_lows = lows[-30:]

    resistance = max(recent_highs)
    support = min(recent_lows)

    # ---------------------------------------------------------
    # OUTPUT DIRECTORY
    # ---------------------------------------------------------

    os.makedirs(
        "charts",
        exist_ok=True
    )

    clean_symbol = symbol.replace(
        "USDT",
        ""
    )

    filename = (
        f"charts/"
        f"{clean_symbol}_"
        f"{direction}_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        f".png"
    )

    # ---------------------------------------------------------
    # FIGURE
    # ---------------------------------------------------------

    fig = plt.figure(
        figsize=(16, 12),
        facecolor="#06101d"
    )

    grid = fig.add_gridspec(
        3,
        1,
        height_ratios=[1.1, 5, 1.4],
        hspace=0.08
    )

    # ---------------------------------------------------------
    # HEADER
    # ---------------------------------------------------------

    header = fig.add_subplot(grid[0])

    header.set_facecolor("#06101d")

    header.axis("off")

    header.text(
        0.02,
        0.72,
        f"{clean_symbol}/USDT",
        fontsize=30,
        fontweight="bold",
        color="white"
    )

    header.text(
        0.02,
        0.28,
        f"1H {direction} SETUP",
        fontsize=19,
        fontweight="bold",
        color="#28e878"
        if direction == "LONG"
        else "#ff4d67"
    )

    header.text(
        0.42,
        0.72,
        datetime.now().strftime("%d %B %Y"),
        fontsize=14,
        color="white"
    )

    header.text(
        0.42,
        0.30,
        f"Current Price: ${format_price(current_price)}",
        fontsize=14,
        color="#28e878"
    )

    change_color = (
        "#28e878"
        if change_24h >= 0
        else "#ff4d67"
    )

    header.text(
        0.70,
        0.72,
        f"24H Change: {change_24h:+.2f}%",
        fontsize=14,
        color=change_color
    )

    header.text(
        0.70,
        0.30,
        f"Signal Score: {score}/100",
        fontsize=14,
        color="white"
    )

    # ---------------------------------------------------------
    # PRICE CHART
    # ---------------------------------------------------------

    ax = fig.add_subplot(grid[1])

    ax.set_facecolor("#081522")

    for i in range(len(closes)):

        color = (
            "#22d69a"
            if closes[i] >= opens[i]
            else "#f05263"
        )

        ax.vlines(
            i,
            lows[i],
            highs[i],
            color=color,
            linewidth=1
        )

        body_low = min(
            opens[i],
            closes[i]
        )

        body_height = abs(
            closes[i] - opens[i]
        )

        if body_height == 0:
            body_height = (
                max(highs[i] - lows[i], 0.000001)
                * 0.02
            )

        rectangle = Rectangle(
            (i - 0.32, body_low),
            0.64,
            body_height,
            facecolor=color,
            edgecolor=color
        )

        ax.add_patch(rectangle)

    # ---------------------------------------------------------
    # TRADE LEVELS
    # ---------------------------------------------------------

    ax.axhline(
        entry,
        linestyle="--",
        linewidth=2,
        color="#25d9a0"
    )

    ax.axhline(
        stop_loss,
        linestyle="--",
        linewidth=2,
        color="#ff4057"
    )

    ax.axhline(
        tp1,
        linestyle="--",
        linewidth=2,
        color="#28e878"
    )

    ax.axhline(
        tp2,
        linestyle="--",
        linewidth=2,
        color="#28e878"
    )

    ax.axhline(
        tp3,
        linestyle="--",
        linewidth=2,
        color="#28e878"
    )

    ax.axhline(
        support,
        linestyle=":",
        linewidth=1.5,
        color="#438cff"
    )

    ax.axhline(
        resistance,
        linestyle=":",
        linewidth=1.5,
        color="#ff4057"
    )

    # ---------------------------------------------------------
    # LABELS
    # ---------------------------------------------------------

    x_position = len(closes) - 1

    ax.text(
        x_position,
        entry,
        f" Entry ${format_price(entry)}",
        color="white",
        fontsize=10,
        va="bottom"
    )

    ax.text(
        x_position,
        stop_loss,
        f" SL ${format_price(stop_loss)}",
        color="white",
        fontsize=10,
        va="bottom"
    )

    ax.text(
        x_position,
        tp1,
        f" TP1 ${format_price(tp1)}",
        color="white",
        fontsize=10,
        va="bottom"
    )

    ax.text(
        x_position,
        tp2,
        f" TP2 ${format_price(tp2)}",
        color="white",
        fontsize=10,
        va="bottom"
    )

    ax.text(
        x_position,
        tp3,
        f" TP3 ${format_price(tp3)}",
        color="white",
        fontsize=10,
        va="bottom"
    )

    ax.text(
        2,
        support,
        f" Support ${format_price(support)}",
        color="#63a4ff",
        fontsize=10
    )

    ax.text(
        2,
        resistance,
        f" Resistance ${format_price(resistance)}",
        color="#ff6678",
        fontsize=10
    )

    ax.set_title(
        f"{clean_symbol}/USDT • 1H",
        loc="left",
        color="white",
        fontsize=14
    )

    ax.tick_params(
        colors="#9fb0c2"
    )

    for spine in ax.spines.values():
        spine.set_color("#24384d")

    ax.grid(
        alpha=0.12
    )

    # ---------------------------------------------------------
    # VOLUME
    # ---------------------------------------------------------

    volume_ax = ax.twinx()

    volume_ax.bar(
        range(len(volumes)),
        volumes,
        alpha=0.12,
        width=0.8
    )

    volume_ax.set_ylim(
        0,
        max(volumes) * 5
    )

    volume_ax.axis("off")

    # ---------------------------------------------------------
    # RSI
    # ---------------------------------------------------------

    ax.text(
        0.01,
        0.03,
        f"RSI (14): {rsi:.1f}",
        transform=ax.transAxes,
        color="#b78cff",
        fontsize=11
    )

    # ---------------------------------------------------------
    # FOOTER
    # ---------------------------------------------------------

    footer = fig.add_subplot(grid[2])

    footer.set_facecolor("#06101d")

    footer.axis("off")

    risk_reward = signal.get(
        "risk_reward",
        "1:3"
    )

    footer.text(
        0.02,
        0.78,
        "TRADE PLAN",
        fontsize=15,
        fontweight="bold",
        color="white"
    )

    footer.text(
        0.02,
        0.48,
        f"Entry: ${format_price(entry)}",
        fontsize=11,
        color="#28e878"
    )

    footer.text(
        0.02,
        0.20,
        f"SL: ${format_price(stop_loss)}",
        fontsize=11,
        color="#ff4057"
    )

    footer.text(
        0.28,
        0.48,
        f"TP1: ${format_price(tp1)}",
        fontsize=11,
        color="white"
    )

    footer.text(
        0.28,
        0.20,
        f"TP2: ${format_price(tp2)}",
        fontsize=11,
        color="white"
    )

    footer.text(
        0.52,
        0.48,
        f"TP3: ${format_price(tp3)}",
        fontsize=11,
        color="white"
    )

    footer.text(
        0.52,
        0.20,
        f"Risk/Reward: {risk_reward}",
        fontsize=11,
        color="#ffd84d"
    )

    footer.text(
        0.75,
        0.62,
        "KEY DATA",
        fontsize=13,
        fontweight="bold",
        color="white"
    )

    footer.text(
        0.75,
        0.36,
        f"RSI: {rsi:.1f}",
        fontsize=10,
        color="#b78cff"
    )

    footer.text(
        0.75,
        0.14,
        f"Score: {score}/100",
        fontsize=10,
        color="white"
    )

    # ---------------------------------------------------------
    # SAVE
    # ---------------------------------------------------------

    plt.savefig(
        filename,
        dpi=160,
        bbox_inches="tight",
        facecolor=fig.get_facecolor()
    )

    plt.close(fig)

    print(
        f"CHART SAVED: {filename}"
    )

    print("=" * 70)

    return filename


if __name__ == "__main__":

    # Temporary test signal.
    # This will be replaced by the real selected signal
    # when we connect this module to main.py.

    test_signal = {
        "symbol": "LTCUSDT",
        "direction": "LONG",
        "score": 85,
        "entry": 67.7500,
        "stop_loss": 66.7321,
        "tp1": 68.7679,
        "tp2": 69.7857,
        "tp3": 70.8036,
        "risk_reward": "1:3"
    }

    generate_chart(test_signal)