import os
import json
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# ============================================================
# AI PROVIDER SETTINGS
# ============================================================

GEMINI_MODEL = "gemini-3.8-flash"
GROQ_MODEL = "openai/gpt-oss-20b"

GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/"
    f"models/{GEMINI_MODEL}:generateContent"
)


# ============================================================
# PRICE FORMATTING
# ============================================================

def format_price(value):
    """
    Format crypto prices cleanly without ugly floating-point
    artifacts.

    Examples:
    2749.041428571 -> 2749.04
    0.2488000000   -> 0.2488
    0.0558400000   -> 0.05584
    86112.56321    -> 86112.56
    """

    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    if number >= 1000:
        decimals = 2

    elif number >= 100:
        decimals = 3

    elif number >= 1:
        decimals = 4

    elif number >= 0.1:
        decimals = 4

    elif number >= 0.01:
        decimals = 5

    elif number >= 0.001:
        decimals = 6

    else:
        decimals = 8

    formatted = f"{number:.{decimals}f}"

    # Remove unnecessary zeros.
    formatted = formatted.rstrip("0").rstrip(".")

    return formatted


# ============================================================
# GENERIC SIGNAL VALUE READER
# ============================================================

def get_signal_value(signal, *keys, default="N/A"):
    """
    Try multiple possible field names.
    This makes the AI writer compatible with different
    signal dictionary naming conventions.
    """

    if not isinstance(signal, dict):
        return default

    for key in keys:

        value = signal.get(key)

        if value is not None:
            text = str(value).strip()

            if text and text.lower() not in (
                "none",
                "null",
                "nan",
            ):
                return value

    return default


# ============================================================
# RSI DETECTOR
# ============================================================

def get_rsi(signal):
    """
    Detect RSI even if the signal engine uses a slightly
    different field name.

    Supported examples:
    rsi
    RSI
    rsi_14
    rsi14
    rsi_15m
    rsi15m
    rsi_1m
    rsi1m
    rsi_1h
    rsi1h
    rsi_4h
    rsi4h
    rsi_value
    """

    possible_keys = [
        "rsi",
        "RSI",
        "rsi_14",
        "rsi14",
        "rsi_value",
        "rsi_15m",
        "rsi15m",
        "rsi_1m",
        "rsi1m",
        "rsi_1h",
        "rsi1h",
        "rsi_4h",
        "rsi4h",
    ]

    value = get_signal_value(
        signal,
        *possible_keys,
        default=None
    )

    if value is not None:

        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return str(value)

    # --------------------------------------------------------
    # Last-resort automatic RSI field detection.
    # --------------------------------------------------------

    if isinstance(signal, dict):

        for key, value in signal.items():

            key_lower = str(key).lower()

            if "rsi" in key_lower:

                try:
                    return round(float(value), 2)
                except (TypeError, ValueError):
                    continue

    return "N/A"


# ============================================================
# TREND DETECTOR
# ============================================================

def get_trend(signal, timeframe):
    """
    Read timeframe trend using both the new and old field names.
    """

    timeframe = timeframe.lower()

    possible_keys = [
        f"trend_{timeframe}",
        timeframe,
        timeframe.upper(),
        f"{timeframe}_trend",
    ]

    return get_signal_value(
        signal,
        *possible_keys,
        default="N/A"
    )


# ============================================================
# BUILD AI PROMPT
# ============================================================

def build_prompt(signal):

    symbol = get_signal_value(
        signal,
        "symbol",
        "coin",
        "pair"
    )

    direction = get_signal_value(
        signal,
        "direction"
    )

    score = get_signal_value(
        signal,
        "score",
        "final_score"
    )

    # --------------------------------------------------------
    # Trading levels
    # --------------------------------------------------------

    entry_raw = get_signal_value(
        signal,
        "entry"
    )

    stop_loss_raw = get_signal_value(
        signal,
        "stop_loss",
        "sl",
        "stoploss"
    )

    tp1_raw = get_signal_value(
        signal,
        "tp1",
        "target1"
    )

    tp2_raw = get_signal_value(
        signal,
        "tp2",
        "target2"
    )

    tp3_raw = get_signal_value(
        signal,
        "tp3",
        "target3"
    )

    risk_reward = get_signal_value(
        signal,
        "risk_reward",
        "risk_reward_ratio",
        "rr",
        "r_r"
    )

    # --------------------------------------------------------
    # Clean price representation
    # --------------------------------------------------------

    entry = format_price(entry_raw)
    stop_loss = format_price(stop_loss_raw)
    tp1 = format_price(tp1_raw)
    tp2 = format_price(tp2_raw)
    tp3 = format_price(tp3_raw)

    # --------------------------------------------------------
    # Multi-timeframe trends
    # --------------------------------------------------------

    trend_4h = get_trend(signal, "4h")
    trend_1h = get_trend(signal, "1h")
    trend_15m = get_trend(signal, "15m")
    trend_1m = get_trend(signal, "1m")

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    rsi = get_rsi(signal)

    # --------------------------------------------------------
    # Prompt
    # --------------------------------------------------------

    prompt = f"""
You are the AI writer for a professional Binance Square
crypto signal system.

Create ONE concise crypto trading signal post.

IMPORTANT DATA RULES:

- Use ONLY the supplied signal data.
- Never invent missing information.
- Never invent news.
- Never invent technical indicators.
- Never invent confirmations.
- Never claim guaranteed profit.
- Never claim a trade is risk-free.
- Never change the direction.
- Never change the score.
- Never change Entry, Stop Loss, TP1, TP2 or TP3.
- Do not recalculate trading levels.
- The formatted price values below are the exact values
  supplied by the signal engine, only displayed without
  floating-point calculation artifacts.

============================================================
SIGNAL DATA
============================================================

Symbol: {symbol}
Direction: {direction}
Final Score: {score}/100

Entry: {entry}
Stop Loss: {stop_loss}
TP1: {tp1}
TP2: {tp2}
TP3: {tp3}

Risk/Reward: {risk_reward}

4H Trend: {trend_4h}
1H Trend: {trend_1h}
15M Trend: {trend_15m}
1M Trend: {trend_1m}

RSI: {rsi}

============================================================
POST FORMAT
============================================================

Create the post in English.

Maximum 150 words.

Use this structure:

[Coin] | [LONG/SHORT]

Signal Score: X/100
Risk/Reward: X

Market Trend:
• 4H: ...
• 1H: ...
• 15M: ...
• 1M: ...
• RSI: ...

Trade Levels:
• Entry: ...
• Stop Loss: ...
• TP1: ...
• TP2: ...
• TP3: ...

Risk Warning: short responsible crypto-risk warning.

Then exactly FIVE relevant hashtags.

============================================================
IMPORTANT
============================================================

1. Use the exact supplied price values.
2. Do NOT add extra decimal digits.
3. Do NOT remove meaningful decimal digits.
4. Do NOT calculate new prices.
5. If RSI is N/A, write RSI: N/A.
6. If a trend is N/A, write N/A.
7. Keep the post mobile-friendly.
8. Do not use a table.
9. Do not add analysis outside the post.
10. Return ONLY the final Binance Square post.
11. Do not use code fences.
12. Exactly five hashtags.

The coin hashtag must be included.

Example hashtag style:

#ETH #ETHUSDT #CryptoSignals #Binance #CryptoTrading

Do not add a sixth hashtag.
""".strip()

    return prompt


# ============================================================
# GEMINI AI
# ============================================================

def generate_gemini_post(prompt):

    api_key = os.environ.get(
        "GEMINI_API_KEY",
        ""
    ).strip()

    if not api_key:

        print(
            "GEMINI: API key not configured; "
            "skipping Gemini."
        )

        return None

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2
        }
    }

    body = json.dumps(payload).encode("utf-8")

    for attempt in range(1, 4):

        print(
            f"GEMINI REQUEST {attempt}/3"
        )

        request = Request(
            GEMINI_API_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
                "User-Agent":
                    "BinanceSquareAIAgent/1.0"
            },
            method="POST"
        )

        try:

            with urlopen(
                request,
                timeout=60
            ) as response:

                result = json.loads(
                    response.read().decode(
                        "utf-8"
                    )
                )

            candidates = result.get(
                "candidates",
                []
            )

            if candidates:

                parts = (
                    candidates[0]
                    .get("content", {})
                    .get("parts", [])
                )

                text = "\n".join(
                    part.get("text", "")
                    for part in parts
                    if part.get("text")
                ).strip()

                if text:

                    print(
                        "GEMINI: SUCCESS"
                    )

                    return text

            print(
                "GEMINI: Response contained "
                "no usable text."
            )

        except HTTPError as error:

            print(
                f"GEMINI HTTP ERROR: "
                f"{error.code}"
            )

            try:

                error_body = (
                    error.read()
                    .decode(
                        "utf-8",
                        errors="replace"
                    )
                )

                print(
                    error_body[:500]
                )

            except Exception:
                pass

            # Retry temporary errors and rate limits.
            if error.code not in (
                429,
                500,
                502,
                503,
                504
            ):
                break

        except (
            URLError,
            TimeoutError,
            OSError
        ) as error:

            print(
                f"GEMINI NETWORK ERROR: "
                f"{error}"
            )

        except (
            json.JSONDecodeError,
            ValueError
        ) as error:

            print(
                f"GEMINI RESPONSE ERROR: "
                f"{error}"
            )

            break

        if attempt < 3:

            wait_seconds = attempt * 5

            print(
                f"Retrying Gemini in "
                f"{wait_seconds} seconds..."
            )

            time.sleep(
                wait_seconds
            )

    print(
        "GEMINI: Failed; "
        "trying Groq fallback."
    )

    return None


# ============================================================
# GROQ AI FALLBACK
# ============================================================

def generate_groq_post(prompt):

    api_key = os.environ.get(
        "GROQ_API_KEY",
        ""
    ).strip()

    if not api_key:

        print(
            "GROQ: API key not configured; "
            "fallback unavailable."
        )

        return None

    try:

        from groq import Groq

    except ImportError:

        print(
            "GROQ: SDK is missing. "
            "Install the 'groq' package."
        )

        return None

    try:

        print(
            f"GROQ: Trying fallback model "
            f"{GROQ_MODEL}"
        )

        client = Groq(
            api_key=api_key,
            timeout=60.0
        )

        response = (
            client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a professional "
                            "Binance Square crypto "
                            "signal post writer. "
                            "Follow supplied data "
                            "exactly. Never invent "
                            "or change trading levels."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2
            )
        )

        text = (
            response
            .choices[0]
            .message
            .content
            or ""
        ).strip()

        if text:

            print(
                "GROQ: SUCCESS"
            )

            return text

        print(
            "GROQ: Response contained "
            "no usable text."
        )

    except Exception as error:

        print(
            f"GROQ ERROR: "
            f"{type(error).__name__}: "
            f"{error}"
        )

    return None


# ============================================================
# MAIN AI WRITER
# ============================================================

def generate_ai_post(signal):

    print(
        "\nBINANCE SQUARE AI WRITER"
    )

    prompt = build_prompt(
        signal
    )

    # --------------------------------------------------------
    # PRIMARY: GEMINI
    # --------------------------------------------------------

    post = generate_gemini_post(
        prompt
    )

    if post:

        print(
            "AI PROVIDER: GEMINI"
        )

        return post

    # --------------------------------------------------------
    # FALLBACK: GROQ
    # --------------------------------------------------------

    print(
        "AI WRITER: Activating "
        "Groq fallback..."
    )

    post = generate_groq_post(
        prompt
    )

    if post:

        print(
            "AI PROVIDER: GROQ"
        )

        return post

    # --------------------------------------------------------
    # BOTH FAILED
    # --------------------------------------------------------

    print(
        "AI WRITER FAILED: "
        "Both providers unavailable."
    )

    return None


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    test_signal = {

        "symbol": "MUBARAKUSDT",

        "direction": "LONG",

        "score": 100,

        "entry": 0.055840,

        "stop_loss": 0.054067,

        "tp1": 0.057613,

        "tp2": 0.059386,

        "tp3": 0.061160,

        "risk_reward": "1:3",

        "4h": "BULLISH",

        "1h": "BULLISH",

        "15m": "BULLISH",

        "1m": "BULLISH",

        "rsi": 60.0
    }

    generated_post = (
        generate_ai_post(
            test_signal
        )
    )

    if generated_post:

        print(
            "\nGENERATED POST"
        )

        print(
            "-" * 60
        )

        print(
            generated_post
        )

        print(
            "-" * 60
        )

        print(
            "AI WRITER: ONLINE"
        )

    else:

        print(
            "AI WRITER: FAILED"
        )

        raise SystemExit(1)