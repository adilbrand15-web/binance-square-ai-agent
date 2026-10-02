
import os
import json
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

GEMINI_MODEL = "gemini-3.8-flash"
GROQ_MODEL = "openai/gpt-oss-20b"

GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/"
    f"models/{GEMINI_MODEL}:generateContent"
)


def format_price(value):
    """Format a numeric price without changing its value."""
    try:
        return f"{float(value):.10f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def get_signal_value(signal, *keys, default="N/A"):
    """Read a signal field using alternative key names."""
    for key in keys:
        value = signal.get(key)
        if value is not None and str(value).strip():
            return value
    return default


def build_prompt(signal):
    symbol = get_signal_value(signal, "symbol", "coin")
    direction = get_signal_value(signal, "direction")
    score = get_signal_value(signal, "score", "final_score")

    entry = get_signal_value(signal, "entry")
    stop_loss = get_signal_value(signal, "stop_loss", "sl")
    tp1 = get_signal_value(signal, "tp1")
    tp2 = get_signal_value(signal, "tp2")
    tp3 = get_signal_value(signal, "tp3")
    risk_reward = get_signal_value(
        signal, "risk_reward", "risk_reward_ratio"
    )

    trend_4h = get_signal_value(signal, "trend_4h", "4h")
    trend_1h = get_signal_value(signal, "trend_1h", "1h")
    trend_15m = get_signal_value(signal, "trend_15m", "15m")
    trend_1m = get_signal_value(signal, "trend_1m", "1m")
    rsi = get_signal_value(signal, "rsi", "rsi_15m")

    return f"""
Write a professional, concise Binance Square crypto signal post in English.

Use ONLY the signal data supplied below.
Never invent prices, indicators, news, confirmations, or guarantees.
Copy all Entry, Stop Loss, and Take Profit values exactly as supplied.
Do not recalculate or modify any trading level.
If a field is N/A, do not invent a replacement.

SIGNAL DATA
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

POST REQUIREMENTS
1. Maximum 150 words.
2. Start with a clear heading showing the coin and LONG or SHORT.
3. Include the score and supplied trading levels.
4. Briefly summarize the supplied timeframe trends and RSI when available.
5. Never call a setup guaranteed or risk-free.
6. Include a short crypto risk warning.
7. Include exactly five relevant hashtags, including the coin hashtag.
8. Use readable formatting suitable for mobile.
9. Return only the finished post. Do not include explanations or code fences.
""".strip()


def generate_gemini_post(prompt):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        print("GEMINI: API key not configured; skipping Gemini.")
        return None

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.2
        }
    }

    body = json.dumps(payload).encode("utf-8")

    for attempt in range(1, 4):
        print(f"GEMINI REQUEST {attempt}/3")

        request = Request(
            GEMINI_API_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
                "User-Agent": "BinanceSquareAIAgent/1.0"
            },
            method="POST"
        )

        try:
            with urlopen(request, timeout=60) as response:
                result = json.loads(
                    response.read().decode("utf-8")
                )

            candidates = result.get("candidates", [])
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
                    print("GEMINI: SUCCESS")
                    return text

            print("GEMINI: Response contained no usable text.")

        except HTTPError as error:
            print(f"GEMINI HTTP ERROR: {error.code}")
            try:
                error_body = error.read().decode(
                    "utf-8", errors="replace"
                )
                print(error_body[:500])
            except Exception:
                pass

            # Retry temporary server errors and rate limits.
            if error.code not in (429, 500, 502, 503, 504):
                break

        except (URLError, TimeoutError, OSError) as error:
            print(f"GEMINI NETWORK ERROR: {error}")

        except (json.JSONDecodeError, ValueError) as error:
            print(f"GEMINI RESPONSE ERROR: {error}")
            break

        if attempt < 3:
            wait_seconds = attempt * 5
            print(f"Retrying Gemini in {wait_seconds} seconds...")
            time.sleep(wait_seconds)

    print("GEMINI: Failed; trying Groq fallback.")
    return None


def generate_groq_post(prompt):
    api_key = os.environ.get("GROQ_API_KEY", "").strip()

    if not api_key:
        print("GROQ: API key not configured; fallback unavailable.")
        return None

    try:
        from groq import Groq
    except ImportError:
        print("GROQ: SDK is missing. Install the 'groq' package.")
        return None

    try:
        print(f"GROQ: Trying fallback model {GROQ_MODEL}")

        client = Groq(api_key=api_key, timeout=60.0)

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write accurate, concise crypto-analysis "
                        "posts. Follow the user's supplied data exactly. "
                        "Never invent or change trading levels."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2
        )

        text = (
            response.choices[0].message.content or ""
        ).strip()

        if text:
            print("GROQ: SUCCESS")
            return text

        print("GROQ: Response contained no usable text.")

    except Exception as error:
        print(f"GROQ ERROR: {type(error).__name__}: {error}")

    return None


def generate_ai_post(signal):
    print("\nBINANCE SQUARE AI WRITER")
    prompt = build_prompt(signal)

    # Primary provider: Gemini.
    post = generate_gemini_post(prompt)
    if post:
        print("AI PROVIDER: GEMINI")
        return post

    # Backup provider: Groq.
    print("AI WRITER: Activating Groq fallback...")
    post = generate_groq_post(prompt)

    if post:
        print("AI PROVIDER: GROQ")
        return post

    print("AI WRITER FAILED: Both providers unavailable.")
    return None


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

    generated_post = generate_ai_post(test_signal)

    if generated_post:
        print("\nGENERATED POST")
        print("-" * 50)
        print(generated_post)
        print("-" * 50)
        print("AI WRITER: ONLINE")
    else:
        print("AI WRITER: FAILED")
        raise SystemExit(1)
