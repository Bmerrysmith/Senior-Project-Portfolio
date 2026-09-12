"""EagleGIS RAG model-serving microservice.

A standalone FastAPI service that exposes the RAG model layer (embeddings,
reranking, and LLM generation) so it can be containerized and deployed
independently from the main EagleGIS API. Designed to run on Google Cloud Run.
"""
