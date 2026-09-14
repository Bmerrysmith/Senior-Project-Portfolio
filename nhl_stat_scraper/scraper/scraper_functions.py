# NHL Scraper Functions

from flask import request
from selenium.webdriver.common.by import By
from selenium.webdriver import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
import time
import datetime

now = datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")

# Wait for Spinner to Close

def wait_for_spinner_to_disappear(wait):
    try:
        wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "loading-container")))
    except Exception as e:
        print("Spinner may not be present or already hidden:", e)

# Close Cookie Window

def close_cookie_window(driver, wait):
    try:
        driver.maximize_window()
        # Checks to see if cookie banner is present
        cookieAccept = driver.find_element(By.XPATH, "//button[contains(text(), 'I Understand')]")
        cookieAccept.click()
        print("\nCookie window close successfully!\n")

    except Exception as e:
        print("\nError finding or closing cookie banner: " , e, "\n") 

# Click Stat Tab

def click_stat_tab(driver, wait):

    wait_for_spinner_to_disappear(wait)
    statsElement = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'STATS')]")))
    statsElement.click()

# Click Player Section

def click_player_section(driver, wait, playerType):
    wait_for_spinner_to_disappear(wait)
    tab_id = "goalies" if playerType == "goalie" else "skaters"
    skater_tab = wait.until(EC.element_to_be_clickable((By.ID, tab_id)))
    skater_tab.click()

# Click Game Type

def click_game_type(driver, wait, gameType):
    wait_for_spinner_to_disappear(wait)
    
    print(f"Selecting game type: {gameType}")
    
    try:
        # More robust selector using aria-label
        dropdown_button = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, 'input[aria-label="Game Type"]')
        ))
        dropdown_button.click()

        # Wait for dropdown option and click it
        game_type_option = wait.until(EC.element_to_be_clickable(
            (By.XPATH, f"//div[@role='listbox' or @role='menu']//li[normalize-space()='{gameType}'] | "
                           f"//div[@role='listbox' or @role='menu']//button[normalize-space()='{gameType}']")
            )
        )
        game_type_option.click()

        print(f"✅ Clicked game type: {gameType}")
        time.sleep(1)

    except Exception as e:
        print(f"❌ Error selecting game type: {e}")
        raise

# Refactored Skater Stat Leaders Functions

def scrape_stat_leaders(driver, wait, stat_title="Goals", column_index=8, label="goals", is_first=True, 
                        playerType="skater", count=None, gameType=None):
    
    if gameType == "Playoffs" and playerType == "goalie":
        column_index = column_index - 1

    #print("Clicking Stat Tab...")
    #click_stat_tab(driver, wait)


    print(f"Getting {playerType.title()}s...")
    click_player_section(driver, wait, playerType=playerType)

    #print(f"Selecting {gameType}...")
    #click_game_type(driver, wait, gameType=gameType)

    print(f"Waiting for table and clicking {stat_title} column...")

    wait.until(EC.presence_of_element_located((By.XPATH, "//*[@id='season-tabpanel']//table")))
    wait_for_spinner_to_disappear(wait)

    click_header = wait.until(EC.element_to_be_clickable((By.XPATH, f"//div[@title='{stat_title}']")))

    # Scroll into view
    scroll_origin = ScrollOrigin.from_element(click_header)
    ActionChains(driver)\
        .scroll_to_element(click_header)\
        .scroll_from_origin(scroll_origin, 0, 200)\
        .perform()
    time.sleep(0.5)

    click_times = 3 if is_first else 1

    if stat_title == "Goals Against Average":
        click_times = 2

    if stat_title == "Shutouts":
        click_times = 1
        
    for i in range(click_times):
        try:
            wait_for_spinner_to_disappear(wait)
            click_header = wait.until(EC.element_to_be_clickable((By.XPATH, f"//div[@title='{stat_title}']")))
            click_header.click()
            print(f"Clicking {stat_title} column... ({i+1}/{click_times})")
            time.sleep(0.5)
        except Exception as e:
            print(f"Click attempt {i+1} failed:", e)
            time.sleep(1)

    # Grab the top N rows
    rows = driver.find_elements(By.XPATH, "//*[@id='season-tabpanel']//table/tbody/tr")

    now = datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")

    leaders = []
    for i in range(min(count, len(rows))):
        name = rows[i].find_element(By.XPATH, "./td[2]/div/a").text
        stat_values = rows[i].find_element(By.XPATH, f"./td[{column_index}]").text
        leaders.append({"name": name, label: stat_values})
    
    return {
        "title": f"Top {count} {playerType.title()} - {stat_title} Leaders in the {gameType} (As of {now})",
        "leaders": leaders
    }