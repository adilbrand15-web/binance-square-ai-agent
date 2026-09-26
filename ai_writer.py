import os
import json
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

    prompt = f"""
You are a professional crypto trading content writer for Binance Square.

Create ONE SHORT crypto signal post using ONLY the data provided below.

IMPORTANT RULES:
- Do NOT invent or change any numbers.
- Do NOT create a different entry, SL, TP or score.
- Keep it short and mobile-friendly.
- Maximum 120 words.
- Use clear English.
- Do not write a long article.
- Mention the technical setup briefly.
- Include Entry, SL, TP1, TP2 and TP3.
- Include the signal score.
- Include Risk/Reward.
- Mention the 4H, 1H, 15M and 1M trend.
- Mention RSI only if available.
- Add a short risk disclaimer.
- Use exactly 5 relevant hashtags.
- Do not use more than 5 hashtags.
- Do not add a title such as "Here is your post".
- Return ONLY the final Binance Square post.

SIGNAL DATA:

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

    return prompt


def generate_ai_post(signal):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("AI WRITER ERROR: GEMINI_API_KEY is not configured.")
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
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 300
        }
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

    try:
        with urlopen(request, timeout=60) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        candidates = result.get("candidates", [])

        if not candidates:
            print("AI WRITER ERROR: No response from Gemini.")
            return None

        parts = candidates[0].get("content", {}).get("parts", [])

        text_parts = []

        for part in parts:
            if "text" in part:
                text_parts.append(part["text"])

        post = "\n".join(text_parts).strip()

        if not post:
            print("AI WRITER ERROR: Empty generated post.")
            return None

        return post

    except HTTPError as error:
        print(
            f"AI WRITER HTTP ERROR: "
            f"{error.code}"
        )

        try:
            print(
                error.read().decode("utf-8")
            )
        except Exception:
            pass

        return None

    except URLError as error:
        print(
            f"AI WRITER NETWORK ERROR: "
            f"{error}"
        )

        return None

    except Exception as error:
        print(
            f"AI WRITER ERROR: "
            f"{error}"
        )

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
    print("BINANCE SQUARE AI WRITER")
    print("=" * 70)

    post = generate_ai_post(
        test_signal
    )

    if post:
        print("\nGENERATED POST")
        print("-" * 70)
        print(post)
        print("-" * 70)
        print("AI WRITER: ONLINE")
    else:
        print("AI WRITER: FAILED")

    print("=" * 70)