"""
Dev entrypoint — run from the project root:

    uvicorn app.main:app --reload

Or via this file directly:

    python main.py
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
