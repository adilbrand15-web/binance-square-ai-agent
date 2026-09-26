import os
import json
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


GEMINI_MODEL = "gemini-3.8-flash"

GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/"
    f"models/{GEMINI_MODEL}:generateContent"
)


def build_prompt(signal):

    symbol = signal.get("symbol", "")
    direction = signal.get("direction", "")
    score = signal.get("score", "")

    entry = signal.get("entry", "")
    stop_loss = signal.get("stop_loss", "")
    tp1 = signal.get("tp1", "")
    tp2 = signal.get("tp2", "")
    tp3 = signal.get("tp3", "")

    risk_reward = signal.get("risk_reward", "")

    trend_4h = signal.get("trend_4h", "")
    trend_1h = signal.get("trend_1h", "")
    trend_15m = signal.get("trend_15m", "")
    trend_1m = signal.get("trend_1m", "")
    rsi = signal.get("rsi", "")

    return f"""
You are a professional crypto trading content writer
for Binance Square.

Create ONE short, professional crypto signal post.

Use ONLY the supplied signal data.

STRICT RULES:

1. Never invent numbers.
2. Never change Entry, SL, TP or Score.
3. Maximum 120 words.
4. Use English.
5. Make it mobile-friendly.
6. Keep the technical explanation very short.
7. Include Entry.
8. Include Stop Loss.
9. Include TP1, TP2 and TP3.
10. Include Score.
11. Include Risk/Reward.
12. Mention 4H, 1H, 15M and 1M trend.
13. Mention RSI if available.
14. Include a short risk warning.
15. Use exactly 5 relevant hashtags.
16. No long article.
17. No introduction or explanation outside the post.
18. Return ONLY the final post.

SIGNAL:

Symbol: {symbol}
Direction: {direction}
Score: {score}/100

Entry: ${entry}
Stop Loss: ${stop_loss}

TP1: ${tp1}
TP2: ${tp2}
TP3: ${tp3}

Risk/Reward: {risk_reward}

4H: {trend_4h}
1H: {trend_1h}
15M: {trend_15m}
1M: {trend_1m}

RSI: {rsi}
"""


def generate_ai_post(signal):

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("AI WRITER ERROR: GEMINI_API_KEY is missing.")
        return None

    prompt = build_prompt(signal)

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
        ]
    }

    data = json.dumps(payload).encode("utf-8")

    request = Request(
        GEMINI_API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key
        },
        method="POST"
    )

    max_attempts = 3

    for attempt in range(1, max_attempts + 1):

        print(
            f"AI WRITER REQUEST "
            f"{attempt}/{max_attempts}"
        )

        try:

            with urlopen(
                request,
                timeout=60
            ) as response:

                result = json.loads(
                    response.read().decode("utf-8")
                )

            candidates = result.get(
                "candidates",
                []
            )

            if not candidates:
                print(
                    "AI WRITER ERROR: "
                    "No candidates returned."
                )

                return None

            parts = candidates[0].get(
                "content",
                {}
            ).get(
                "parts",
                []
            )

            text_parts = []

            for part in parts:

                if "text" in part:
                    text_parts.append(
                        part["text"]
                    )

            post = "\n".join(
                text_parts
            ).strip()

            if post:

                return post

            print(
                "AI WRITER ERROR: "
                "Empty response."
            )

            return None

        except HTTPError as error:

            print(
                f"AI WRITER HTTP ERROR: "
                f"{error.code}"
            )

            if error.code == 503:

                if attempt < max_attempts:

                    wait_time = attempt * 10

                    print(
                        f"Model temporarily "
                        f"unavailable."
                    )

                    print(
                        f"Retrying in "
                        f"{wait_time} seconds..."
                    )

                    time.sleep(
                        wait_time
                    )

                    continue

                print(
                    "AI WRITER FAILED "
                    "AFTER RETRIES."
                )

                return None

            try:

                error_body = (
                    error.read()
                    .decode("utf-8")
                )

                print(error_body)

            except Exception:
                pass

            return None

        except URLError as error:

            print(
                f"AI WRITER NETWORK ERROR: "
                f"{error}"
            )

            if attempt < max_attempts:

                wait_time = attempt * 10

                print(
                    f"Retrying in "
                    f"{wait_time} seconds..."
                )

                time.sleep(
                    wait_time
                )

                continue

            return None

        except Exception as error:

            print(
                f"AI WRITER ERROR: "
                f"{error}"
            )

            return None

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

        "trend_4h": "BULLISH",

        "trend_1h": "BULLISH",

        "trend_15m": "BULLISH",

        "trend_1m": "BULLISH",

        "rsi": 60.0
    }

    print("=" * 70)

    print(
        "BINANCE SQUARE AI WRITER"
    )

    print("=" * 70)

    post = generate_ai_post(
        test_signal
    )

    if post:

        print(
            "\nGENERATED POST"
        )

        print("-" * 70)

        print(post)

        print("-" * 70)

        print(
            "AI WRITER: ONLINE"
        )

    else:

        print(
            "AI WRITER: FAILED"
        )

    print("=" * 70)