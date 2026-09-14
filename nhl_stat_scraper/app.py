# Flask API
# app.py
from flask import Flask, jsonify, request
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from scraper.scraper_functions import (
     scrape_stat_leaders,
     close_cookie_window  
)

app = Flask(__name__)
CORS(app)

# Driver SetUp Function

def setup_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")   
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 15)

    return driver, wait

# Main Page

@app.route("/")
def index():
    return jsonify({"message": "Welcome to the NHL Stats API!"})

# Skater Goal Leaders

@app.route("/stats/skaters/goals", methods=["GET"])
def get_goal_stats():
    
    print("Setting Up Driver...")
    driver, wait = setup_driver()

    driver.get("https://www.nhl.com/stats")

    try:
        close_cookie_window(driver, wait)
        count = request.args.get("count", default=6, type=int)
        gameType = request.args.get("gameType", default="Regular Season")
        data = scrape_stat_leaders(driver, wait, stat_title = "Goals", column_index = 8, label = "goals", is_first=True, count=count, gameType=gameType)

        return jsonify(data)
    finally:
        driver.quit()

# Skater Assists Leaders

@app.route("/stats/skaters/assists", methods=["GET"])
def get_assists_stats():

    print("Setting Up Driver...")
    driver, wait = setup_driver()

    driver.get("https://www.nhl.com/stats")

    try:
        close_cookie_window(driver, wait)
        count = request.args.get("count", default=6, type=int)
        gameType = request.args.get("gameType", default="Regular Season")
        data = scrape_stat_leaders(driver, wait, stat_title = "Assists", column_index = 9, label = "assists", is_first=True, count=count, gameType=gameType)

        return jsonify(data)
    finally:
        driver.quit()

# Skater Point Leaders

@app.route("/stats/skaters/points", methods=["GET"])
def get_points_stats():

    print("Setting Up Driver..")
    driver, wait = setup_driver()

    driver.get("https://www.nhl.com/stats")

    try:
        close_cookie_window(driver, wait)
        count = request.args.get("count", default=6, type=int)
        gameType = request.args.get("gameType", default="Regular Season")
        data = scrape_stat_leaders(driver, wait, stat_title = "Points", column_index = 10, label = "points", is_first=True, count=count, gameType=gameType)

        return jsonify(data)
    finally:
        driver.quit()

        
# Goalie SV% Leaders

@app.route("/stats/goalies/sv", methods=["GET"])
def get_sv_stats():

    print("Setting Up Driver..")
    driver, wait = setup_driver()

    driver.get("https://www.nhl.com/stats")

    try:
        close_cookie_window(driver, wait)
        count = request.args.get("count", default=6, type=int)
        gameType = request.args.get("gameType", default="Regular Season")
        data = scrape_stat_leaders(driver, wait, stat_title = "Save Percentage", column_index = 15, label = "save_percentage", is_first=True, playerType="goalie", count=count, gameType=gameType)

        return jsonify(data)
    finally:
        driver.quit()

# Goalie GAA Leaders

@app.route("/stats/goalies/gaa", methods=["GET"])
def get_gaa_stats():

    print("Setting Up Driver..")
    driver, wait = setup_driver()

    driver.get("https://www.nhl.com/stats")

    try:
        close_cookie_window(driver, wait)
        count = request.args.get("count", default=6, type=int)
        gameType = request.args.get("gameType", default="Regular Season")
        data = scrape_stat_leaders(driver, wait, stat_title = "Goals Against Average", column_index = 16, label = "goals_against_allowed", is_first=True, playerType="goalie", count=count, gameType=gameType)

        return jsonify(data)
    finally:
        driver.quit()

# Goalie SO Leaders

@app.route("/stats/goalies/so", methods=["GET"])
def get_so_stats():

    print("Setting Up Driver..")
    driver, wait = setup_driver()

    driver.get("https://www.nhl.com/stats")

    try:
        close_cookie_window(driver, wait)
        count = request.args.get("count", default=6, type=int)
        gameType = request.args.get("gameType", default="Regular Season")
        data = scrape_stat_leaders(driver, wait, stat_title = "Shutouts", column_index = 18, label = "shutouts", is_first=True, playerType="goalie", count=count, gameType=gameType)

        return jsonify(data)
    finally:
        driver.quit()

if __name__ == "__main__":
    app.run()
