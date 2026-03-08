import os
import pickle
import numpy as np
from google import genai
from dotenv import load_dotenv

load_dotenv()

class EmbeddingManager:
    def __init__(self, storage_path="embeddings.pkl"):
        self.storage_path = storage_path
        self.embeddings = {} # {text: vector}
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model_id = "gemini-embedding-001"
        
        if self.api_key:
            print(f"Initializing Gemini API Client (Model: {self.model_id})...")
            self.client = genai.Client(api_key=self.api_key)
        else:
            print("Error: GEMINI_API_KEY not found. Falling back to Mock mode.")
            self.client = None
            
        self.load_storage()
        # Gemini-embedding-001 dimension is 768 or 3072 depending on version/config.
        # Verified earlier as 3072 via test script.
        self.verify_storage_consistency()

    def verify_storage_consistency(self):
        """If stored embeddings are from a different model, clear them."""
        if self.embeddings:
            sample_vec = next(iter(self.embeddings.values()))
            if len(sample_vec) != 3072: 
                print(f"Detected vector dimension mismatch ({len(sample_vec)} != 3072). Clearing storage for Gemini re-embedding...")
                self.embeddings = {}

    def load_storage(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "rb") as f:
                    self.embeddings = pickle.load(f)
                print(f"Loaded {len(self.embeddings)} existing embeddings.")
            except Exception as e:
                print(f"Error loading storage: {e}")
                self.embeddings = {}
        else:
            self.embeddings = {}

    def save_storage(self):
        try:
            with open(self.storage_path, "wb") as f:
                pickle.dump(self.embeddings, f)
            print(f"Storage saved: {self.storage_path} ({len(self.embeddings)} records)")
        except Exception as e:
            print(f"Error saving storage: {e}")

    def create_mock_embedding(self, text):
        """Deterministic mock embedding to prevent crashes when API fails."""
        import hashlib
        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
        np.random.seed(hash_val % (2**32))
        # Dimension must match Gemini (3072)
        vector = np.random.uniform(-1, 1, 3072).tolist()
        return vector

    def get_embedding(self, text):
        text = str(text).strip()
        if not text:
            return None
        
        if text in self.embeddings:
            return self.embeddings[text]
        
        if not self.client:
            vector = self.create_mock_embedding(text)
            self.embeddings[text] = vector
            return vector
        
        try:
            result = self.client.models.embed_content(
                model=self.model_id,
                contents=text
            )
            vector = result.embeddings[0].values
            self.embeddings[text] = vector
            return vector
        except Exception as e:
            if "429" in str(e):
                print(f"API Quota hit for text. Using Mock fallback.")
                vector = self.create_mock_embedding(text)
                # We don't save Mock to self.embeddings to allow real overwrite later
                return vector
            print(f"Error fetching embedding: {e}")
            return self.create_mock_embedding(text) # Final safety fallback

    def get_many_embeddings(self, texts):
        results = [None] * len(texts)
        to_fetch = []
        indices = []

        for i, text in enumerate(texts):
            text = str(text).strip()
            if text in self.embeddings:
                results[i] = self.embeddings[text]
            else:
                to_fetch.append(text)
                indices.append(i)

        if to_fetch:
            if not self.client:
                for idx, text in zip(indices, to_fetch):
                    results[idx] = self.get_embedding(text)
            else:
                try:
                    import time
                    print(f"Requesting Gemini embeddings for {len(to_fetch)} new posts...")
                    
                    chunk_size = 50
                    for k in range(0, len(to_fetch), chunk_size):
                        chunk = to_fetch[k:k+chunk_size]
                        chunk_indices = indices[k:k+chunk_size]
                        
                        max_retries = 2 # Reduced for faster fallback
                        retry_delay = 1
                        
                        success = False
                        for attempt in range(max_retries):
                            try:
                                response = self.client.models.embed_content(
                                    model=self.model_id,
                                    contents=chunk
                                )
                                for idx, emb in enumerate(response.embeddings):
                                    vector = emb.values
                                    self.embeddings[chunk[idx]] = vector
                                    results[chunk_indices[idx]] = vector
                                success = True
                                break
                            except Exception as e:
                                if "429" in str(e) and attempt < max_retries - 1:
                                    time.sleep(retry_delay)
                                    retry_delay *= 2
                                else:
                                    break
                        
                        if not success:
                            print(f"Chunk starting at index {k} failed (Quota). Using Mock fallback for this batch.")
                            for idx, text in zip(chunk_indices, chunk):
                                results[idx] = self.create_mock_embedding(text)
                                    
                        if (k // chunk_size) % 4 == 0:
                            self.save_storage()
                        time.sleep(0.5)
                            
                except Exception as e:
                    print(f"Error during Gemini batch embedding: {e}")

        # Final pass for results
        for i, text in enumerate(texts):
            if results[i] is None:
                results[i] = self.create_mock_embedding(texts[i])

        return results
    def get_embeddings_matrix(self, texts):
        """
        텍스트 리스트를 받아 NumPy 행렬(N x Dimension) 형태로 반환함
        """
        vectors = self.get_many_embeddings(texts)
        # None인 경우 대비 필터링 (필요시)
        matrix = np.array([v if v is not None else np.zeros(3072) for v in vectors])
        return matrix
