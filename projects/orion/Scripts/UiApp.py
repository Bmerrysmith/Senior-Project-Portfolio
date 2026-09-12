import os
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
import streamlit as st
from fpdf import FPDF

# --- Load env and initialize models ---
load_dotenv()
embedding = AzureOpenAIEmbeddings(
    model="text-embedding-ada-002",
    azure_endpoint=os.getenv("AZURE_API_BASE"),
    api_key=os.getenv("AZURE_API_KEY"),
    deployment=os.getenv("AZURE_EMBED_DEPLOYMENT"),
    api_version=os.getenv("AZURE_EMBED_VERSION"),
    chunk_size=1000,
)
vectorstore = FAISS.load_local(
    "faiss_index_fund_data",
    embedding,
    allow_dangerous_deserialization=True
)
retriever = vectorstore.as_retriever()
llm = AzureChatOpenAI(
    deployment_name=os.getenv("AZURE_CHAT_DEPLOYMENT"),
    model="gpt-4.1",
    azure_endpoint=os.getenv("AZURE_API_BASE"),
    api_key=os.getenv("AZURE_API_KEY"),
    api_version=os.getenv("AZURE_CHAT_VERSION"),
    temperature=0,
)

# --- PAGE STYLING ---
st.set_page_config(page_title="WealthAI", layout="wide", page_icon="💼")
st.markdown("""
    <style>
    body, .stApp { background: linear-gradient(135deg, #b3bcf5 0%, #d9c2fa 100%)!important; font-family: 'Inter', sans-serif; }
    .centered { display: flex; flex-direction: column; align-items: center; margin-bottom: 0.5rem;}
    .header-title { font-size: 2.7rem; font-weight: 800; color: #4533a9; margin: 0.5rem 0 0.2rem 0; }
    .header-subtitle { font-size: 1.12rem; color: #43496b; margin-bottom: 1.0rem;}
    .header-img { width: 105px; height: 105px; border-radius: 18px; object-fit:cover; margin-bottom: 1.2rem; box-shadow:0 4px 16px #b3a7e7aa;}
    .input-card {
        background: #f8fafc;
        border-radius: 22px;
        box-shadow: 0 2px 24px #b2a8ef44;
        padding: 1.5rem 1.6rem 0.7rem 1.6rem;
        margin: 1.2rem auto 1.2rem auto;
        max-width: 700px;
        border: 1.5px solid #e8e5fb;
    }
    .result-card {
        background: #fff;
        border-radius: 22px;
        padding: 2.1rem 2.2rem 1.3rem 2.2rem;
        box-shadow: 0 8px 34px #c7d2fe70;
        margin: 1.7rem auto;
        max-width: 900px;
        color: #22233c;
        border: 1.3px solid #ecebfb;
    }
    .sources-section {
        background: #f1f5f9;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        margin: 1rem 0 0.5rem 0;
        border: 1.2px solid #e7eafc;
        color: #555;
    }
    .stTextArea textarea {
        background: #fff !important;
        border-radius: 12px !important;
        color: #24273a !important;
        font-size: 1.12rem !important;
        min-height: 65px !important;
        border: 2.5px solid #e0e7ff !important;
        box-shadow: 0 2px 10px #ebe9fc44;
        padding: 1.1rem !important;
        transition: border-color 0.18s, box-shadow 0.18s;
    }
    .stTextArea textarea:focus {
        border-color: #8b5cf6 !important;
        box-shadow: 0 0 0 2px #c7d2fe99;
    }
    .stTextArea textarea::placeholder {
        color: #a3a3b3 !important;
        opacity: 1 !important;
        font-size: 1.03rem !important;
    }
    .action-row { display: flex; gap: 2rem; justify-content: center; margin-bottom: 1.6rem; margin-top: 0.1rem;}
    .action-btn {
        width: 200px;
        font-weight: 600;
        font-size: 1.09rem;
        border-radius: 14px;
        border: 2px solid #a78bfa;
        background: #fff;
        color: #4f46e5;
        padding: 1rem 0;
        margin: 0 0.2rem;
        transition: 0.15s;
    }
    .action-btn:hover {
        background: #a78bfa;
        color: #fff;
        border-color: #6d28d9;
        box-shadow: 0 8px 36px #c4b5fd5c;
        transform: scale(1.04);
    }
    .clear-btn {
        margin-top: 0.5rem !important;
        color: #fff !important;
        background: #d946ef !important;
        border-radius: 11px !important;
        border: none !important;
        font-weight: 600 !important;
        font-size: 1.01rem !important;
        padding: 0.6rem 1.1rem !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- HEADER ---
st.markdown(f"""
<div class="centered">
    <img class="header-img" src="wealthai_banner.png" alt="WealthAI Banner"/>
    <div class="header-title">WealthAI Fund Advisor</div>
    <div class="header-subtitle">Your intelligent companion for mutual fund analysis and investment decisions</div>
</div>
""", unsafe_allow_html=True)

# --- ACTION BUTTONS (as a row) ---
col1, col2, col3 = st.columns([1,1,1])
with col1:
    if st.button("Risk Analysis", key="btn1"):
        st.session_state.user_query = "What is Sharpe ratio and how is it calculated?"
        st.rerun()
with col2:
    if st.button("Fund Comparison", key="btn2"):
        st.session_state.user_query = "Compare VWELX vs VFIAX performance metrics"
        st.rerun()
with col3:
    if st.button("Smart Recommendations", key="btn3"):
        st.session_state.user_query = "Recommend a low-risk long-term investment fund"
        st.rerun()

# --- CLEAR BUTTON ---
if st.button("Clear Conversation", key="clear_btn"):
    for key in ("memory", "qa_chain", "user_query"):
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

# --- CHAT MEMORY AND QA CHAIN ---
custom_prompt = PromptTemplate.from_template("""
You are a financial assistant helping users with mutual fund questions.
You have access to:
- Definitions of terms (e.g., Sortino, Sharpe)
- Fund risk metrics (Sharpe, Sortino, Treynor, Std Dev)
- Fund metadata (inception date, AUM, expense ratio)
Before answering, use chain-of-thought reasoning:
STEP 1: Identify the question type:
  - Definition/info question? ("What is AUM?")
  - Fund comparison? ("Compare VWELX vs VFIAX")
  - Fund recommendation? ("Suggest a low-risk long-term fund")
STEP 2: Handle accordingly:
  - For definitions: Explain the term from context.
  - For comparisons: Compare metrics from context across funds.
  - For recommendations:
      a. Infer user profile (risk, time horizon, ESG, etc.)
      b. Filter based on context metrics (Sortino, Sharpe, Expense, etc.)
      c. Recommend and justify based on real data.
If context is missing, reply: "That information is not available in the provided context."
Context:
{context}
Question:
{question}
""")

if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        output_key="answer"
    )
if "qa_chain" not in st.session_state:
    st.session_state.qa_chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=st.session_state.memory,
        return_source_documents=True,
        combine_docs_chain_kwargs={"prompt": custom_prompt},
        output_key="answer"
    )

# --- CHAT HISTORY ---
if st.session_state.memory.chat_memory.messages:
    st.markdown('<div class="result-card">', unsafe_allow_html=True)
    for msg in st.session_state.memory.chat_memory.messages:
        if msg.type == "human":
            st.markdown(f'<div style="color:#7c3aed;"><b>You:</b> {msg.content}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div style="color:#262335;"><b>WealthAI:</b> {msg.content}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# --- INPUT CARD ---
st.markdown('<div class="input-card">', unsafe_allow_html=True)
query = st.text_area(
    "Ask Your Question",
    placeholder="Try: 'What is Sortino Ratio?' or 'Compare PRBLX and FSPTX performance'",
    height=80,
    key="user_query"
)
ask_button = st.button("Get Analysis")
st.markdown('</div>', unsafe_allow_html=True)

# --- PROCESS QUERY ---
if ask_button and query:
    with st.spinner("Analyzing your request..."):
        result = st.session_state.qa_chain.invoke({"question": query})
        answer = result.get("answer")
        source_docs = result.get("source_documents", [])
        sources = "\n".join(doc.metadata.get("source", "N/A") for doc in source_docs)
        st.markdown('<div class="result-card">', unsafe_allow_html=True)
        st.markdown(f"<b>Analysis Results</b><br><div style='margin-top: 1rem; line-height: 1.6;'>{answer}</div>", unsafe_allow_html=True)
        if sources.strip():
            st.markdown(f"<div class='sources-section'><b>Sources:</b><br>{sources}</div>", unsafe_allow_html=True)
        # PDF Export Button
        if st.button("Export as PDF"):
            class CustomPDF(FPDF):
                def header(self):
                    self.set_font("Arial", "B", 16)
                    self.cell(0, 10, "GenAI Fund Advisor - Analysis Report", ln=True, align="C")
                    self.ln(10)
                def footer(self):
                    self.set_y(-15)
                    self.set_font("Arial", "I", 8)
                    self.cell(0, 10, f"Page {self.page_no()}", align="C")
            pdf = CustomPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 10, f"Question:\n{query}\n\nAnalysis:\n{answer}\n")
            if sources:
                pdf.multi_cell(0, 10, f"Sources:\n{sources}")
            with open("fund_analysis_report.pdf", "wb") as f:
                pdf.output(f)
            with open("fund_analysis_report.pdf", "rb") as f:
                st.download_button("Download Report", f, file_name="fund_analysis_report.pdf", mime="application/pdf")
        st.markdown('</div>', unsafe_allow_html=True)

# --- FOOTER ---
st.markdown("""
<div style="text-align: center; margin-top: 2.5rem;">
    <p style="color: #6b7280; font-size: 0.92rem;">
        Powered by Azure OpenAI • Built with Streamlit • Your financial data is secure
    </p>
</div>
""", unsafe_allow_html=True)
