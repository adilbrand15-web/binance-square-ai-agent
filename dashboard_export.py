import json
from datetime import datetime, timezone
from database import get_all_signals


def export_dashboard_data():

    all_signals = get_all_signals()
    signals = []

    for row in all_signals:

        signals.append({
            "id": row[0],
            "symbol": row[1],
            "direction": row[2],
            "score": row[3],

            "timeframes": {
                "4h": row[4],
                "1h": row[5],
                "15m": row[6],
                "1m": row[7],
            },

            "entry": row[8],
            "stop_loss": row[9],
            "tp1": row[10],
            "tp2": row[11],
            "tp3": row[12],
            "risk_reward": row[13],
            "signal_time": row[14],

            "published": row[15],
            "selected": row[16],
            "chart_saved": row[17],
            "post_id": row[18],
            "post_link": row[19],
            "outcome": row[20],
            "created_at": row[21],
            "rsi": row[22],
        })

    today = datetime.now(timezone.utc).date().isoformat()

    today_signals = [
        signal for signal in signals
        if str(signal["created_at"] or "").startswith(today)
        or str(signal["signal_time"] or "").startswith(today)
    ]

    data = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "summary": {
            "total_saved_signals": len(signals),
            "today_saved_signals": len(today_signals),
            "today_published_signals": sum(
                1 for signal in today_signals
                if signal["published"] == 1
            ),
            "total_published_signals": sum(
                1 for signal in signals
                if signal["published"] == 1
            ),
        },

        "signals": signals,
    }

    with open(
        "dashboard_data.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
            default=str
        )

    print("Dashboard JSON export successful.")
    print("Total signals:", len(signals))
    print("Today's signals:", len(today_signals))


if __name__ == "__main__":
    export_dashboard_data()