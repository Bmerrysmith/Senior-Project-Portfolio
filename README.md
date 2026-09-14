# Samuel Tusick
 
Software Engineering, Florida Gulf Coast University | Expected May 2027
Focus: Agentic AI, applied backend systems, and secure cloud architecture
 
[GitHub](https://github.com/samtusick) · [LinkedIn](https://linkedin.com/in/samuel-tusick) · [Portfolio](https://samtusick.github.io/Portfolio-Website/)
 
---
 
## FGCU Dendritic AI & Data Science Institute — Student Research Assistant
 
**Role:** Agentic AI Research Assistant | March 2025 to present
 
The codebases here are institutional and not public, but this is the core of my applied AI work and the context behind the projects below.
 
- Co-developing MAIVA, an AI Avatar Training Platform for mental health training scenarios, alongside a Master's thesis researcher. My role covers backend architecture (AWS API Gateway, Lambda, Aurora, Cognito, IAM), LLM-driven persona generation through the Anthropic API, and the React/Vite/Tailwind frontend, translating requirements gathered from two university colleges into the platform's data model.
- Helped coordinate and deliver the 2026 FGCU Summer AI Academy, serving 500+ participants across 150+ hours of instructional content.  
- Built and maintain 14+ AI tutoring tools using the OpenAI Custom GPT Builder, deployed across FGCU's Engineering Learning Hub to support tutoring, mentoring, and knowledge assistance workflows.
---
 
## RAG Email Agent
 
**Role:** Developer <br>
**Links:** [Link to Repo](https://github.com/SamTusick/Rag-Email-Agent)
 
### What it is
 
A multi-tenant RAG-based email agent and daily digest system connected to Outlook via the Microsoft Graph API. I built this to understand a full RAG pipeline end to end, so I deliberately avoided LangChain or any similar abstraction layer.
 
### What I built
 
- Ingestion pipeline that pulls emails through Microsoft Graph, chunks and embeds them, and stores vectors in a Postgres/pgvector store.
- Retrieval and summarization layer that grounds daily digest generation in semantically relevant prior email context, with an urgency-grading rubric for triage.
- Scheduled execution on AWS Lambda via EventBridge, with failure alerting.
- Microsoft OAuth with allowlist gating and Fernet-encrypted refresh tokens, with secrets managed through AWS Secrets Manager and narrowly scoped IAM policies.
### Stack
 
Python, Microsoft Graph API, PostgreSQL, pgvector, Supabase, AWS Lambda, EventBridge, AWS Secrets Manager, OpenAI (embeddings + GPT-4o Mini)
 
### What I took away
 
Building the retrieval and grounding logic myself, instead of through a framework, is what forced me to actually understand the tradeoffs in chunking, embedding, and context window management, rather than trusting a library's defaults.
 
---
 
## Router-Level Security Detection — Eagle CyberNest Lab
 
**Role:** Subteam Lead & Backend Developer | Feb 2025 to Apr 2025<br>
**Links:** [Link to Repo](https://github.com/nixguin/TrafficGuard-Upgraded)
 
### What it is
 
A home-network security research platform built with a 5-person team, focused on detecting and monitoring activity at the router level across multiple router platforms.
 
### What I built
 
- Led backend architecture decisions and task coordination for the subteam.
- Flask backend services with SSH-based data collection for real-time, centralized monitoring across three router platforms.
- SQLite-backed secure data storage for router telemetry.
- Tested and deployed production-ready router-communication scripts.
### Stack
 
Python, Flask, SSH, SQLite
 
### What I took away
 
This was the first project where I owned architecture decisions for a team instead of just contributing code, and where "production-ready" had to mean something concrete: tested, documented, and handed off cleanly to teammates who maintained it after I moved on.
 
------
 
## Switch4Good Database System
 
**Role:** Team Lead | January 2026 to May 2026<br>
**Links:** [Link to Repo](https://github.com/SamTusick/Switch4Good_DataBaseSystem)
 
### What it is
 
A PostgreSQL database and schema supporting a nonprofit's operations across participation tracking, projects, partnerships, and outcomes.
 
### What I built
 
- Led development of a normalized PostgreSQL schema modeling participation, projects, partnerships, and outcomes data.
- Designed the schema to support data-driven operations at scale: 100+ universities and 1,500+ students.
- Coordinated a team through requirements gathering and schema design decisions.
### Stack
 
PostgreSQL, SQL, Data Engineering
 
### What I took away
 
This was less about writing code and more about modeling ambiguity correctly the first time. A schema that has to serve a nonprofit's real reporting needs across multiple stakeholder groups punishes bad assumptions early, and there's no framework that fixes a bad data model after the fact.
 
---
 
## NHL Stat Scraper
 
**Role:** Developer<br>
**Links:** [Link to Repo](https://github.com/SamTusick/NHL-Web-Scraping)
 
### What it is
 
A full-stack analytics application for searching and comparing live stats across every NHL player.
 
### What I built
 
- Selenium-based Flask scraper covering 15+ stat categories across every player in the league, exposed through REST APIs.
- React/Vite frontend with dynamic, filterable stat views driven by query parameters.
- Deployed live on Render (backend) and Netlify (frontend).
### Stack
 
Python, Flask, Selenium, React, Vite, Render, Netlify
 
### What I took away
 
Scraping a live, frequently-updated external data source taught me more about handling flaky data and building resilient pipelines than any of my more controlled academic projects did.
