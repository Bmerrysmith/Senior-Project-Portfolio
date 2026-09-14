# Dev Notes — NHL Web Scraper

## Weekend Plan (June 1–2)

- [x] Review existing `userMenu.py` and `nhlScraper.py`
- [x] Add `headless` mode to Selenium
- [x] Clean up XPath selectors for stability
- [x] Create initial README.md with overview and instructions

---

## Weekly Plan (June 1–5)

### 🧱 Backend Prep

- [x] Refactor scraper into functions (goals, assists, points)
- [x] Set up Python virtual environment
- [x] Install and configure Flask
- [x] Create base Flask route to test connection
- [x] Build first API route: `/stats/goals`

## Weekly Plan (June 22-28)

- [x] Create routes for goalies
- [x] Create function to select game type (Regular Season / Playoffs)

---

### ⚛️ Frontend (Coming Soon)

- [x] Scaffold new React app
- [x] Create simple homepage with stat selection
- [x] Connect to Flask backend via fetch
- [x] Display JSON results in a table

---

## 📝 Notes to Self

- Keep frontend and backend loosely coupled
- Selenium can be slow — consider caching results later
- Use `print()` or logging to test API endpoints before integrating with React
- Keep `PATH` to ChromeDriver portable for easier deployment

---

## Color Palette

- Background: "#0B0B0B"
- Main Text: "#F0F0F0"
- Primary Accent: "#1F75FE"
- Secondary Accent: "#7FDBFF"

---

## 🐛 Issues to Watch

- NHL site layout may change and break XPath
- Long scraping time could cause API timeout
- Clicking elements may fail if not visible — use `WebDriverWait`

---

## 💡 Ideas for Later

- Add dropdown for selecting team or player stats
- Allow user to export results to `.csv`
- Allow users to select type(By Season, All-time), Season, Game Type(Playoffs)

---

## ⚙️ Tech Stack Plan

| Layer    | Tech                      | Purpose                |
| -------- | ------------------------- | ---------------------- |
| Frontend | React                     | User interface         |
| Backend  | Flask (Python)            | API to trigger scraper |
| Scraper  | Selenium                  | Scraping NHL.com stats |
| Storage  | (Optional) SQLite or JSON | Cache results          |

---

## 🔗 Reference Links

- [NHL Stats Page](https://www.nhl.com/stats/)
- [Selenium Docs](https://www.selenium.dev/documentation/)
- [Flask Docs](https://flask.palletsprojects.com/)

---

## Where to Continue

- Deploy backend with Render and frontend with Netlify
