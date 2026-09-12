import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

funds = {
    "Conservative": {
        "VWELX": "Vanguard Wellington Fund",
        "AGG": "iShares Core U.S. Aggregate Bond ETF",
        "VBTLX": "Vanguard Total Bond Market Index Fund"
    },
    "Moderate": {
        "VFIAX": "Vanguard 500 Index Fund Admiral Shares",
        "VTMFX": "Vanguard Tax-Managed Balanced Fund",
        "PRBLX": "Parnassus Core Equity Fund"
    },
    "Aggressive": {
        "FSPTX": "Fidelity Select Semiconductors Portfolio",
        "VSMAX": "Vanguard Small-Cap Index Fund Admiral Shares",
        "VTIAX": "Vanguard Total International Stock Index Fund",
        "FCPGX": "Fidelity Small Cap Growth Fund"
    }
}

def setup_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    return webdriver.Chrome(options=options)

def get_morningstar_risk(driver):
    risk_data = {"3y": "N/A", "5y": "N/A", "10y": "N/A"}
    try:
        # Ratings & Risk tab may be a button or a link
        try:
            tab = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Ratings & Risk')]"))
            )
        except TimeoutException:
            tab = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Ratings & Risk')]"))
            )
        tab.click()
        time.sleep(3)

        for term in ["3-Year", "5-Year", "10-Year"]:
            try:
                label = driver.find_element(By.XPATH, f"//div[text()='{term}']/following-sibling::div")
                risk_data[term[:2].lower() + "y"] = label.text.strip()
            except:
                pass

    except Exception as e:
        print(f"[Risk Tab Error] {e}")

    return risk_data

def extract_volatility_measures(driver):
    data = {
        "Upside Capture (Category)": "N/A",
        "Downside Capture (Category)": "N/A",
        "Max Drawdown (Investment)": "N/A",
        "Drawdown Peak Date": "N/A",
        "Drawdown Valley Date": "N/A",
        "Drawdown Duration": "N/A"
    }

    try:
        # Scroll to bottom to trigger load of lower sections
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.75);")
        time.sleep(4)

        # Find volatility section
        section = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//h2[contains(text(), 'Market Volatility Measures')]/.."))
        )

        rows = section.find_elements(By.XPATH, ".//div[contains(@class, 'cell')]")

        for i, cell in enumerate(rows):
            text = cell.text.strip()
            if text == "Upside":
                data["Upside Capture (Category)"] = rows[i + 2].text.strip()
            elif text == "Downside":
                data["Downside Capture (Category)"] = rows[i + 2].text.strip()
            elif text == "Maximum":
                data["Max Drawdown (Investment)"] = rows[i + 1].text.strip()
            elif text == "Peak":
                data["Drawdown Peak Date"] = rows[i + 1].text.strip()
            elif text == "Valley":
                data["Drawdown Valley Date"] = rows[i + 1].text.strip()
            elif text == "Max Duration":
                data["Drawdown Duration"] = rows[i + 1].text.strip()

    except Exception as e:
        print(f"[Volatility Section Error] {e}")

    return data

def scrape_all():
    driver = setup_driver()
    all_data = []

    for risk_level, fund_dict in funds.items():
        for ticker, name in fund_dict.items():
            print(f"Scraping {ticker} - {name}")
            url = f"https://www.morningstar.com/funds/xnas/{ticker.lower()}/quote"
            try:
                driver.get(url)
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                time.sleep(3)

                risk = get_morningstar_risk(driver)
                volatility = extract_volatility_measures(driver)

                all_data.append({
                    "Risk Profile": risk_level,
                    "Ticker": ticker,
                    "Name": name,
                    "3-Year Risk": risk["3y"],
                    "5-Year Risk": risk["5y"],
                    "10-Year Risk": risk["10y"],
                    **volatility
                })

            except Exception as e:
                print(f"[{ticker}] Load Failed: {e}")

    driver.quit()
    return pd.DataFrame(all_data)

if __name__ == "__main__":
    df = scrape_all()
    print(df)
    df.to_csv("morningstar_risk_volatility.csv", index=False)
