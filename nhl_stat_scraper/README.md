#  NHL Web Scraper

A Python + React tool that scrapes real-time NHL data by category using Selenium. Built for quick access to different player stat leaders.

*Currently have the frontend running through Netlify, but working on a way to deploy the backend, that is cost effictive and enough memory in an instance to handle headless Chrome.*
*Backend is being deployed on Render, but the instance I'm currently running doesn't have enough memory for Selenium and headless Chrome*

[Link to Deployed Frontend](https://nhl-stat-scraper.netlify.app/)

##  Demo

[![Watch the demo](https://img.youtube.com/vi/1gMDVs8MUEQ/maxresdefault.jpg)](https://youtu.be/1gMDVs8MUEQ)

##  Usage

Once both servers are running, you can interact with the app via the frontend. It makes API calls to the Flask backend to fetch NHL stats. Progress checkpoints and scraping updates will appear in the backend terminal.

##  Prerequisites

- [Node.js](https://nodejs.org/) installed
- [Python 3.9+](https://www.python.org/) installed
- `pip` and `venv` available

##  Getting Started

You will need **two separate terminals** to run this program.

To run locally you will need to change the fetch url in NHL-Web-Scraping\frontend\nhl-stat-frontend\src\pages\ResultsPage.jsx on line 20 to

```bash

const url = `http://localhost:5000/stats/${playerType}/${statType}?count=${count}&gameType=${encodeURIComponent(gameType)}`;

```

### 1. Clone the Repository

```bash
git clone https://github.com/SamTusick/NHL-Web-Scraping.git
cd NHL-Web-Scraping
```
### 2. Set Up the Frontend (Terminal 1)

```bash
cd frontend/nhl-stat-frontend
npm install
npm run dev
```

### 3. Set Up the Backend (Terminal 2)

```bash
cd NHL-Web-Scraping
python -m venv .venv
source .venv/Scripts/activate   # On Windows
# or
source .venv/bin/activate       # On macOS/Linux

pip install -r requirements.txt
python app.py
```
