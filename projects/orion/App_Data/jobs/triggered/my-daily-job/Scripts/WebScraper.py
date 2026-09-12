from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json
import time
import random

target_metrics = {
    "Mean Annual Return",
    "Sharpe Ratio",
    "Treynor Ratio",
    "Standard Deviation",
    "Alpha"
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.5735.133 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

risk_free_rate = 0.02
min_rows_per_year = {3: 50, 5: 125, 10: 250}
periods = [3, 5, 10]

tickers = {
    "Conservative": ["VWELX", "VBTLX", "AGG", "FTBFX", "BOND", "VCIT"],
    "Moderate":     ["VFIAX", "VTMFX", "PRBLX", "MAMOX", "FMTIX", "VBAIX"],
    "Aggressive":   ["FSPTX", "VSMAX", "VTIAX", "FCPGX"]
}

def get_driver():
    options = uc.ChromeOptions()
    options.headless = True
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    user_agent = random.choice(USER_AGENTS)
    options.add_argument(f'user-agent={user_agent}')
    driver = uc.Chrome(options=options)
    return driver

def scrape_selected_risk_metrics(ticker, max_retries=3):
    url = f"https://finance.yahoo.com/quote/{ticker}/risk"
    attempt = 0
    while attempt < max_retries:
        driver = None
        try:
            driver = get_driver()
            driver.get(url)
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
            soup = BeautifulSoup(driver.page_source, "html.parser")
            rows = soup.find_all("tr", class_="yf-1m2lefb useStripingColumn")
            results = {}
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 7:
                    metric_name = cols[0].text.strip()
                    if metric_name in target_metrics:
                        results[metric_name] = {
                            "3y": cols[1].text.strip(),
                            "5y": cols[3].text.strip(),
                            "10y": cols[5].text.strip()
                        }
            return results
        except Exception as e:
            print(f"Attempt {attempt+1} failed for {ticker}: {e}")
            attempt += 1
            time.sleep(random.uniform(2, 5))
        finally:
            if driver:
                driver.quit()
    print(f"Failed to get data for {ticker} after {max_retries} attempts.")
    return {}

def calculate_sortino_annual(returns, daily_mar):
    daily_excess = returns - daily_mar
    downside_returns = returns[returns < daily_mar]
    if len(downside_returns) == 0:
        return None
    daily_downside_dev = np.sqrt(np.mean((downside_returns - daily_mar) ** 2))
    daily_excess_mean = np.mean(daily_excess)
    annual_excess   = daily_excess_mean   * 252
    annual_downside = daily_downside_dev  * np.sqrt(252)
    if annual_downside == 0:
        return None
    return round(annual_excess / annual_downside, 4)

def fetch_sortino(ticker, years):
    end_date = datetime.today()
    start_date = end_date - timedelta(days=365 * years)
    try:
        data = yf.download(
            ticker,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            progress=False,
        )
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        row_count = len(data)
        minimum_required = min_rows_per_year[years]
        if "Close" not in data.columns or row_count < minimum_required:
            return None
        data["Return"] = data["Close"].pct_change().dropna()
        returns = data["Return"].dropna()
        daily_mar = risk_free_rate / 252
        return calculate_sortino_annual(returns, daily_mar)
    except Exception as e:
        print(f"Error fetching Sortino for {ticker} {years}y: {e}")
        return None

if __name__ == "__main__":
    all_results = {}

    for category, symbol_list in tickers.items():
        for symbol in symbol_list:
            print(f"Scraping {symbol}...")

            yahoo_data = scrape_selected_risk_metrics(symbol)
            all_metrics = {}

            # Copy over Yahoo metrics if present
            for metric in target_metrics:
                all_metrics[metric] = {}
                for yrs in ["3y", "5y", "10y"]:
                    all_metrics[metric][yrs] = yahoo_data.get(metric, {}).get(yrs, "N/A")

            # Add calculated Sortino for each period
            sortino_dict = {}
            for yrs in periods:
                sortino = fetch_sortino(symbol, yrs)
                label = f"{yrs}y"
                sortino_dict[label] = "N/A" if sortino is None else sortino
            all_metrics["Sortino Ratio"] = sortino_dict

            # Store by ticker
            all_results[symbol] = {
                "Category": category,
                "Metrics": all_metrics
            }

            time.sleep(random.uniform(2.5, 4.5))

    # Save results to JSON
    with open("fund_risk_metrics.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print("All fund data saved to 'fund_risk_metrics.json'")
