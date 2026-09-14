def chunk_text(text, chunk_size, overlap):
    text = text.strip()
    if not text:
        return []
    if overlap >= chunk_size:
        raise ValueError("CHUNK_OVERLAP must be less than CHUNK_SIZE")

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks
