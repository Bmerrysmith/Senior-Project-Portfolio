import os
import gensim
import numpy as np
from numpy.linalg import norm
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import qdrant_client
from qdrant_client.models import ScoredPoint, SearchParams
from openai import OpenAI
import uvicorn

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
QDRANT_HOST = os.getenv("QDRANT_HOST")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME")

# Initialize FastAPI app
app = FastAPI()

# Input request schema
class SimilarityRequest(BaseModel):
    answer: str
    data: str = None  # Optional direct data comparison
    collection: str = None

# Helper function to get embeddings from OpenAI
def get_openai_embedding(text: str):
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.embeddings.create(
            input=text,
            model="text-embedding-ada-002"
        ).data[0].embedding
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI embedding error: {e}")

# Helper function to process Qdrant results
def process_qdrant_results(results):
    try:
        if not results:
            raise ValueError("No results returned from Qdrant")

        processed_results = []
        for point in results:
            if isinstance(point, ScoredPoint):
                processed_results.append({
                    "id": point.id,
                    "payload": point.payload,
                    "score": point.score
                })
            else:
                raise AttributeError(f"Unexpected result format: {point}")

        return processed_results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing Qdrant results: {e}")

# Function to compute the vector sum
def vector_sum(word_list, model: gensim.models.Word2Vec):
    vector_sum = np.zeros(model.vector_size)
    for word in word_list:
        if word in model.wv:
            vector_sum += model.wv[word]
    return vector_sum

# Function to compute cosine similarity
def cosine_similarity(v1, v2):
    return np.dot(v1, v2) / (norm(v1) * norm(v2))

# API Endpoint for similarity computation
@app.post("/similarity")
def get_similarity(request: SimilarityRequest):
    try:
        if request.collection is None:
            request.collection = QDRANT_COLLECTION_NAME
        processed_results = []
        embedding = get_openai_embedding(request.answer)
        
        if request.data:
            # Direct data comparison without Qdrant
            qdrantAns = [gensim.utils.simple_preprocess(request.data)]
            qAns = sum(qdrantAns, [])
            qAns = [qAns]
        else:
            # Step 1: Connect to Qdrant client
            client = qdrant_client.QdrantClient(
                host=QDRANT_HOST,
                port=443,
                api_key=QDRANT_API_KEY,
                https=True
            )

            # Step 3: Search Qdrant for content similar to the embedding
            search_results = client.search(
                collection_name= request.collection,
                query_vector=embedding,
                limit=5,
                search_params=SearchParams()
            )
            
            # Step 4: Obtain qdrant content related to the chatbot answer
            processed_results = process_qdrant_results(search_results)
            qdrantAns = [answer['payload']['page_content'] for answer in processed_results]

            # Step 4.1: Convert Qdrant content into a word dictionary
            tempQAns = [gensim.utils.simple_preprocess(answer) for answer in qdrantAns]
            qAns = sum(tempQAns, [])
            qAns = [qAns]

        # Step 4.2: Convert chatbot answer into a word dictionary
        aichatbotAns = [gensim.utils.simple_preprocess(request.answer)]

        model = gensim.models.Word2Vec(window=10, min_count=1, workers=4)

        # Step 4.3: Build vocabulary and train
        model.build_vocab(aichatbotAns + qAns, progress_per=1000)
        model.train(aichatbotAns + qAns, total_examples=model.corpus_count, epochs=model.epochs)

        # Step 4.4: Convert Qdrant content into a vector
        q_vector_sum = vector_sum(qAns[0], model)
        qdrant_embedding = np.squeeze(np.asarray(q_vector_sum))

        # Step 4.5: Convert chatbot answer into a vector
        cb_vector_sum = vector_sum(aichatbotAns[0], model)
        chatbot_embedding = np.squeeze(np.asarray(cb_vector_sum))

        # Step 5: Apply cosine similarity to validate chatbot answer accuracy
        similarity = cosine_similarity(chatbot_embedding, qdrant_embedding)

        return {"result": f"{similarity:.0%}", "qdrant_content": processed_results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

# Run with uvicorn directly in the script
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)