import json
from pathlib import Path

SOURCE = Path("data/predictions/latest.json")
OUTPUT = Path("data/predictions/history")
OUTPUT.mkdir(parents=True, exist_ok=True)

if not SOURCE.exists():
    raise SystemExit("Prediction data not found")

data = json.loads(SOURCE.read_text(encoding="utf-8"))

forecasts = data.get("forecasts", [])

if not forecasts:
    raise SystemExit("No forecasts found")

dates = {item["as_of_date"] for item in forecasts}

if len(dates) != 1:
    raise SystemExit("Forecast dates do not match")

date_text = dates.pop()
destination = OUTPUT / f"{date_text}.json"

if destination.exists():
    print(f"Already saved: {destination}")
else:
    destination.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"Saved: {destination}")
