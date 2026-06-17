"""RAG (Retrieval Augmented Generation) Service with Provider Abstraction."""

import os
import json
import re
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod
import logging

from app.services.document_parser import DocumentParser, get_demo_document_content

logger = logging.getLogger(__name__)


# ==================== Provider Interface ====================


class RetrieverProvider(ABC):
    """Abstract base class for RAG retriever providers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass
    
    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is properly configured."""
        pass
    
    @abstractmethod
    async def retrieve(self, query: str, chunks: List[Dict], top_k: int = 5) -> List[Dict]:
        """Retrieve relevant chunks for a query."""
        pass
    
    @abstractmethod
    async def generate_answer(self, question: str, context: str) -> str:
        """Generate answer using the retrieved context."""
        pass


# ==================== Provider Implementations ====================


class LocalMockRetrieverProvider(RetrieverProvider):
    """Local keyword-based retrieval without external API."""
    
    def __init__(self):
        self._name = "Local Mock"
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def is_available(self) -> bool:
        return True  # Always available
    
    async def retrieve(self, query: str, chunks: List[Dict], top_k: int = 5) -> List[Dict]:
        """Simple keyword-based retrieval."""
        query_words = set(query.lower().split())
        
        scored_chunks = []
        for chunk in chunks:
            content_lower = chunk.get('content', '').lower()
            content_words = set(content_lower.split())
            
            # Calculate relevance score
            matches = len(query_words & content_words)
            if matches > 0:
                score = matches / len(query_words)
                # Bonus for exact phrase matches
                if query.lower() in content_lower:
                    score += 0.5
                scored_chunks.append((score, chunk))
        
        # Sort by score and return top k
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored_chunks[:top_k]]
    
    async def generate_answer(self, question: str, context: str) -> str:
        """Generate answer from context using simple extraction."""
        if not context.strip():
            return "I couldn't find relevant information in the uploaded documents to answer your question."
        
        # Simple approach: extract sentences containing query keywords
        question_words = [w for w in question.lower().split() if len(w) > 3]
        
        sentences = re.split(r'[.!?]+', context)
        relevant_sentences = []
        
        for sentence in sentences:
            sentence_lower = sentence.lower().strip()
            if not sentence_lower:
                continue
            # Check if any key words match
            matches = sum(1 for word in question_words if word in sentence_lower)
            if matches >= 2:
                relevant_sentences.append(sentence.strip())
        
        if relevant_sentences:
            # Build answer from relevant sentences
            answer_parts = relevant_sentences[:5]  # Max 5 sentences
            answer = ". ".join(answer_parts)
            if not answer.endswith('.'):
                answer += "."
            return answer
        else:
            # Fallback: return first part of context
            return context[:500] + "..." if len(context) > 500 else context


class OpenAIRetrieverProvider(RetrieverProvider):
    """OpenAI-powered RAG provider."""
    
    def __init__(self):
        self._name = "OpenAI"
        self._client = None
        self._api_key = os.getenv("OPENAI_API_KEY")
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def is_available(self) -> bool:
        return bool(self._api_key)
    
    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None and self._api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self._api_key)
            except ImportError:
                logger.warning("OpenAI package not installed")
                return None
        return self._client
    
    async def retrieve(self, query: str, chunks: List[Dict], top_k: int = 5) -> List[Dict]:
        """Use OpenAI embeddings for semantic search (simplified)."""
        client = self._get_client()
        if not client:
            # Fall back to mock retriever
            mock = LocalMockRetrieverProvider()
            return await mock.retrieve(query, chunks, top_k)
        
        try:
            # Get query embedding
            query_response = client.embeddings.create(
                model="text-embedding-3-small",
                input=query
            )
            query_embedding = query_response.data[0].embedding
            
            # Simple cosine similarity
            import math
            
            def cosine_sim(a: List[float], b: List[float]) -> float:
                dot = sum(x * y for x, y in zip(a, b))
                norm_a = math.sqrt(sum(x * x for x in a))
                norm_b = math.sqrt(sum(x * x for x in b))
                return dot / (norm_a * norm_b) if norm_a and norm_b else 0
            
            # Note: For production, store embeddings in DB and use vector similarity
            # For now, fall back to keyword matching
            mock = LocalMockRetrieverProvider()
            return await mock.retrieve(query, chunks, top_k)
            
        except Exception as e:
            logger.error(f"OpenAI retrieval error: {e}")
            mock = LocalMockRetrieverProvider()
            return await mock.retrieve(query, chunks, top_k)
    
    async def generate_answer(self, question: str, context: str) -> str:
        """Generate answer using OpenAI GPT."""
        client = self._get_client()
        if not client:
            mock = LocalMockRetrieverProvider()
            return await mock.generate_answer(question, context)
        
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an assistant helping exhibition booth companies with compliance questions. Answer based ONLY on the provided context. If the answer isn't in the context, say so."},
                    {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"}
                ],
                max_tokens=500,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI generation error: {e}")
            mock = LocalMockRetrieverProvider()
            return await mock.generate_answer(question, context)


class NvidiaNeMoRetrieverProvider(RetrieverProvider):
    """NVIDIA NeMo Retriever placeholder for future deployment."""
    
    def __init__(self):
        self._name = "NVIDIA NeMo"
        self._api_key = os.getenv("NVIDIA_API_KEY")
        self._base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        self._endpoint = os.getenv("NEMO_RETRIEVER_ENDPOINT", "/retrieval")
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def is_available(self) -> bool:
        """Check if NVIDIA API is configured."""
        return bool(self._api_key)
    
    async def retrieve(self, query: str, chunks: List[Dict], top_k: int = 5) -> List[Dict]:
        """Retrieve using NVIDIA NeMo Retriever (placeholder)."""
        if not self.is_available:
            mock = LocalMockRetrieverProvider()
            return await mock.retrieve(query, chunks, top_k)
        
        # TODO: Implement NVIDIA NeMo Retriever API call
        # Expected API format:
        # POST {base_url}/retrieval
        # Headers: Authorization: Bearer {api_key}
        # Body: {"query": query, "documents": chunks}
        
        logger.info("NVIDIA NeMo Retriever not yet implemented, using mock")
        mock = LocalMockRetrieverProvider()
        return await mock.retrieve(query, chunks, top_k)
    
    async def generate_answer(self, question: str, context: str) -> str:
        """Generate answer using NVIDIA NIM (placeholder)."""
        if not self.is_available:
            mock = LocalMockRetrieverProvider()
            return await mock.generate_answer(question, context)
        
        # TODO: Implement NVIDIA NIM API call for answer generation
        logger.info("NVIDIA NIM generation not yet implemented, using mock")
        mock = LocalMockRetrieverProvider()
        return await mock.generate_answer(question, context)


class DeepSeekRetrieverProvider(RetrieverProvider):
    """DeepSeek-powered RAG provider."""
    
    def __init__(self):
        self._name = "DeepSeek"
        self._api_key = os.getenv("DEEPSEEK_API_KEY")
        self._base_url = "https://api.deepseek.com"
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def is_available(self) -> bool:
        return bool(self._api_key)
    
    async def retrieve(self, query: str, chunks: List[Dict], top_k: int = 5) -> List[Dict]:
        """Retrieve using DeepSeek (simplified keyword matching for now)."""
        if not self.is_available:
            mock = LocalMockRetrieverProvider()
            return await mock.retrieve(query, chunks, top_k)
        
        # TODO: Implement DeepSeek embedding-based retrieval
        mock = LocalMockRetrieverProvider()
        return await mock.retrieve(query, chunks, top_k)
    
    async def generate_answer(self, question: str, context: str) -> str:
        """Generate answer using DeepSeek."""
        if not self.is_available:
            mock = LocalMockRetrieverProvider()
            return await mock.generate_answer(question, context)
        
        try:
            import httpx
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": "You are an assistant helping exhibition booth companies with compliance questions. Answer based ONLY on the provided context."},
                            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}
                        ],
                        "max_tokens": 500,
                        "temperature": 0.3
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    logger.error(f"DeepSeek API error: {response.status_code}")
                    mock = LocalMockRetrieverProvider()
                    return await mock.generate_answer(question, context)
                    
        except Exception as e:
            logger.error(f"DeepSeek generation error: {e}")
            mock = LocalMockRetrieverProvider()
            return await mock.generate_answer(question, context)


# ==================== Provider Factory ====================


class RAGService:
    """Main RAG service with provider management."""
    
    def __init__(self):
        self._providers = {
            'mock': LocalMockRetrieverProvider(),
            'openai': OpenAIRetrieverProvider(),
            'nvidia': NvidiaNeMoRetrieverProvider(),
            'deepseek': DeepSeekRetrieverProvider(),
        }
        self._default_provider = 'mock'
    
    def get_provider(self, name: str = None) -> RetrieverProvider:
        """Get retriever provider by name."""
        if name is None:
            name = self._default_provider
        return self._providers.get(name, self._providers['mock'])
    
    def get_active_provider(self) -> tuple[str, RetrieverProvider]:
        """Get the best available provider."""
        # Priority: OpenAI > DeepSeek > NVIDIA > Mock
        for provider_name in ['openai', 'deepseek', 'nvidia', 'mock']:
            provider = self._providers[provider_name]
            if provider.is_available:
                return provider_name, provider
        
        return 'mock', self._providers['mock']
    
    def get_provider_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all providers."""
        status = {}
        for name, provider in self._providers.items():
            status[name] = {
                'name': provider.name,
                'available': provider.is_available,
                'active': False
            }
        
        active_name, _ = self.get_active_provider()
        status[active_name]['active'] = True
        
        return status
    
    async def query(self, question: str, chunks: List[Dict], provider: str = None) -> Dict[str, Any]:
        """Process a RAG query."""
        if provider is None:
            provider, retriever = self.get_active_provider()
        else:
            retriever = self.get_provider(provider)
        
        # Retrieve relevant chunks
        retrieved_chunks = await retriever.retrieve(question, chunks, top_k=5)
        
        # Build context from retrieved chunks
        context = "\n\n".join([
            f"[Source: {chunk.get('document_title', 'Unknown')} | {chunk.get('chunk_index', 0) + 1}]\n{chunk.get('content', '')}"
            for chunk in retrieved_chunks
        ])
        
        # Generate answer
        answer = await retriever.generate_answer(question, context)
        
        # Format sources
        sources = []
        for chunk in retrieved_chunks:
            sources.append({
                'document_id': chunk.get('document_id'),
                'document_title': chunk.get('document_title', 'Unknown'),
                'chunk_index': chunk.get('chunk_index', 0),
                'excerpt': chunk.get('content', '')[:200] + '...' if len(chunk.get('content', '')) > 200 else chunk.get('content', ''),
                'relevance': chunk.get('relevance', 1.0)
            })
        
        return {
            'answer': answer,
            'sources': sources,
            'provider': provider,
            'provider_name': retriever.name
        }


# Singleton instance
rag_service = RAGService()
