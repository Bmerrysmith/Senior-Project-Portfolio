import os
from langchain_core.documents import Document

# 1. Install PyMuPDF if you haven't
# pip install pymupdf

import fitz  # PyMuPDF

def extract_pdf_text(pdf_path):
    """Extract all text from a PDF file using PyMuPDF."""
    doc = fitz.open(pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    return full_text

def clean_text(text):
    """Remove problematic characters, collapse whitespace, etc."""
    import re
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def chunk_text(text, max_chunk=800):
    """Chunk text into sentences, keeping each chunk under max_chunk chars."""
    from nltk.tokenize import sent_tokenize
    import nltk
    nltk.download('punkt', quiet=True)
    sentences = sent_tokenize(text)
    chunks, cur = [], ""
    for s in sentences:
        if len(cur) + len(s) < max_chunk:
            cur += " " + s
        else:
            chunks.append(cur.strip())
            cur = s
    if cur:
        chunks.append(cur.strip())
    return chunks

# ---- PDF Paths (update this list) ----
pdf_paths = [
    "p021.pdf",  # Example: the file you uploaded
    # Add more PDF file paths here as needed
]

docs = []
skipped = 0

for pdf_path in pdf_paths:
    try:
        pdf_text = extract_pdf_text(pdf_path)
        pdf_text = clean_text(pdf_text)
        for chunk in chunk_text(pdf_text):
            docs.append(Document(
                page_content=chunk,
                metadata={"source": os.path.basename(pdf_path)}
            ))
        print(f"Processed {pdf_path}: {len(docs)} chunks so far")
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        skipped += 1

print(f"Loaded {len(docs)} chunks from {len(pdf_paths)} PDFs (skipped {skipped}).")

# ---- Now you can pass docs to your embedding/indexing pipeline as before ----
