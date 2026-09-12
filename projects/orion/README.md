# ORION: AI-Powered Mutual Fund Advisor
### Optimal Risk-Investment Outreach Navigator

*Developed during Infosys Summer 2025 Internship*

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Available-brightgreen)](https://fundsummary-b7bub6eacvc7e7bs.eastus2-01.azurewebsites.net/)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red.svg)](https://streamlit.io)
[![Azure](https://img.shields.io/badge/Azure-OpenAI-0078d4.svg)](https://azure.microsoft.com/en-us/products/ai-services/openai-service)

## Project Overview

ORION is an intelligent mutual fund advisory system that leverages Azure OpenAI's GPT-4 and advanced RAG (Retrieval-Augmented Generation) architecture to provide comprehensive investment analysis. The system processes extensive fund documentation, performance data, and risk metrics to deliver personalized investment insights through an intuitive conversational interface.

**🌐 Live Application:** [https://fundsummary-b7bub6eacvc7e7bs.eastus2-01.azurewebsites.net/](https://fundsummary-b7bub6eacvc7e7bs.eastus2-01.azurewebsites.net/)

##  Key Features

###  Intelligent Fund Analysis
- **Conversational AI Interface**: Natural language queries about mutual funds and investment strategies
- **Comprehensive Fund Coverage**: Analysis of 15+ major funds including VFIAX, VWELX, VBTLX, FMTIX, and more
- **Real-time Risk Assessment**: Dynamic evaluation of fund risk metrics, alpha, beta, and Sharpe ratios
- **Performance Comparisons**: Side-by-side analysis of multiple funds with detailed metrics

###  Advanced Data Processing
- **Multi-format Document Ingestion**: Processes JSON, PDF, and structured fund data
- **Vector Database Integration**: FAISS-powered semantic search across fund documentation
- **Smart Text Chunking**: Preserves financial context while optimizing for embeddings
- **Ticker Symbol Recognition**: Intelligent extraction and preservation of fund symbols

###  Modern User Experience
- **Responsive Design**: Mobile-optimized interface with glassmorphism UI elements
- **Dark/Light Theme Support**: Adaptive design with professional color schemes
- **Real-time Feedback System**: Integrated user satisfaction tracking
- **Analytics Dashboard**: Usage metrics and conversation analytics

## Technical Architecture

### Core Technologies
- **Frontend**: Streamlit with custom CSS/HTML
- **Backend**: Python with LangChain framework
- **AI Model**: Azure OpenAI GPT-4 with text-embedding-ada-002
- **Vector Database**: FAISS for semantic search
- **Document Processing**: PyMuPDF, NLTK for text preprocessing
- **Deployment**: Azure App Service with container deployment

### System Components

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Streamlit UI  │────│  LangChain RAG   │────│  Azure OpenAI   │
│                 │    │     Pipeline     │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                        │                       │
         │                        │                       │
         ▼                        ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ User Feedback   │    │ FAISS Vector DB │    │  Fund Documents │
│    System       │    │                  │    │   (PDF/JSON)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Data Sources
- **Fund Prospectuses**: Detailed investment strategies and objectives
- **Performance Reports**: Historical returns, risk metrics, and benchmarks
- **Risk Analytics**: Comprehensive risk assessments and volatility measures
- **Metadata**: Fund classifications, expense ratios, and operational details

##  Key Capabilities

### Investment Analysis Features
- **Fund Comparison Engine**: Multi-dimensional fund analysis with quantitative metrics
- **Risk Profiling**: Advanced risk assessment using modern portfolio theory
- **Performance Attribution**: Detailed breakdown of fund performance drivers
- **Sector Allocation Analysis**: Geographic and sector-wise investment distribution

### Query Examples
```
"Compare VFIAX and VWELX risk metrics"
"What is FMTIX alpha and how does it perform against benchmarks?"
"Show me VBTLX expense ratio and investment strategy"
"Which funds have the lowest volatility in large-cap category?"
```

### Response Format
**Concise Answer**: Direct response to user query with key metrics
**Detailed Analysis**: Comprehensive breakdown with:
- Fund rankings and quantitative metrics
- Risk assessment with specific calculations
- Investment implications and recommendations
- Additional considerations and caveats

## Technical Highlights

### Advanced RAG Implementation
- **Context-Aware Chunking**: Preserves financial terminology and ticker symbols
- **Multi-Document Retrieval**: Synthesizes information from multiple fund sources
- **Citation System**: Transparent source attribution for all recommendations
- **Semantic Search**: FAISS-powered similarity matching for relevant context

### Performance Optimizations
- **Caching Strategy**: Document processing and embedding caching
- **Batch Processing**: Efficient handling of large document collections
- **Rate Limit Management**: Robust Azure OpenAI API interaction
- **Error Recovery**: Comprehensive exception handling and retry logic

### Data Engineering Pipeline
```python
# Enhanced document processing with financial context preservation
class EnhancedDocumentProcessor:
    def extract_tickers(self, text: str) -> List[str]:
        # Intelligent ticker symbol extraction
    
    def enhanced_clean_text(self, text: str) -> str:
        # Financial data-aware text cleaning
    
    def intelligent_chunk_text(self, text: str) -> List[str]:
        # Context-preserving text segmentation
```

##  UI/UX Design

### Design Philosophy
- **Professional Aesthetics**: Financial services-grade visual design
- **Intuitive Navigation**: Streamlined user journey with minimal friction
- **Accessibility First**: WCAG compliant with proper contrast and semantic markup
- **Performance Focused**: Optimized loading times and responsive interactions

### Visual Features
- **Animated Logo**: Custom ORION branding with gradient effects
- **Interactive Elements**: Hover effects and smooth transitions
- **Data Visualization**: Clean tables and metrics presentation
- **Feedback Integration**: Seamless user satisfaction collection

##  Analytics & Monitoring

### Built-in Analytics
- **Conversation Tracking**: User query patterns and response quality
- **Performance Metrics**: System response times and success rates
- **User Feedback**: Integrated thumbs up/down rating system
- **Error Logging**: Comprehensive error tracking and debugging

### Usage Statistics
- Real-time conversation count monitoring
- Feedback sentiment analysis
- Popular query identification
- System health monitoring

## Project Impact

### Business Value
- **Investment Decision Support**: Data-driven fund selection assistance
- **Risk Management**: Comprehensive risk assessment capabilities
- **User Education**: Interactive learning about mutual fund investing
- **Operational Efficiency**: Automated analysis replacing manual research

### Technical Achievements
- **Scalable Architecture**: Container-based deployment supporting high concurrent users
- **AI Integration**: Advanced RAG implementation with production-grade reliability
- **Data Processing**: Efficient handling of complex financial document structures
- **User Experience**: Modern, responsive interface with professional design standards

## 🔧 Development Highlights

### Code Quality
- **Modular Architecture**: Clean separation of concerns with reusable components
- **Error Handling**: Comprehensive exception management and user feedback
- **Logging System**: Detailed logging for debugging and monitoring
- **Documentation**: Inline documentation and type hints throughout

### Security & Compliance
- **Environment Variables**: Secure API key management
- **Input Validation**: Robust user input sanitization
- **Rate Limiting**: Protection against API abuse
- **Error Sanitization**: Safe error message presentation

##  Learning Outcomes

### Technical Skills Developed
- **Large Language Model Integration**: Hands-on experience with GPT-4 and embeddings
- **Vector Database Management**: FAISS implementation and optimization
- **Full-Stack Development**: End-to-end application development and deployment
- **Cloud Services**: Azure OpenAI and App Service utilization

### Professional Development
- **Project Management**: End-to-end project delivery from conception to deployment
- **User Experience Design**: Creating intuitive interfaces for complex data
- **Performance Optimization**: Scaling applications for production use
- **Documentation**: Technical writing and project presentation skills

##  Future Enhancements

### Planned Features
- **Portfolio Optimization**: Modern portfolio theory implementation
- **Real-time Data**: Live market data integration
- **Advanced Visualizations**: Interactive charts and graphs
- **Mobile App**: Native mobile application development

### Technical Roadmap
- **Database Integration**: PostgreSQL for persistent data storage
- **API Development**: RESTful API for third-party integrations
- **Machine Learning**: Custom models for fund recommendation
- **Multi-language Support**: Internationalization capabilities

## Acknowledgments

**Infosys Summer 2025 Internship Program**
- Mentorship and guidance from Infosys technical team
- Access to Azure cloud resources and development environment
- Collaborative learning experience with fellow interns

**Technologies & Frameworks**
- OpenAI for advanced language model capabilities
- Microsoft Azure for cloud infrastructure
- Streamlit community for rapid prototyping tools
- LangChain for RAG framework implementation

---

*This project represents the culmination of learning and development during the Infosys Summer 2025 Internship, demonstrating practical application of AI technologies in financial services.*

**Project Repository**: Advanced RAG-based Investment Advisory System  
**Deployment**: Azure App Service with Container Registry  
**Status**: Production Ready ✅
