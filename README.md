# Krish Shah

Software Engineering, Florida Gulf Coast University (Minor: Mathematics) | Expected Spring 2027
Focus: Agentic AI, RAG systems, and AI applied to FinTech and civic data

[GitHub](https://github.com/krocks9903) · [LinkedIn](https://linkedin.com/in/krish-sshah)

---

## EagleGIS (Engage Estero / Village of Estero)

**Role:** Team Lead and AI Developer | Spring 2026 to present
**Links:** [Live app](https://frontend-react-pemczlmvf-krish-shahs-projects-8b25281c.vercel.app/) · [Repo](https://github.com/EagleGIS-FGCU/EagleGIS)

### What it is

A civic transparency platform for the Village of Estero, Florida. Public meeting records, agendas, budgets, and capital improvement plans live scattered across PDFs and web pages with no searchable index. EagleGIS pulls them into one place, maps them geographically, and puts a citation-backed AI assistant on top so residents can ask plain questions and get answers tied to the actual source document.

Started as a COP 3710 database systems project with community partner Engage Estero. It has since grown into an ongoing build used by the Village, with a valuation around $350K.

### What I built

- **Data pipeline (bronze → silver → gold).** Python pipeline that validates raw scraped CSVs against Pydantic schemas with foreign key checks, cleans OCR artifacts, enriches documents with canonical PDF links, and publishes a denormalized public CSV. Every run writes a manifest with row counts, SHA-256 hashes, and the git SHA so it is reproducible.
- **PDF extraction.** `extract_budget_pdf.py` parses Estero budget and Capital Improvement Plan documents into RAG-ready chunks, normalized financial CSVs, and structured tables for Postgres loading.
- **Coverage.** 2,604 agenda items spanning 2015 to 2026, with 601 mapped locations.
- **RAG architecture.** Router-first pipeline with SQL, RAG, and mixed query paths. pgvector plus tsvector hybrid retrieval, CRAG correction loops, and RAGAS-based evaluation. Two-layer retrieval across the Village corpus and a curated domain allowlist, with synthesis rules requiring a Village-sourced citation for any claim about Village action.
- **Per-claim traceability.** Every answer links back to the specific document and page. This is the core differentiator over asking a general-purpose chatbot.
- **Database design.** BCNF-normalized PostgreSQL schema on Supabase (projects, meetings, meeting_types, documents, locations) with a FastAPI read-API serving JSON and GeoJSON at `/api/v1`.
- **Geospatial layer.** ArcGIS Online map with clustering and Arcade popup expressions, plus a Leaflet dashboard built to WCAG AA with adjustable text size and 44px touch targets, since a large share of Estero residents are older.
- **Automation.** GitHub Actions for weekly rescrape and rebuild, monthly meeting discovery that opens a candidate PR for human review, nightly Supabase publish, and a drift check every 6 hours.

### Stack

Python, FastAPI, PostgreSQL, Supabase, pgvector, Pydantic, React, ArcGIS Online, Leaflet, GitHub Actions, pytest

### What I took away

Integrating a RAG system with real GIS data was the part I did not expect to be good at. The harder lesson was that the pipeline mattered more than the model. Most of the quality came from validation, cleaning, and making every claim traceable, not from prompt tuning.

---

## ORION: AI-Powered Mutual Fund Advisor (Infosys)

**Role:** AI/ML Developer Intern, Infosys Consulting | May to Aug 2025 (remote)
**Links:** [Repo](https://github.com/krocks9903/-GenAi-fund-advisor-Summer-Internship-2025)
**Note:** The Azure deployment has been taken down since the internship ended. The repo has the full source and docs.

### What it is

ORION (Optimal Risk-Investment Outreach Navigator) is a conversational mutual fund advisory system. It ingests fund prospectuses, performance reports, and risk analytics, then answers natural language questions about funds with quantitative backing and source citations.

### What I built

- **RAG pipeline** over 15+ major funds (VFIAX, VWELX, VBTLX, FMTIX and others) using LangChain, Azure OpenAI GPT-4, and text-embedding-ada-002.
- **Financial-aware document processing.** Custom chunking that preserves ticker symbols and financial terminology instead of splitting on them, with text cleaning tuned for PDF-extracted financial data.
- **FAISS vector store** for semantic retrieval across multi-format sources (PDF, JSON, structured fund data).
- **Risk analysis features.** Fund comparison, alpha/beta/Sharpe ratio evaluation, sector and geographic allocation breakdowns, and volatility ranking.
- **Citation system** so every recommendation points back to the source document.
- **Production concerns.** Embedding and document caching, batch processing, Azure rate limit handling with retry logic, structured logging, and environment-based secret management.
- **Streamlit front end** with a built-in feedback and analytics layer tracking query patterns and satisfaction.
- **Deployment** to Azure App Service via container registry.

### Stack

Python, LangChain, Azure OpenAI (GPT-4), FAISS, Streamlit, PyMuPDF, NLTK, Docker, Azure App Service

### What I took away

First time shipping an LLM app to production. Rate limits, caching, and error recovery ended up taking as much work as the RAG logic itself. Working in FinTech also made the citation requirement obvious early: nobody trusts an investment answer they cannot verify.

---

## Selected coursework and other work

- **Undergraduate Learning Assistant**, Statistics (2 sections), FGCU, Spring 2025
- **Service Learning Management System** for Harry Chapin Food Bank
- **Automated Selenium/TestNG test suite** (CEN 4072, Software Testing)
- **Lightning morphology research**

## Recognition

National Merit Scholar (2021) · FGCU Foundations Scholarship (2025) · Dean's List (Spring 2026)
