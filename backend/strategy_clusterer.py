import numpy as np
from embedding_utils import EmbeddingManager

class StrategyClusterer:
    def __init__(self, embed_mgr):
        self.embed_mgr = embed_mgr
        self.clusters = {} # cluster_id: {'centroid': vector, 'name': str, 'description': str}

    def define_clusters_from_samples(self, sample_posts):
        """
        sample_posts: list of {'본문': text, 'category': name, 'desc': description}
        Use these as initial centroids for strategic clusters.
        """
        for i, post in enumerate(sample_posts):
            vector = self.embed_mgr.get_embedding(post['본문'])
            if vector is not None:
                self.clusters[f"Cluster_{i+1}"] = {
                    'centroid': np.array(vector),
                    'name': post.get('category', f"Category_{i+1}"),
                    'description': post.get('desc', ""),
                    'example_text': post['본문']
                }

    def get_closest_cluster(self, text):
        vector = self.embed_mgr.get_embedding(text)
        if vector is None or not self.clusters:
            return None
        
        vector = np.array(vector)
        best_cluster = None
        max_sim = -1.0
        
        for cid, cinfo in self.clusters.items():
            # Cosine similarity (simplified since vectors are usually normalized)
            sim = np.dot(vector, cinfo['centroid']) / (np.linalg.norm(vector) * np.linalg.norm(cinfo['centroid']))
            if sim > max_sim:
                max_sim = sim
                best_cluster = cid
        
        return best_cluster

    def compute_context_weights(self, product_info):
        """
        Compare product info with cluster centroids to boost relevant strategies.
        """
        product_vector = self.embed_mgr.get_embedding(product_info)
        if product_vector is None:
            return {cid: 1.0 for cid in self.clusters}
        
        product_vector = np.array(product_vector)
        weights = {}
        
        for cid, cinfo in self.clusters.items():
            sim = np.dot(product_vector, cinfo['centroid']) / (np.linalg.norm(product_vector) * np.linalg.norm(cinfo['centroid']))
            # Boost weight based on similarity (min 0.8, max 1.5)
            weights[cid] = 0.8 + (sim * 0.7) 
            
        return weights
