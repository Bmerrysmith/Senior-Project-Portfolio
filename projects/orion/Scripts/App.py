import os
import sys
import traceback
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

# Third-party imports with error handling
try:
    from dotenv import load_dotenv
    from langchain_community.vectorstores import FAISS
    from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI
    from langchain.chains import ConversationalRetrievalChain
    from langchain.memory import ConversationBufferMemory
    from langchain.prompts import PromptTemplate
    import streamlit as st
    from fpdf import FPDF
except ImportError as e:
    print(f"Missing required package: {e}")
    print("Please install required packages with: pip install -r requirements.txt")
    sys.exit(1)

# --- Configure logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('orion_app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Load environment variables ---
try:
    load_dotenv()
    logger.info("Environment variables loaded successfully")
except Exception as e:
    logger.error(f"Failed to load environment variables: {e}")
    st.error("Failed to load environment configuration. Please check your .env file.")

# --- Streamlit page config ---
st.set_page_config(
    page_title="ORION: AI-Powered Mutual Fund Advisor",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="💼"
)

# --- Session state initialization with error handling ---
def initialize_session_state():
    """Initialize session state variables with proper defaults"""
    defaults = {
        "documents": set(),
        "active_page": "💬 Chat",
        "feedback_log": [],
        "conversation_history": [],
        "last_query": "",
        "error_log": [],
        "initialized": False,
        "clear_input": False,  # Flag to handle input clearing
        "input_key": 0  # Counter for input widget keys
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

# --- Environment validation ---
def validate_environment() -> bool:
    """Validate that all required environment variables are present"""
    required_vars = [
        "AZURE_API_BASE",
        "AZURE_API_KEY", 
        "AZURE_EMBED_DEPLOYMENT",
        "AZURE_EMBED_VERSION",
        "AZURE_CHAT_DEPLOYMENT",
        "AZURE_CHAT_VERSION"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        st.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error(f"Missing environment variables: {missing_vars}")
        return False
    
    return True

# --- Initialize components with error handling ---
@st.cache_resource
def initialize_embeddings():
    """Initialize Azure OpenAI embeddings with caching and error handling"""
    try:
        embedding = AzureOpenAIEmbeddings(
            model="text-embedding-ada-002",
            azure_endpoint=os.getenv("AZURE_API_BASE"),
            api_key=os.getenv("AZURE_API_KEY"),
            deployment=os.getenv("AZURE_EMBED_DEPLOYMENT"),
            api_version=os.getenv("AZURE_EMBED_VERSION"),
            chunk_size=1000,
        )
        logger.info("Embeddings initialized successfully")
        return embedding
    except Exception as e:
        logger.error(f"Failed to initialize embeddings: {e}")
        st.error(f"Failed to initialize embeddings: {str(e)}")
        return None

@st.cache_resource
def initialize_vectorstore():
    """Initialize FAISS vectorstore with error handling"""
    try:
        embedding = initialize_embeddings()
        if embedding is None:
            return None
            
        if not os.path.exists("faiss_index_fund_data"):
            st.error("FAISS index directory not found. Please ensure the index is properly created.")
            logger.error("FAISS index directory not found")
            return None
            
        vectorstore = FAISS.load_local(
            "faiss_index_fund_data",
            embedding,
            allow_dangerous_deserialization=True
        )
        logger.info("Vectorstore loaded successfully")
        return vectorstore
    except Exception as e:
        logger.error(f"Failed to load vectorstore: {e}")
        st.error(f"Failed to load vectorstore: {str(e)}")
        return None

@st.cache_resource
def initialize_llm():
    """Initialize Azure OpenAI chat model with error handling"""
    try:
        llm = AzureChatOpenAI(
            deployment_name=os.getenv("AZURE_CHAT_DEPLOYMENT"),
            model="gpt-4",
            azure_endpoint=os.getenv("AZURE_API_BASE"),
            api_key=os.getenv("AZURE_API_KEY"),
            api_version=os.getenv("AZURE_CHAT_VERSION"),
            temperature=0,
            max_tokens=2500,
            timeout=30,
        )
        logger.info("LLM initialized successfully")
        return llm
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {e}")
        st.error(f"Failed to initialize language model: {str(e)}")
        return None

# --- IMPROVED prompt template with concise answer and detailed analysis ---
def get_custom_prompt():
    """Enhanced prompt template with concise answer paragraph and detailed analysis sections"""
    return PromptTemplate(
        input_variables=["context", "question"],
        template="""You are an expert mutual fund assistant. Provide comprehensive, detailed analysis using ALL available data.

SEARCH ALL CONTEXT thoroughly including JSON files with complete risk metrics, fund metadata, and PDF documents.

RESPONSE FORMAT:

Answer: 
[Provide a single, concise paragraph (3-4 sentences max) that directly answers the user's question with the most important information. Include specific fund names and key numbers but keep it brief and focused.]

Detailed Analysis:

**Fund Rankings & Metrics:**
When presenting fund data, use clean tables and include source citations. Format fund information like this:

| Fund | Category | Assets | Yield | Key Details | Source |
|------|----------|---------|-------|-------------|---------|
| VFIAX | Large Blend | $770.8B | 1.3% | 100% U.S. large- and mid-cap stocks | [Source: fund_summary.json] |
| VWELX | Moderate Allocation | $110.9B | 2.1% | U.S. stocks and bonds, some foreign securities | [Source: prospectus_data.pdf] |

**Risk Assessment:** [Source: risk_metrics.json]
[Analyze volatility, risk-adjusted returns, and downside protection with specific metric interpretations and source citations]

**Investment Implications:** [Source: Multiple documents]
[Explain what these metrics mean for investors, suitable investor profiles, and practical considerations with citations]

**Additional Considerations:** [Source: fund_metadata.json, performance_data.csv]
[Include expense ratios, fund strategies, historical performance context, and any caveats with source references]

IMPORTANT GUIDELINES:
- Keep the Answer section to ONE concise paragraph (3-4 sentences maximum)
- The Answer should directly address the user's question with key facts and numbers
- Use specific numbers with units (e.g., "Standard Deviation of 5.05%" not just "5.05")
- Add [Source: filename] citations after each major section in Detailed Analysis
- Format fund comparisons in clean tables with source column
- Explain what metrics mean in practical terms
- Compare funds directly with quantitative differences
- Include context about fund strategies and characteristics
- Use detailed analysis in each section with proper citations
- Always search ALL available context before claiming data is missing
- Present data in organized, scannable format with proper table formatting and source attribution

Context: {context}
Question: {question}

Answer:"""
    )

# --- Modified answer processing function for concise answers ---
def format_answer_paragraph(answer_text):
    """Format answer as a single concise paragraph"""
    if not answer_text:
        return answer_text
    
    # Clean up the answer text
    answer_text = answer_text.strip()
    
    # If it already looks like a paragraph, return as is
    if not ('•' in answer_text or answer_text.startswith('-') or '<li>' in answer_text):
        return answer_text
    
    # Convert bullet points back to paragraph format
    if '•' in answer_text:
        # Remove bullet points and join sentences
        sentences = [s.strip().lstrip('•').strip() for s in answer_text.split('\n') if s.strip() and not s.strip().startswith('•')]
        # Join with proper spacing and periods
        cleaned_sentences = []
        for sentence in sentences:
            if sentence and len(sentence) > 5:  # Avoid very short fragments
                if not sentence.endswith(('.', '!', '?')):
                    sentence += '.'
                cleaned_sentences.append(sentence)
        
        # Join into a single paragraph, limiting to first 3-4 sentences for conciseness
        return ' '.join(cleaned_sentences[:4])
    
    return answer_text

# --- Enhanced citation processing function (unchanged) ---
def add_citations_to_analysis(analysis_text, source_docs):
    """Add citations to the detailed analysis sections"""
    if not analysis_text or not source_docs:
        return analysis_text
    
    # Extract unique sources
    sources = {}
    for i, doc in enumerate(source_docs):
        source = doc.metadata.get("source", f"Document_{i+1}")
        filename = source.split('/')[-1] if '/' in source else source
        sources[filename] = source
    
    # Define section headers that should get citations
    section_headers = [
        "**Fund Rankings & Metrics:**",
        "**Risk Assessment:**",
        "**Investment Implications:**",
        "**Additional Considerations:**",
        "Fund Rankings & Metrics:",
        "Risk Assessment:",
        "Investment Implications:",
        "Additional Considerations:"
    ]
    
    # Add citations to section headers
    modified_text = analysis_text
    for header in section_headers:
        if header in modified_text:
            # Add citation after the header
            citation_html = f' <span class="citation">[Source: Multiple documents]</span>'
            modified_text = modified_text.replace(header, header + citation_html)
    
    return modified_text

# --- Enhanced CSS with smaller answer box ---
def load_custom_css():
    """Load enhanced custom CSS with smaller answer container"""
    st.markdown("""
    <style>
    /* Import modern fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Main app styling - Light blue background */
    .stApp {
        background: #f0f8ff !important;
        color: #2c3e50;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    /* ENHANCED FEEDBACK MESSAGE STYLING - FIXED VISIBILITY */
    /* Success message styling - Bright green with white text */
    .stAlert[data-baseweb="notification"] div[data-testid="stNotificationContentSuccess"] {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
        color: #ffffff !important;
        border: 2px solid #047857 !important;
        border-radius: 12px !important;
        padding: 1rem 1.5rem !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3) !important;
        margin: 1rem 0 !important;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1) !important;
    }
    
    /* Success message icon */
    .stAlert[data-baseweb="notification"] div[data-testid="stNotificationContentSuccess"] > div:first-child {
        color: #ffffff !important;
        font-size: 1.2rem !important;
        font-weight: bold !important;
    }
    
    /* Warning message styling - Orange with white text */
    .stAlert[data-baseweb="notification"] div[data-testid="stNotificationContentWarning"] {
        background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%) !important;
        color: #ffffff !important;
        border: 2px solid #b45309 !important;
        border-radius: 12px !important;
        padding: 1rem 1.5rem !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3) !important;
        margin: 1rem 0 !important;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1) !important;
    }
    
    /* Warning message icon */
    .stAlert[data-baseweb="notification"] div[data-testid="stNotificationContentWarning"] > div:first-child {
        color: #ffffff !important;
        font-size: 1.2rem !important;
        font-weight: bold !important;
    }
    
    /* Error message styling - Red with white text */
    .stAlert[data-baseweb="notification"] div[data-testid="stNotificationContentError"] {
        background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%) !important;
        color: #ffffff !important;
        border: 2px solid #b91c1c !important;
        border-radius: 12px !important;
        padding: 1rem 1.5rem !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3) !important;
        margin: 1rem 0 !important;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1) !important;
    }
    
    /* Error message icon */
    .stAlert[data-baseweb="notification"] div[data-testid="stNotificationContentError"] > div:first-child {
        color: #ffffff !important;
        font-size: 1.2rem !important;
        font-weight: bold !important;
    }
    
    /* Info message styling - Blue with white text */
    .stAlert[data-baseweb="notification"] div[data-testid="stNotificationContentInfo"] {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
        color: #ffffff !important;
        border: 2px solid #1d4ed8 !important;
        border-radius: 12px !important;
        padding: 1rem 1.5rem !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3) !important;
        margin: 1rem 0 !important;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1) !important;
    }
    
    /* Info message icon */
    .stAlert[data-baseweb="notification"] div[data-testid="stNotificationContentInfo"] > div:first-child {
        color: #ffffff !important;
        font-size: 1.2rem !important;
        font-weight: bold !important;
    }
    
    /* Custom feedback message styling */
    .custom-feedback-success {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
        color: #ffffff !important;
        border: 2px solid #047857 !important;
        border-radius: 12px !important;
        padding: 1rem 1.5rem !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3) !important;
        margin: 1rem auto !important;
        text-align: center !important;
        max-width: 500px !important;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1) !important;
        animation: slideInFade 0.5s ease-out !important;
    }
    
    .custom-feedback-warning {
        background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%) !important;
        color: #ffffff !important;
        border: 2px solid #b45309 !important;
        border-radius: 12px !important;
        padding: 1rem 1.5rem !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3) !important;
        margin: 1rem auto !important;
        text-align: center !important;
        max-width: 500px !important;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1) !important;
        animation: slideInFade 0.5s ease-out !important;
    }
    
    /* Animation for feedback messages */
    @keyframes slideInFade {
        0% {
            opacity: 0;
            transform: translateY(-10px);
        }
        100% {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    /* Ensure all alert text is visible */
    .stAlert * {
        color: inherit !important;
    }
    
    /* Override any conflicting styles */
    div[data-testid="stAlert"] {
        background: inherit !important;
        color: inherit !important;
    }
    
    /* ENHANCED SIDEBAR - DEEP BLUE PRIMARY COLORS */
    .stSidebar {
        background: linear-gradient(180deg, #003366 0%, #001144 100%) !important;
        border-right: 2px solid #004080 !important;
    }
    
    .stSidebar > div {
        background: transparent !important;
        padding-top: 1rem !important;
    }
    
    /* SIDEBAR NAVIGATION - WHITE TEXT WITH DEEP BLUE THEME */
    .stSidebar .stRadio > div {
        background: transparent !important;
        gap: 0.5rem !important;
        padding: 0 0.5rem !important;
    }
    
    .stSidebar .stRadio > div > label {
        background: rgba(255, 255, 255, 0.08) !important;
        color: #ffffff !important;  /* PURE WHITE TEXT */
        padding: 1.2rem 1.5rem !important;
        border-radius: 12px !important;
        margin-bottom: 0.75rem !important;
        transition: all 0.3s ease !important;
        border: 2px solid rgba(255, 255, 255, 0.1) !important;
        cursor: pointer !important;
        font-weight: 500 !important;
        font-size: 1rem !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        width: 100% !important;
        min-height: 65px !important;
        text-align: left !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2) !important;
        backdrop-filter: blur(10px) !important;
    }
    
    .stSidebar .stRadio > div > label:hover {
        background: rgba(255, 255, 255, 0.15) !important;
        color: #ffffff !important;  /* PURE WHITE TEXT ON HOVER */
        border-color: rgba(255, 255, 255, 0.3) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3) !important;
    }
    
    .stSidebar .stRadio > div > label[data-checked="true"] {
        background: rgba(255, 255, 255, 0.2) !important;
        color: #ffffff !important;  /* PURE WHITE TEXT WHEN SELECTED */
        border-color: rgba(255, 255, 255, 0.4) !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25) !important;
        transform: scale(1.02) !important;
    }
    
    /* Remove radio button circles */
    .stSidebar .stRadio > div > label > div:first-child {
        display: none !important;
    }
    
    /* SIDEBAR TEXT CONTENT - ENSURE WHITE COLOR */
    .stSidebar .stRadio > div > label > div:last-child {
        pointer-events: none !important;
        width: 100% !important;
        text-align: left !important;
        font-size: 1rem !important;
        font-weight: inherit !important;
        color: #ffffff !important;  /* FORCE WHITE TEXT */
    }
    
    /* Override any text color inheritance */
    .stSidebar .stRadio > div > label * {
        color: #ffffff !important;  /* FORCE ALL TEXT TO BE WHITE */
    }
    
    .stSidebar .stRadio > div > label {
        pointer-events: auto !important;
        user-select: none !important;
    }
    
    /* SIDEBAR TITLE - WHITE TEXT */
    .sidebar-title {
        color: #ffffff !important;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        margin-bottom: 1.5rem !important;
        padding: 1rem !important;
        text-align: center !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.2) !important;
    }
    
    .sidebar-logo {
        padding: 1rem 0 1rem 0 !important;
        text-align: center !important;
        filter: brightness(1.2) !important;
    }
    
    /* ADDITIONAL SIDEBAR TEXT OVERRIDES */
    .stSidebar p, .stSidebar span, .stSidebar div {
        color: #ffffff !important;
    }
    
    /* Force white text on all sidebar elements */
    .stSidebar * {
        color: #ffffff !important;
    }
    
    /* Main header - ORION animated title */
    .main-header {
        text-align: center;
        margin: 1.5rem 0 2rem 0;
        letter-spacing: -0.5px;
        line-height: 1.2;
        overflow: hidden;
    }
    
    .orion-title {
        color: #1a1d29;
        font-size: 3.5rem;
        font-weight: 900;
        margin: 0;
        letter-spacing: -1px;
        white-space: nowrap;
        overflow: hidden;
        display: inline-block;
        background: linear-gradient(45deg, #1a1d29, #004578, #0078D4);
        background-size: 300% 300%;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        animation: slideInFromLeft 1.2s ease-out, gradientShift 3s ease-in-out infinite;
    }
    
    @keyframes slideInFromLeft {
        0% {
            transform: translateX(-100%);
            opacity: 0;
        }
        100% {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes gradientShift {
        0%, 100% {
            background-position: 0% 50%;
        }
        50% {
            background-position: 100% 50%;
        }
    }
    
    .orion-subtitle {
        color: #6b7280;
        font-size: 1.1rem;
        font-weight: 400;
        margin: 0.5rem 0 0 0;
        letter-spacing: 0.5px;
        animation: fadeInUp 1.5s ease-out 0.3s both;
    }
    
    @keyframes fadeInUp {
        0% {
            transform: translateY(20px);
            opacity: 0;
        }
        100% {
            transform: translateY(0);
            opacity: 1;
        }
    }
    
    /* Example hint */
    .example-hint {
        font-size: 0.85rem;
        color: #6b7280;
        margin-bottom: 1.5rem;
        text-align: center;
        background: transparent !important;
        padding: 0.5rem 1rem;
        font-weight: 400;
        max-width: 768px;
        margin-left: auto;
        margin-right: auto;
        font-style: italic;
    }
    
    .example-hint::before {
        content: "💡";
        margin-right: 0.5rem;
        font-style: normal;
    }
    
    /* ENHANCED INPUT STYLING - LARGER TEXT BOX */
    .stTextInput > div > div > input {
        background: #ffffff !important;
        border: 2px solid #e2e8f0 !important;
        border-radius: 16px !important;
        padding: 20px 24px !important;
        font-size: 17px !important;
        color: #1a1d29 !important;
        transition: all 0.3s ease !important;
        min-height: 68px !important;
        height: 68px !important;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.08) !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 400 !important;
        width: 100% !important;
        outline: none !important;
        line-height: 1.4 !important;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #0078D4 !important;
        box-shadow: 0 0 0 4px rgba(0, 120, 212, 0.15) !important;
        transform: translateY(-1px) !important;
    }
    
    .stTextInput > div > div > input::placeholder {
        color: #9ca3af !important;
        font-size: 16px !important;
        font-weight: 400 !important;
    }
    
    /* Input container adjustments */
    .stTextInput > div {
        height: auto !important;
    }
    
    .stTextInput > div > div {
        height: auto !important;
    }
    
    /* Input row */
    .input-row {
        display: flex !important;
        gap: 10px !important;
        align-items: flex-end !important;
        width: 100% !important;
        max-width: 768px !important;
        margin: 0 auto !important;
    }
    
    /* BUTTON STYLING - Submit Blue, Clear Orange */
    .stButton button, 
    .stButton > button {
        background: #0078D4 !important;
        color: white !important;
        border: none !important;
        border-radius: 16px !important;
        font-weight: 600 !important;
        height: 68px !important;
        min-height: 68px !important;
        box-shadow: 0 4px 8px rgba(0, 120, 212, 0.25) !important;
        transition: all 0.3s ease !important;
        font-size: 16px !important;
        padding: 0 24px !important;
        min-width: 120px !important;
        font-family: 'Inter', sans-serif !important;
        cursor: pointer !important;
    }
    
    .stButton button:hover,
    .stButton > button:hover {
        background: #106EBE !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 16px rgba(0, 120, 212, 0.4) !important;
    }
    
    /* FIXED: Clear button orange styling - More specific targeting */
    button[kind="secondary"] {
        background: #f97316 !important;
        color: white !important;
        box-shadow: 0 4px 8px rgba(249, 115, 22, 0.25) !important;
    }
    
    button[kind="secondary"]:hover {
        background: #ea580c !important;
        box-shadow: 0 6px 16px rgba(249, 115, 22, 0.4) !important;
    }
    
    /* Alternative targeting for clear button */
    .stButton:has(button:contains("Clear")) button,
    button:contains("Clear") {
        background: #f97316 !important;
        color: white !important;
        box-shadow: 0 4px 8px rgba(249, 115, 22, 0.25) !important;
    }
    
    .stButton:has(button:contains("Clear")) button:hover,
    button:contains("Clear"):hover {
        background: #ea580c !important;
        box-shadow: 0 6px 16px rgba(249, 115, 22, 0.4) !important;
    }
    
    /* REMOVED: Response container - No more white box around output */
    .response-container {
        background: transparent !important;
        padding: 0 !important;
        border-radius: 0 !important;
        box-shadow: none !important;
        margin: 1.5rem auto !important;
        border: none !important;
        max-width: 768px !important;
    }
    
    .response-header {
        display: flex;
        align-items: center;
        margin-bottom: 1rem;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid #e2e8f0;
        background: #ffffff;
        padding: 1rem 1.5rem 0.75rem 1.5rem;
        border-radius: 12px 12px 0 0;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }
    
    .response-icon {
        background: #0078D4;
        color: white;
        width: 32px;
        height: 32px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-right: 0.75rem;
        font-size: 1rem;
        font-weight: 600;
    }
    
    .response-title {
        color: #1a1d29;
        font-size: 1.1rem;
        font-weight: 600;
        margin: 0;
    }
    
    /* MODIFIED: Smaller, more concise answer styling */
    .custom-answer {
        background: #f8fafc;
        padding: 1rem 1.25rem;
        border-left: 3px solid #0078D4;
        margin: 1rem 0;
        border-radius: 8px;
        font-weight: 400;
        position: relative;
        line-height: 1.6;
        font-size: 0.95rem;
        max-height: none;
        overflow: visible;
    }
    
    .custom-answer::before {
        content: "Answer:";
        position: absolute;
        top: -12px;
        left: 12px;
        background: #0078D4;
        color: white;
        padding: 4px 12px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    
    /* Detailed explanation styling - unchanged */
    .custom-explanation {
        background: #ffffff;
        padding: 1rem;
        border: 1px solid #e2e8f0;
        border-left: 3px solid #10b981;
        margin: 1rem 0;
        border-radius: 8px;
        position: relative;
    }
    
    .custom-explanation::before {
        content: "Detailed Analysis:";
        position: absolute;
        top: -12px;
        left: 12px;
        background: #10b981;
        color: white;
        padding: 4px 12px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    
    /* Citation styling */
    .citation {
        display: inline-block !important;
        background: #f0f9ff !important;
        color: #0369a1 !important;
        padding: 2px 8px !important;
        border-radius: 4px !important;
        font-size: 0.8rem !important;
        font-weight: 500 !important;
        margin-left: 0.25rem !important;
        border: 1px solid #bae6fd !important;
    }
    
    /* Table styling */
    .custom-explanation table {
        width: 100%;
        border-collapse: collapse;
        margin: 1rem 0;
        font-size: 0.9rem;
        background: #ffffff;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        border-radius: 8px;
        overflow: hidden;
    }
    
    .custom-explanation table th {
        background: #f8fafc;
        color: #374151;
        font-weight: 600;
        padding: 12px 8px;
        text-align: left;
        border-bottom: 2px solid #e5e7eb;
        font-size: 0.8rem;
    }
    
    .custom-explanation table td {
        padding: 10px 8px;
        border-bottom: 1px solid #f3f4f6;
        color: #1f2937;
        font-size: 0.85rem;
    }
    
    /* Feedback buttons */
    .feedback-container {
        display: flex;
        gap: 0.5rem;
        margin-top: 1rem;
        justify-content: center;
        padding-top: 1rem;
        border-top: 1px solid #f1f5f9;
    }
    
    .feedback-container .stButton > button {
        background: #f8fafc !important;
        color: #64748b !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 8px !important;
        padding: 6px 12px !important;
        font-weight: 500 !important;
        font-size: 13px !important;
        height: 32px !important;
    }
    
    /* Footer */
    .footer {
        text-align: center;
        padding: 2rem;
        color: #6b7280;
        font-size: 0.85rem;
        max-width: 768px;
        margin: 3rem auto 0 auto;
    }
    
    /* Metrics cards */
    .metrics-card {
        background: #ffffff;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        margin: 1rem 0;
        border: 1px solid #e2e8f0;
    }
    
    /* Hide Streamlit elements */
    .stTextInput > label {
        display: none !important;
    }
    
    .stAppHeader {
        display: none !important;
    }
    
    #MainMenu {
        display: none !important;
    }
    
    footer {
        display: none !important;
    }
    
    .stDeployButton {
        display: none !important;
    }
    
    .stToolbar {
        display: none !important;
    }
    
    /* Main container */
    .block-container {
        max-width: 800px !important;
        padding: 1rem !important;
        margin: 0 auto !important;
    }
    
    /* Mobile responsive */
    @media (max-width: 768px) {
        .orion-title {
            font-size: 2rem;
        }
        
        .input-row {
            flex-direction: column;
            gap: 10px;
        }
        
        .block-container {
            padding: 0.5rem !important;
        }
        
        .stTextInput > div > div > input {
            min-height: 60px !important;
            height: 60px !important;
            padding: 18px 20px !important;
            font-size: 16px !important;
        }
        
        .stButton button, 
        .stButton > button {
            height: 60px !important;
            min-height: 60px !important;
            font-size: 15px !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)

def process_query(query: str, qa_chain) -> Dict[str, Any]:
    """Process user query with enhanced formatting for concise answers and detailed analysis"""
    try:
        if not query or not query.strip():
            return {"error": "Please enter a valid query"}
        
        # Add query to history
        st.session_state.conversation_history.append({
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "type": "user"
        })

        with st.spinner("Analyzing your query..."):
            result = qa_chain.invoke({"question": query})
        
        answer = result.get("answer", "")
        source_docs = result.get("source_documents", [])

        # If no documents were used, fallback to LLM only
        if not source_docs:
            fallback_prompt = f"""You are a mutual fund expert assistant. The user asked:

{query}

Provide a helpful answer in this format:

Answer: 
[Provide a single, concise paragraph (3-4 sentences max) that directly answers the user's question with the most important information.]

If you're unsure about specific details, say so."""
            
            llm = st.session_state.qa_chain.llm
            fallback_response = llm.invoke(fallback_prompt)
            answer = f"**Note:** This answer is based on general knowledge, as no supporting documents were found.\n\n{fallback_response}"
        
        # Save answer to history
        st.session_state.conversation_history.append({
            "timestamp": datetime.now().isoformat(),
            "response": answer,
            "type": "assistant",
            "source_count": len(source_docs)
        })

        return {
            "answer": answer,
            "source_docs": source_docs,
            "success": True
        }

    except Exception as e:
        error_msg = f"Error processing query: {str(e)}"
        logger.error(f"Query processing error: {e}")
        st.session_state.error_log.append({
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "query": query
        })
        return {"error": error_msg}

# --- Enhanced feedback handling with better visibility ---
def handle_feedback(query: str, feedback_type: str):
    """Handle user feedback with enhanced visibility and logging"""
    feedback_entry = {
        "timestamp": datetime.now().isoformat(),
        "question": query,
        "feedback": feedback_type,
        "session_id": st.session_state.get("session_id", "unknown")
    }
    
    st.session_state.feedback_log.append(feedback_entry)
    logger.info(f"Feedback received: {feedback_type} for query: {query[:50]}...")
    
    # Show enhanced feedback messages with better visibility
    if feedback_type == "positive":
        st.success("✅ Thank you for your positive feedback! We're glad we could help.")
    else:
        st.warning("⚠️ Thank you for your feedback. We'll work on improving this response.")

# --- Alternative custom feedback display function ---
def display_feedback_message(message_type: str, message_text: str):
    """Display feedback message with enhanced visibility using custom HTML"""
    if message_type == "success":
        st.markdown(f"""
        <div class="custom-feedback-success">
            {message_text}
        </div>
        """, unsafe_allow_html=True)
    
    elif message_type == "warning":
        st.markdown(f"""
        <div class="custom-feedback-warning">
            {message_text}
        </div>
        """, unsafe_allow_html=True)

# --- Initialize everything ---
def initialize_app():
    """Initialize the application with comprehensive error handling"""
    try:
        # Initialize session state
        initialize_session_state()
        
        # Validate environment
        if not validate_environment():
            st.stop()
        
        # Initialize components
        vectorstore = initialize_vectorstore()
        llm = initialize_llm()
        
        if vectorstore is None or llm is None:
            st.error("Failed to initialize core components. Please check your configuration.")
            st.stop()
        
        # Initialize memory and chain
        if "memory" not in st.session_state:
            st.session_state.memory = ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True,
                output_key="answer"
            )
        
        if "qa_chain" not in st.session_state:
            retriever = vectorstore.as_retriever(
                search_kwargs={"k": 15}  # Increased to get more context
            )
            st.session_state.qa_chain = ConversationalRetrievalChain.from_llm(
                llm=llm,
                retriever=retriever,
                memory=st.session_state.memory,
                return_source_documents=True,
                combine_docs_chain_kwargs={"prompt": get_custom_prompt()},  # Using improved prompt
                output_key="answer"
            )
        
        st.session_state.initialized = True
        logger.info("Application initialized successfully")
        
    except Exception as e:
        logger.error(f"Application initialization failed: {e}")
        st.error(f"Application initialization failed: {str(e)}")
        st.stop()

# --- Main application ---
def main():
    """Main application function"""
    try:
        # Load custom CSS
        load_custom_css()
        
        # Initialize the app
        initialize_app()
        
        # Enhanced Sidebar
        with st.sidebar:
            # Logo section
            logo_path = "Scripts/infosys_logo.png"
            if os.path.exists(logo_path):
                st.markdown('<div class="sidebar-logo">', unsafe_allow_html=True)
                st.image(logo_path, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
            
            # Clean title
            st.markdown(
                '<div class="sidebar-title"> </div>',
                unsafe_allow_html=True,
            )
            
            # Enhanced navigation with better styling
            sidebar_options = [
                "💬 Chat",
                "📊 Analytics", 
                "⚙️ Settings"
            ]
            
            # Get current page for proper selection
            current_page = st.session_state.get("active_page", "💬 Chat")
            if current_page == "💬 GenAI Fund Page":
                current_page = "💬 Chat"
            
            try:
                current_index = sidebar_options.index(current_page)
            except ValueError:
                current_index = 0  # Default to Chat if not found
            
            selected = st.radio(
                "Navigation",
                sidebar_options,
                index=current_index,
                label_visibility="collapsed",
                key="sidebar_navigation"
            )
            
            # Update session state with selected page
            st.session_state["active_page"] = selected
        
        # Main content area
        if st.session_state["active_page"] == "💬 Chat":
            render_chat_page()
        elif st.session_state["active_page"] == "📊 Analytics":
            render_analytics_page()
        elif st.session_state["active_page"] == "⚙️ Settings":
            render_settings_page()
        else:
            st.info("This page is under development.")
        
        # Footer
        st.markdown("""
        <div class='footer'>
        | © 2025 Infosys GenAI Fund Advisor | Powered by Azure OpenAI and LangChain | 
        </div>
        """, unsafe_allow_html=True)
        
    except Exception as e:
        logger.error(f"Main application error: {e}")
        st.error(f"An unexpected error occurred: {str(e)}")
        st.error("Please refresh the page or contact support if the issue persists.")

def render_chat_page():
    """Render the main chat interface with concise answers and detailed analysis"""
    # Updated header with the new title
    st.markdown("""
    <div class='main-header'>
        <h1 class='orion-title'>ORION: AI-Powered Mutual Fund Advisor</h1>
        <p class='orion-subtitle'>Optimal Risk-Investment Outreach Navigator</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Clean input section - NO CONTAINER BOX
    # Example hint - now looks like simple text, not an input box
    st.markdown("<div class='example-hint'>Try: \"Compare VFIAX and VWELX risk metrics\", \"What is VBIAX alpha?\", \"Show me VBTLX performance data\"</div>", 
               unsafe_allow_html=True)
    
    # Handle clear flag - clear input before creating new widget
    if st.session_state.get("clear_input", False):
        st.session_state.clear_input = False
        st.session_state.input_key += 1  # Change key to force widget recreation
    
    # Input row with text input and buttons
    st.markdown('<div class="input-row">', unsafe_allow_html=True)
    col_input, col_submit, col_clear = st.columns([6.5, 1.5, 1.5])
    
    with col_input:
        # Use dynamic key to allow input clearing
        input_key = f"chat_input_{st.session_state.input_key}"
        query = st.text_input(
            "Search", 
            placeholder="Ask about fund performance, risks, or comparisons...", 
            key=input_key, 
            label_visibility="collapsed"
        )
    
    with col_submit:
        submit_clicked = st.button("Submit", key="submit_btn", use_container_width=True, help="Submit your query")
    
    with col_clear:
        clear_clicked = st.button("Clear", key="clear_btn", use_container_width=True, help="Clear conversation history", type="secondary")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Handle clear button - FIXED to avoid session state modification error
    if clear_clicked:
        # Clear conversation state more thoroughly
        keys_to_clear = ["memory", "qa_chain", "conversation_history", "last_query"]
        for key in keys_to_clear:
            if key in st.session_state:
                if key == "conversation_history":
                    st.session_state[key] = []
                else:
                    del st.session_state[key]
        
        # Set flag to clear input on next rerun (instead of directly modifying session state)
        st.session_state.clear_input = True
        
        # Force reinitialization on next query
        st.session_state.initialized = False
        
        # Show success message with enhanced visibility
        st.success("✅ Conversation cleared successfully!")
        
        # Force a clean restart
        st.rerun()
    
    # Process query (either from Enter key or Submit button)
    if (query and query.strip()) or submit_clicked:
        if not query or not query.strip():
            st.warning("⚠️ Please enter a question before submitting.")
            return
            
        if not st.session_state.get("initialized", False):
            st.error("Application not properly initialized. Please refresh the page.")
            return
        
        result = process_query(query, st.session_state.qa_chain)
        
        if "error" in result:
            st.markdown(f'<div class="error-message">❌ {result["error"]}</div>', 
                       unsafe_allow_html=True)
        else:
            answer = result.get("answer", "")
            source_docs = result.get("source_documents", [])
            
            # Add source documents to session state
            for doc in source_docs:
                source = doc.metadata.get("source", "N/A")
                if source and source != "N/A":
                    st.session_state["documents"].add(source)
            
            # Display response
            if not answer or "context does not include" in answer.lower():
                st.warning("⚠️ No relevant data found for that question. Please try rephrasing your query.")
            else:
                st.markdown('<div class="response-container">', unsafe_allow_html=True)
                
                # Response header
                st.markdown('''
                <div class="response-header">
                    <div class="response-icon">AI</div>
                    <h3 class="response-title">Investment Analysis</h3>
                </div>
                ''', unsafe_allow_html=True)
                
                # Parse and display answer with enhanced formatting
                if "Detailed Analysis:" in answer:
                    parts = answer.split("Detailed Analysis:", 1)
                    answer_part = parts[0].replace("Answer:", "").strip()
                    explanation_part = parts[1].strip()
                    
                    # Format answer as concise paragraph
                    formatted_answer = format_answer_paragraph(answer_part)
                    
                    # Add citations to detailed analysis
                    formatted_explanation = add_citations_to_analysis(explanation_part, source_docs)
                    
                    st.markdown(f'<div class="custom-answer">{formatted_answer}</div>', 
                               unsafe_allow_html=True)
                    st.markdown(f'<div class="custom-explanation">{formatted_explanation}</div>', 
                               unsafe_allow_html=True)
                else:
                    # Format single response as concise paragraph
                    formatted_answer = format_answer_paragraph(answer)
                    st.markdown(f'<div class="custom-answer">{formatted_answer}</div>', 
                               unsafe_allow_html=True)
                
                # Show source information
                if source_docs:
                    with st.expander(f"📚 Sources Used ({len(source_docs)} documents)"):
                        sources_used = set()
                        for doc in source_docs:
                            source = doc.metadata.get("source", "Unknown")
                            if source not in sources_used:
                                sources_used.add(source)
                                st.write(f"• {source}")
                
                # Enhanced feedback section with better visibility
                st.markdown('<div class="feedback-container">', unsafe_allow_html=True)
                feedback_col1, feedback_col2 = st.columns(2)
                
                with feedback_col1:
                    if st.button("👍 Helpful", key="positive_feedback", use_container_width=True):
                        handle_feedback(query, "positive")
                
                with feedback_col2:
                    if st.button("👎 Not Helpful", key="negative_feedback", use_container_width=True):
                        handle_feedback(query, "negative")
                
                st.markdown('</div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
                # Update last query
                st.session_state["last_query"] = query

def render_analytics_page():
    """Render analytics dashboard"""
    st.markdown("<h1 class='main-header'>📊 Analytics Dashboard</h1>", unsafe_allow_html=True)
    
    # Conversation stats
    conversation_count = len(st.session_state.get("conversation_history", []))
    feedback_count = len(st.session_state.get("feedback_log", []))
    error_count = len(st.session_state.get("error_log", []))
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f'''
        <div class="metrics-card">
            <h3>💬 Conversations</h3>
            <h2>{conversation_count}</h2>
        </div>
        ''', unsafe_allow_html=True)
    
    with col2:
        st.markdown(f'''
        <div class="metrics-card">
            <h3>👍 Feedback</h3>
            <h2>{feedback_count}</h2>
        </div>
        ''', unsafe_allow_html=True)
    
    with col3:
        st.markdown(f'''
        <div class="metrics-card">
            <h3>⚠️ Errors</h3>
            <h2>{error_count}</h2>
        </div>
        ''', unsafe_allow_html=True)
    
    # Recent queries
    if st.session_state.get("conversation_history"):
        st.markdown("### Recent Queries")
        for item in st.session_state.conversation_history[-5:]:
            if item["type"] == "user":
                st.markdown(f"- **{item['timestamp'][:19]}**: {item['query']}")

def render_settings_page():
    """Render settings page"""
    st.markdown("<h1 class='main-header'>⚙️ Settings</h1>", unsafe_allow_html=True)
    
    # System status
    st.markdown("### System Status")
    
    status_items = [
        ("Environment Variables", validate_environment()),
        ("Vector Store", st.session_state.get("initialized", False)),
        ("Language Model", st.session_state.get("initialized", False)),
    ]
    
    for item, status in status_items:
        status_icon = "✅" if status else "❌"
        st.markdown(f"{status_icon} {item}")
    
    # Clear data options
    st.markdown("### Data Management")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Clear Conversation History", use_container_width=True):
            st.session_state.conversation_history = []
            st.success("✅ Conversation history cleared!")
    
    with col2:
        if st.button("Clear Feedback Log", use_container_width=True):
            st.session_state.feedback_log = []
            st.success("✅ Feedback log cleared!")
    
    # Debug information
    with st.expander("Debug Information"):
        st.write("Session State Keys:", list(st.session_state.keys()))
        st.write("Error Log:", st.session_state.get("error_log", []))
        
        # Show vectorstore stats
        if st.session_state.get("initialized", False):
            try:
                vectorstore = initialize_vectorstore()
                if vectorstore:
                    vector_count = vectorstore.index.ntotal
                    st.write(f"Vectorstore Status: {vector_count} vectors loaded")
                    
                    # Quick test search
                    test_results = vectorstore.similarity_search("VFIAX", k=3)
                    st.write(f"Quick Test Search (VFIAX): {len(test_results)} results found")
                    
                    if test_results:
                        st.write("Sample result source:", test_results[0].metadata.get('source', 'Unknown'))
            except Exception as e:
                st.write(f"Vectorstore test failed: {e}")

if __name__ == "__main__":
    main()