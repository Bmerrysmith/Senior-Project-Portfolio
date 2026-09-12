import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json

tickers = {
    "Conservative": ["VWELX", "VBTLX", "AGG"],
    "Moderate":     ["VFIAX", "VTMFX", "PRBLX"],
    "Aggressive":   ["FSPTX", "VSMAX", "VTIAX", "FCPGX"]
}

risk_free_rate = 0.02  
min_rows_per_year = {3: 50, 5: 125, 10: 250}
periods = [3, 5, 10]

def calculate_sortino_annual(returns, daily_mar):
    daily_excess = returns - daily_mar
    downside_returns = returns[returns < daily_mar]
    if len(downside_returns) == 0:
        return np.inf
    daily_downside_dev = np.sqrt(np.mean((downside_returns - daily_mar) ** 2))
    daily_excess_mean = np.mean(daily_excess)
    annual_excess   = daily_excess_mean   * 252
    annual_downside = daily_downside_dev  * np.sqrt(252)
    if annual_downside == 0:
        return np.inf
    return annual_excess / annual_downside

results = []

for category, symbol_list in tickers.items():
    for symbol in symbol_list:
        for yrs in periods:
            end_date = datetime.today()
            start_date = end_date - timedelta(days=365 * yrs)

            data = yf.download(
                symbol,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                progress=False,
            )

            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            row_count = len(data)
            minimum_required = min_rows_per_year[yrs]

            if "Close" not in data.columns or row_count < minimum_required:
                results.append({
                    "Category": category,
                    "Ticker":   symbol,
                    "Years":    yrs,
                    "Sortino (Annualized)": "N/A"
                })
                continue

            data["Return"] = data["Close"].pct_change().dropna()
            returns = data["Return"].dropna()
            daily_mar = risk_free_rate / 252

            sortino_ann = calculate_sortino_annual(returns, daily_mar)
            sortino_display = (
                "Inf" if np.isinf(sortino_ann)
                else round(sortino_ann, 4)
            )

            results.append({
                "Category": category,
                "Ticker":   symbol,
                "Years":    yrs,
                "Sortino (Annualized)": sortino_display
            })

print(json.dumps(results, indent=2))

with open("sortino.json", "w") as f:
    json.dump(results, f, indent=2)
