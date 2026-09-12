import requests
from bs4 import BeautifulSoup
import json

tickers = [
    "VWELX", "VBTLX", "AGG", "FTBFX", "BOND", "VCIT",
    "VFIAX", "VTMFX", "PRBLX", "MAMOX", "FMTIX", "VBAIX",
    "FSPTX", "VSMAX", "VTIAX", "FCPGX"
]

def get_years_up_down(ticker):
    url = f"https://finance.yahoo.com/quote/{ticker}/risk/"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers)
    soup = BeautifulSoup(resp.text, "html.parser")

    years_data = {"years_up": None, "years_down": None}
    try:
        # Find all rows with "Number of Years"
        for row in soup.find_all("tr"):
            if "Number of Years" in row.text:
                tds = row.find_all("td")
                if len(tds) > 1:
                    label = tds[0].text.strip()
                    value = tds[1].text.strip()
                    if "Up" in label:
                        years_data["years_up"] = value
                    elif "Down" in label:
                        years_data["years_down"] = value
    except Exception as e:
        print(f"{ticker}: Error - {e}")
    return years_data

results = {}
for ticker in tickers:
    print(f"Scraping {ticker}...")
    results[ticker] = get_years_up_down(ticker)
    print(f"{ticker}: {results[ticker]}")

with open("years_up_down_bs4.json", "w") as f:
    json.dump(results, f, indent=2)

print("Saved results to years_up_down_bs4.json")
