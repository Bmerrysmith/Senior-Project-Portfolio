# FIXED FAISS REBUILD SCRIPT - NO UNICODE ENCODING ISSUES
# This version removes emoji characters that cause encoding errors on Windows

import os
import json
import time
import logging
import re
import hashlib
import pickle
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from tqdm import tqdm
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_openai import AzureOpenAIEmbeddings
import fitz  # PyMuPDF
import nltk
from openai import RateLimitError

# ============================================================================
# CONFIGURATION - ALL YOUR FUND DOCUMENTS
# ============================================================================

@dataclass
class CompleteIndexingConfig:
    """Complete configuration for all your fund documents"""
    max_chunk_size: int = 1200
    chunk_overlap: int = 200
    batch_size: int = 30
    rate_limit_wait: int = 60
    max_retries: int = 3
    cache_dir: str = "cache"
    index_dir: str = "faiss_index_fund_data"
    nltk_path: str = os.path.expanduser(r'C:\Users\krock\nltk_data')
    
    def __post_init__(self):
        # JSON files
        self.json_files = [
            "Data/fund_risk_metrics.json",
            "Data/fund_metadata.json", 
            "Data/Definitions.json"
        ]
        
        # ALL your PDF files
        self.pdf_files = [
            # Core fund PDFs
            "Data/AGG.pdf",
            "Data/PRBLX.pdf", 
            "Data/VBAIX.pdf",
            "Data/VBTLX.pdf",
            "Data/VCIT.pdf",
            "Data/VFIAX.pdf",
            "Data/VTMFX.pdf",
            "Data/VWELX.pdf",
            
            # ALL Investment Reports
            "Data/AGG Investment Report (1).pdf",
            "Data/BOND Investment Report.pdf",
            "Data/FCPGX Investment Report.pdf", 
            "Data/FMTIX Investment Report.pdf",
            "Data/FSPTX Investment Report.pdf",
            "Data/FTBFX Investment Report.pdf",
            "Data/MAMOX Investment Report.pdf",
            "Data/PRBLX Investment Report.pdf",
            "Data/VBAIX Investment Report.pdf",
            "Data/VBTLX Investment Report.pdf", 
            "Data/VCIT Investment Report.pdf",
            "Data/VFIAX Investment Report (1).pdf",
            "Data/VSMAX Investment Report.pdf",
            "Data/VTIAX Investment Report.pdf",
            "Data/VTMFX Investment Report.pdf",
            "Data/VWELX Investment Report (1).pdf"
        ]
        
        # DOCX files (skip for now due to missing library)
        self.docx_files = []

# ============================================================================
# LOGGING SETUP (NO UNICODE CHARACTERS)
# ============================================================================

def setup_logging():
    """Setup logging without unicode characters"""
    Path("logs").mkdir(exist_ok=True)
    
    # Create custom formatter that handles encoding
    class SafeFormatter(logging.Formatter):
        def format(self, record):
            # Remove or replace unicode characters
            msg = super().format(record)
            # Replace common emojis with text equivalents
            replacements = {
                '✅': '[OK]',
                '❌': '[ERROR]', 
                '⚠️': '[WARNING]',
                '📁': '[FILE]',
                '🔧': '[PROCESSING]',
                '📊': '[INFO]',
                '🚀': '[START]',
                '🎯': '[TARGET]',
                '💡': '[TIP]'
            }
            for emoji, replacement in replacements.items():
                msg = msg.replace(emoji, replacement)
            return msg
    
    # Configure logging with safe formatter
    formatter = SafeFormatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # File handler
    file_handler = logging.FileHandler('logs/faiss_rebuild.log', encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Setup logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# ============================================================================
# NLTK SETUP
# ============================================================================

def setup_nltk(nltk_path: str):
    """Setup NLTK with proper error handling"""
    try:
        if nltk_path not in nltk.data.path:
            nltk.data.path.append(nltk_path)
        
        Path(nltk_path).mkdir(parents=True, exist_ok=True)
        
        print("Setting up NLTK...")
        nltk.download('punkt', download_dir=nltk_path, quiet=True)
        nltk.download('punkt_tab', download_dir=nltk_path, quiet=True)
        
        print("[OK] NLTK setup complete")
        return True
    except Exception as e:
        print(f"[ERROR] NLTK setup failed: {e}")
        return False

# ============================================================================
# ENHANCED DOCUMENT PROCESSOR
# ============================================================================

class EnhancedDocumentProcessor:
    """Enhanced document processor that preserves fund data and ticker symbols"""
    
    def __init__(self, config: CompleteIndexingConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.cache_dir = Path(config.cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # Fund ticker patterns
        self.ticker_patterns = [
            r'\b[A-Z]{3,5}X\b',    # VFIAX, VWELX, etc.
            r'\b[A-Z]{3,4}\b'      # AGG, SPY, QQQ, etc.
        ]
        
        # Financial keywords to preserve
        self.financial_keywords = [
            'expense ratio', 'risk', 'return', 'performance', 'alpha', 'beta',
            'sharpe', 'sortino', 'volatility', 'yield', 'aum', 'inception',
            'benchmark', 'category', 'allocation', 'portfolio', 'holdings'
        ]
    
    def _get_file_hash(self, file_path: str) -> str:
        """Generate hash for file caching"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return hashlib.md5(file_path.encode()).hexdigest()
    
    def _get_cache_path(self, file_path: str) -> Path:
        """Get cache file path"""
        file_hash = self._get_file_hash(file_path)
        cache_name = f"{Path(file_path).stem}_{file_hash}.pkl"
        return self.cache_dir / cache_name
    
    def _load_from_cache(self, file_path: str) -> Optional[List[Document]]:
        """Load processed documents from cache"""
        cache_path = self._get_cache_path(file_path)
        if cache_path.exists():
            try:
                with open(cache_path, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                self.logger.warning(f"Failed to load cache for {file_path}: {e}")
        return None
    
    def _save_to_cache(self, file_path: str, documents: List[Document]):
        """Save processed documents to cache"""
        cache_path = self._get_cache_path(file_path)
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(documents, f)
        except Exception as e:
            self.logger.warning(f"Failed to save cache for {file_path}: {e}")
    
    def extract_tickers(self, text: str) -> List[str]:
        """Extract ticker symbols from text"""
        tickers = set()
        
        for pattern in self.ticker_patterns:
            found = re.findall(pattern, text.upper())
            tickers.update(found)
        
        # Filter out common false positives
        exclude_words = {
            'THE', 'AND', 'FOR', 'YOU', 'ARE', 'NOT', 'BUT', 'CAN', 'ALL', 'ANY',
            'NEW', 'NOW', 'OUR', 'OUT', 'TWO', 'WAY', 'WHO', 'ITS', 'DID', 'GET',
            'HAS', 'HAD', 'HIS', 'HER', 'HOW', 'MAN', 'OLD', 'SEE', 'USE', 'HIM',
            'MAY', 'SAY', 'SHE', 'HER', 'NOW', 'HOW', 'ITS', 'ONE', 'TWO', 'SIX',
            'TEN', 'TOP', 'LOW', 'HIGH', 'NET', 'TAX', 'FEE', 'END', 'SET', 'RUN'
        }
        
        return [ticker for ticker in tickers 
                if ticker not in exclude_words and len(ticker) >= 3]
    
    def enhanced_clean_text(self, text: str) -> str:
        """Enhanced text cleaning that preserves financial data"""
        
        # Extract tickers and financial terms before cleaning
        original_tickers = self.extract_tickers(text)
        
        # Basic cleaning
        text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
        
        # Remove problematic characters but keep financial symbols
        text = re.sub(r'[^\w\s\-\.,;:!?()"\'\n$%/]', '', text)
        
        # Split into lines and filter
        lines = text.split('\n')
        meaningful_lines = []
        
        for line in lines:
            line = line.strip()
            # Keep substantial lines or those with important content
            if (len(line) > 15 or 
                any(ticker in line.upper() for ticker in original_tickers) or
                any(term.lower() in line.lower() for term in self.financial_keywords) or
                any(char in line for char in ['%', '$']) or
                re.search(r'\d+\.\d+', line)):  # Contains decimal numbers
                meaningful_lines.append(line)
        
        cleaned_text = ' '.join(meaningful_lines)
        
        # Ensure tickers are preserved
        for ticker in original_tickers:
            if ticker not in cleaned_text.upper():
                cleaned_text = f"{ticker} {cleaned_text}"
        
        return cleaned_text.strip()
    
    def intelligent_chunk_text(self, text: str, max_chunk: int = None) -> List[str]:
        """Intelligent chunking that preserves context"""
        if max_chunk is None:
            max_chunk = self.config.max_chunk_size
        
        overlap = self.config.chunk_overlap
        
        # Try NLTK sentence tokenization
        try:
            from nltk.tokenize import sent_tokenize
            sentences = sent_tokenize(text)
        except:
            # Fallback to simple splitting
            sentences = text.split('. ')
            sentences = [s.strip() + ('.' if not s.endswith('.') else '') for s in sentences]
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            # Check if adding this sentence would exceed limit
            potential_length = len(current_chunk) + len(sentence) + 1
            
            if potential_length > max_chunk and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                current_chunk += (" " + sentence if current_chunk else sentence)
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # Add intelligent overlap
        overlapped_chunks = []
        for i, chunk in enumerate(chunks):
            final_chunk = chunk
            
            # Add context from previous chunk
            if i > 0 and overlap > 0:
                prev_chunk = chunks[i-1]
                # Take last sentences from previous chunk
                prev_sentences = prev_chunk.split('. ')
                if len(prev_sentences) > 1:
                    context_sentences = prev_sentences[-2:]  # Last 2 sentences
                    context = '. '.join(context_sentences)
                    if len(context) < overlap:
                        final_chunk = f"{context} ... {final_chunk}"
            
            overlapped_chunks.append(final_chunk)
        
        return overlapped_chunks
    
    def extract_pdf_text(self, pdf_path: str) -> str:
        """Enhanced PDF text extraction"""
        try:
            doc = fitz.open(pdf_path)
            full_text = ""
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text = page.get_text()
                
                if page_text.strip():
                    full_text += f"\n--- Page {page_num + 1} ---\n{page_text}"
            
            doc.close()
            return full_text
            
        except Exception as e:
            self.logger.error(f"Error extracting PDF {pdf_path}: {e}")
            return ""
    
    def process_json_file(self, file_path: str) -> List[Document]:
        """Process JSON file with enhanced structure handling"""
        cached_docs = self._load_from_cache(file_path)
        if cached_docs:
            self.logger.info(f"[FILE] Loaded {len(cached_docs)} documents from cache: {file_path}")
            return cached_docs
        
        documents = []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading JSON {file_path}: {e}")
            return documents
        
        file_name = os.path.basename(file_path)
        
        if isinstance(data, dict):
            for key, content in data.items():
                if isinstance(content, dict):
                    # Format structured data nicely
                    formatted_content = json.dumps(content, indent=2)
                    
                    # Extract any tickers from the key or content
                    tickers = self.extract_tickers(f"{key} {formatted_content}")
                    
                    doc_text = self.enhanced_clean_text(f"{key}\n{formatted_content}")
                    
                    for chunk in self.intelligent_chunk_text(doc_text):
                        metadata = {
                            "source": file_name,
                            "key": key,
                            "type": "structured_data"
                        }
                        if tickers:
                            metadata["tickers"] = tickers
                        
                        documents.append(Document(
                            page_content=chunk,
                            metadata=metadata
                        ))
                else:
                    doc_text = self.enhanced_clean_text(f"{key}\n{str(content)}")
                    for chunk in self.intelligent_chunk_text(doc_text):
                        documents.append(Document(
                            page_content=chunk,
                            metadata={"source": file_name, "key": key, "type": "text_data"}
                        ))
        
        self._save_to_cache(file_path, documents)
        return documents
    
    def process_pdf_file(self, pdf_path: str) -> List[Document]:
        """Process PDF file with enhanced metadata"""
        cached_docs = self._load_from_cache(pdf_path)
        if cached_docs:
            self.logger.info(f"[FILE] Loaded {len(cached_docs)} documents from cache: {pdf_path}")
            return cached_docs
        
        documents = []
        
        try:
            pdf_text = self.extract_pdf_text(pdf_path)
            if not pdf_text.strip():
                self.logger.warning(f"No text extracted from {pdf_path}")
                return documents
            
            cleaned_text = self.enhanced_clean_text(pdf_text)
            chunks = self.intelligent_chunk_text(cleaned_text)
            
            # Extract tickers from filename and content
            filename = os.path.basename(pdf_path)
            filename_tickers = self.extract_tickers(filename)
            
            for i, chunk in enumerate(chunks):
                # Extract tickers from chunk content
                content_tickers = self.extract_tickers(chunk)
                all_tickers = list(set(filename_tickers + content_tickers))
                
                metadata = {
                    "source": filename,
                    "chunk_index": i,
                    "type": "pdf_content"
                }
                
                if all_tickers:
                    metadata["tickers"] = all_tickers
                    # Add primary ticker (usually from filename)
                    if filename_tickers:
                        metadata["primary_ticker"] = filename_tickers[0]
                
                documents.append(Document(
                    page_content=chunk,
                    metadata=metadata
                ))
            
            self._save_to_cache(pdf_path, documents)
            
        except Exception as e:
            self.logger.error(f"Error processing PDF {pdf_path}: {e}")
        
        return documents

# ============================================================================
# ENHANCED FAISS INDEXER
# ============================================================================

class EnhancedFAISSIndexer:
    """Enhanced FAISS indexer with robust error handling"""
    
    def __init__(self, config: CompleteIndexingConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.embedding = self._initialize_embedding()
    
    def _initialize_embedding(self) -> AzureOpenAIEmbeddings:
        """Initialize Azure OpenAI embeddings"""
        try:
            return AzureOpenAIEmbeddings(
                model="text-embedding-ada-002",
                deployment=os.getenv("AZURE_EMBED_DEPLOYMENT"),
                api_key=os.getenv("AZURE_API_KEY"),
                azure_endpoint=os.getenv("AZURE_API_BASE"),
                api_version=os.getenv("AZURE_EMBED_VERSION"),
                chunk_size=1000,
                max_retries=self.config.max_retries
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize embeddings: {e}")
            raise
    
    def create_index_with_progress(self, documents: List[Document]) -> FAISS:
        """Create FAISS index with detailed progress tracking"""
        total_docs = len(documents)
        self.logger.info(f"[PROCESSING] Creating FAISS index for {total_docs} documents...")
        
        # Filter out very short documents
        filtered_docs = [doc for doc in documents if len(doc.page_content.strip()) > 20]
        filtered_count = len(filtered_docs)
        
        if filtered_count < total_docs:
            self.logger.info(f"[INFO] Filtered to {filtered_count} substantial documents")
        
        # Process in batches
        batch_size = self.config.batch_size
        batches = [filtered_docs[i:i+batch_size] for i in range(0, filtered_count, batch_size)]
        
        vectorstores = []
        failed_batches = []
        
        print(f"\n[START] Processing {len(batches)} batches...")
        
        with tqdm(total=len(batches), desc="Creating embeddings") as pbar:
            for batch_idx, batch in enumerate(batches):
                success = False
                
                for attempt in range(self.config.max_retries):
                    try:
                        # Create vectorstore for this batch
                        vectorstore = FAISS.from_documents(batch, self.embedding)
                        vectorstores.append(vectorstore)
                        success = True
                        break
                        
                    except RateLimitError as e:
                        self.logger.warning(f"[WARNING] Rate limit hit on batch {batch_idx + 1}, attempt {attempt + 1}")
                        if attempt < self.config.max_retries - 1:
                            time.sleep(self.config.rate_limit_wait)
                        else:
                            self.logger.error(f"[ERROR] Failed batch {batch_idx + 1} after {self.config.max_retries} attempts")
                            failed_batches.append(batch_idx)
                    
                    except Exception as e:
                        self.logger.error(f"[ERROR] Unexpected error in batch {batch_idx + 1}: {e}")
                        if attempt < self.config.max_retries - 1:
                            time.sleep(10)
                        else:
                            failed_batches.append(batch_idx)
                
                pbar.update(1)
                
                if success:
                    # Small delay between batches
                    time.sleep(2)
        
        if failed_batches:
            self.logger.warning(f"[WARNING] {len(failed_batches)} batches failed: {failed_batches}")
        
        if not vectorstores:
            raise RuntimeError("[ERROR] No vectorstores were created successfully")
        
        # Merge all vectorstores
        self.logger.info("[PROCESSING] Merging vectorstores...")
        final_vectorstore = vectorstores[0]
        
        for vs in tqdm(vectorstores[1:], desc="Merging vectorstores"):
            try:
                final_vectorstore.merge_from(vs)
            except Exception as e:
                self.logger.error(f"Error merging vectorstore: {e}")
        
        return final_vectorstore

# ============================================================================
# MAIN REBUILD FUNCTION
# ============================================================================

def rebuild_faiss_index():
    """Main function to rebuild FAISS index with all documents"""
    
    print("[START] COMPLETE FAISS INDEX REBUILD")
    print("=" * 50)
    
    # Setup
    config = CompleteIndexingConfig()
    logger = setup_logging()
    
    logger.info("Starting complete FAISS index rebuild...")
    
    # Load environment variables
    load_dotenv()
    required_vars = ["AZURE_API_BASE", "AZURE_API_KEY", "AZURE_EMBED_DEPLOYMENT", "AZURE_EMBED_VERSION"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"[ERROR] Missing environment variables: {missing_vars}")
        return False
    
    # Setup NLTK
    if not setup_nltk(config.nltk_path):
        logger.error("[ERROR] Failed to setup NLTK")
        return False
    
    # Initialize processor and indexer
    processor = EnhancedDocumentProcessor(config)
    indexer = EnhancedFAISSIndexer(config)
    
    # Process all documents
    all_documents = []
    
    # Track file processing
    total_files = len(config.json_files) + len(config.pdf_files) + len(config.docx_files)
    processed_files = 0
    
    print(f"\n[INFO] Processing {total_files} files...")
    
    # Process JSON files
    for json_file in tqdm(config.json_files, desc="Processing JSON files"):
        if not os.path.exists(json_file):
            logger.warning(f"[WARNING] JSON file not found: {json_file}")
            continue
        
        try:
            documents = processor.process_json_file(json_file)
            all_documents.extend(documents)
            logger.info(f"[OK] {json_file}: {len(documents)} documents")
            processed_files += 1
        except Exception as e:
            logger.error(f"[ERROR] Failed to process {json_file}: {e}")
    
    # Process PDF files
    for pdf_file in tqdm(config.pdf_files, desc="Processing PDF files"):
        if not os.path.exists(pdf_file):
            logger.warning(f"[WARNING] PDF file not found: {pdf_file}")
            continue
        
        try:
            documents = processor.process_pdf_file(pdf_file)
            all_documents.extend(documents)
            logger.info(f"[OK] {pdf_file}: {len(documents)} documents")
            processed_files += 1
        except Exception as e:
            logger.error(f"[ERROR] Failed to process {pdf_file}: {e}")
    
    if not all_documents:
        logger.error("[ERROR] No documents were processed successfully")
        return False
    
    print(f"\n[INFO] PROCESSING SUMMARY:")
    print(f"Files processed: {processed_files}/{total_files}")
    print(f"Total document chunks: {len(all_documents)}")
    
    # Analyze ticker coverage
    tickers_found = set()
    for doc in all_documents:
        if "tickers" in doc.metadata:
            tickers_found.update(doc.metadata["tickers"])
    
    print(f"Tickers found: {sorted(tickers_found)}")
    
    # Create FAISS index
    try:
        start_time = time.time()
        vectorstore = indexer.create_index_with_progress(all_documents)
        
        # Save the index
        Path(config.index_dir).mkdir(parents=True, exist_ok=True)
        vectorstore.save_local(config.index_dir)
        
        end_time = time.time()
        
        print(f"\n[SUCCESS] FAISS INDEX REBUILD COMPLETE!")
        print(f"[OK] FAISS index created and saved")
        print(f"[TARGET] Location: {config.index_dir}")
        print(f"[INFO] Documents indexed: {len(all_documents)}")
        print(f"[TARGET] Tickers covered: {len(tickers_found)}")
        print(f"[INFO] Total time: {end_time - start_time:.2f} seconds")
        
        # Test the index
        print(f"\n[PROCESSING] Testing index...")
        test_queries = ["VFIAX", "VTSMX", "FMTIX", "expense ratio"]
        
        for query in test_queries:
            try:
                results = vectorstore.similarity_search(query, k=3)
                print(f"[OK] '{query}': {len(results)} results")
                
                # Show a sample result
                if results:
                    sample_content = results[0].page_content[:100] + "..."
                    print(f"     Sample: {sample_content}")
                    
            except Exception as e:
                print(f"[ERROR] '{query}': {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to create FAISS index: {e}")
        return False

# ============================================================================
# RUN THE REBUILD
# ============================================================================

if __name__ == "__main__":
    # Set environment to handle UTF-8 properly
    if os.name == 'nt':  # Windows
        os.environ['PYTHONIOENCODING'] = 'utf-8'
    
    success = rebuild_faiss_index()
    
    if success:
        print(f"\n[TARGET] NEXT STEPS:")
        print("1. Your FAISS index has been rebuilt with ALL your fund documents")
        print("2. Now you can update your App.py with enhanced retrieval")
        print("3. Restart your Streamlit app")
        print("4. Test with queries like 'Compare VFIAX and FMTIX'")
        print("5. You should now have data for all these tickers:")
        print("   VFIAX, VWELX, VBTLX, VBAIX, VCIT, VTMFX, VTIAX, VSMAX,")
        print("   FCPGX, FMTIX, FSPTX, FTBFX, PRBLX, MAMOX, AGG")
    else:
        print(f"\n[ERROR] REBUILD FAILED")
        print("Check the logs/faiss_rebuild.log file for detailed error information")
        print("Common issues:")
        print("- Missing environment variables in .env file")
        print("- Azure OpenAI API key issues")  
        print("- Missing PDF files in Data/ folder")