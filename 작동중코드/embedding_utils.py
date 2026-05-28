import gc
import hashlib
import os
import pickle
import shutil
import tempfile
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app_config import GlobalConfig

load_dotenv()


def _build_content_hash(text: str = None, image_paths_or_urls: list = None) -> str:
    img_list = []
    if image_paths_or_urls:
        if isinstance(image_paths_or_urls, str):
            img_list = [image_paths_or_urls]
        else:
            img_list = [str(url) for url in image_paths_or_urls]
    payload = f"{text or ''}{'|'.join(img_list)}"
    return hashlib.md5(payload.encode()).hexdigest()


def _is_retriable(exc):
    msg = str(exc).lower()
    return any(
        code in msg
        for code in ["429", "503", "resource exhausted", "unavailable", "deadline exceeded"]
    )


class EmbeddingManager:
    VECTOR_TYPES = ("text", "visual", "multi")
    DISK_STORE_VERSION = 1

    def __init__(self, storage_path=None):
        self.storage_path = Path(storage_path or GlobalConfig.STORAGE_PATH)
        self.disk_store_dir = self.storage_path.parent / f"{self.storage_path.stem}_diskstore"
        self.disk_manifest_path = self.disk_store_dir / "manifest.pkl"
        self.vector_dtype = np.float64
        # Runtime additions only. Precomputed vectors are served from disk-backed storage.
        self.embeddings = {"text": {}, "visual": {}, "multi": {}, "metadata": {}}
        self._disk_lookup = {e_type: {} for e_type in self.VECTOR_TYPES}
        self._disk_row_keys = {e_type: [] for e_type in self.VECTOR_TYPES}
        self._disk_vectors = {}
        self._metadata_lookup = {}
        self._storage_mode = "memory"
        self.api_key = GlobalConfig.GEMINI_API_KEY
        self.model_id = GlobalConfig.EMBEDDING_MODEL
        print(f"?? [EmbeddingManager v6.0] Initialized with model: {self.model_id}")

        if self.api_key:
            print(f"Initializing Gemini Multimodal Embedding Client (Model: {self.model_id})...")
            self.client = genai.Client(api_key=self.api_key)
        else:
            print("Error: GEMINI_API_KEY not found.")
            self.client = None

        self._file_cache = {}
        self.load_storage()

    def load_storage(self):
        if not self.storage_path.exists():
            return

        try:
            if not self._is_disk_store_ready():
                print("Preparing disk-backed embedding store...")
                self._build_disk_store_from_legacy_pickle()
            self._load_disk_store()
            print(
                f"Loaded disk store: {len(self._disk_row_keys.get('text', []))} text, "
                f"{len(self._disk_row_keys.get('visual', []))} visual records."
            )
            return
        except Exception as e:
            print(f"Error loading disk store: {e}. Falling back to legacy pickle mode.")

        try:
            data = self._load_legacy_storage()
            self.embeddings = data
            self._storage_mode = "memory"
            print(
                f"Loaded storage: {len(self.embeddings.get('text', {}))} text, "
                f"{len(self.embeddings.get('visual', {}))} visual records."
            )
        except Exception as e:
            print(f"Error loading storage: {e}")

    def save_storage(self):
        try:
            data = self._materialize_full_storage()
            with self.storage_path.open("wb") as f:
                pickle.dump(data, f)
            self._close_disk_vectors()
            self._build_disk_store_from_data(data)
            self._load_disk_store()
            self.embeddings = {"text": {}, "visual": {}, "multi": {}, "metadata": {}}
            print(f"Storage saved: {self.storage_path}")
        except Exception as e:
            print(f"Error saving storage: {e}")

    def get_content_hash(self, text: str, image_paths_or_urls: list = None) -> str:
        return _build_content_hash(text=text, image_paths_or_urls=image_paths_or_urls)

    def _normalize_storage_key(self, value):
        if value is None:
            return None
        return str(value).strip()

    def _disk_vector_path(self, e_type: str) -> Path:
        return self.disk_store_dir / f"{e_type}.npy"

    def _is_disk_store_ready(self) -> bool:
        if not self.disk_manifest_path.exists():
            return False
        try:
            with self.disk_manifest_path.open("rb") as f:
                manifest = pickle.load(f)
            stat = self.storage_path.stat()
            if manifest.get("version") != self.DISK_STORE_VERSION:
                return False
            if manifest.get("source_path") != str(self.storage_path):
                return False
            if manifest.get("source_size") != stat.st_size:
                return False
            if manifest.get("source_mtime_ns") != stat.st_mtime_ns:
                return False
            for e_type in self.VECTOR_TYPES:
                if not self._disk_vector_path(e_type).exists():
                    return False
            return True
        except Exception:
            return False

    def _load_legacy_storage(self):
        with self.storage_path.open("rb") as f:
            data = pickle.load(f)
        if isinstance(data, dict) and "text" in data:
            return data
        legacy = {"text": {}, "visual": {}, "multi": {}, "metadata": {}}
        legacy["multi"] = data
        return legacy

    def _add_lookup_alias(self, lookup: dict, alias, row_index: int):
        alias = self._normalize_storage_key(alias)
        if not alias:
            return
        lookup.setdefault(alias, row_index)

    def _build_bucket_lookup(self, e_type: str, keys, metadata_lookup: dict):
        lookup = {}
        for row_index, key in enumerate(keys):
            key_str = self._normalize_storage_key(key)
            self._add_lookup_alias(lookup, key_str, row_index)

            meta = metadata_lookup.get(key_str, {}) or {}
            text = str(meta.get("text", "") or "").strip()
            urls = meta.get("urls") or []

            if text:
                self._add_lookup_alias(lookup, text, row_index)
                if e_type == "text":
                    self._add_lookup_alias(lookup, _build_content_hash(text=text), row_index)
            if urls and e_type == "visual":
                self._add_lookup_alias(lookup, _build_content_hash(image_paths_or_urls=urls), row_index)
            if text and urls and e_type == "multi":
                self._add_lookup_alias(
                    lookup,
                    _build_content_hash(text=text, image_paths_or_urls=urls),
                    row_index,
                )
        return lookup

    def _build_disk_store_from_data(self, data):
        self.disk_store_dir.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = self.disk_store_dir.parent / f"{self.disk_store_dir.name}.tmp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        metadata_lookup = data.get("metadata", {}) if isinstance(data, dict) else {}
        stat = self.storage_path.stat() if self.storage_path.exists() else None
        manifest = {
            "version": self.DISK_STORE_VERSION,
            "source_path": str(self.storage_path),
            "source_size": stat.st_size if stat else 0,
            "source_mtime_ns": stat.st_mtime_ns if stat else 0,
            "dtype": str(np.dtype(self.vector_dtype)),
            "vector_types": list(self.VECTOR_TYPES),
            "buckets": {},
            "metadata": metadata_lookup,
        }

        for e_type in self.VECTOR_TYPES:
            bucket = data.get(e_type, {}) if isinstance(data, dict) else {}
            keys = list(bucket.keys())
            vector_path = temp_dir / f"{e_type}.npy"

            dim = 0
            if keys:
                first_vec = np.asarray(bucket[keys[0]], dtype=self.vector_dtype)
                dim = int(first_vec.shape[0]) if first_vec.ndim > 0 else 0

            mmap = np.lib.format.open_memmap(
                vector_path,
                mode="w+",
                dtype=self.vector_dtype,
                shape=(len(keys), dim),
            )
            for row_index, key in enumerate(keys):
                mmap[row_index] = np.asarray(bucket[key], dtype=self.vector_dtype)
            mmap.flush()
            del mmap

            manifest["buckets"][e_type] = {
                "count": len(keys),
                "dim": dim,
                "keys": [self._normalize_storage_key(key) for key in keys],
                "lookup": self._build_bucket_lookup(e_type, keys, metadata_lookup),
                "file_name": vector_path.name,
            }

        with (temp_dir / "manifest.pkl").open("wb") as f:
            pickle.dump(manifest, f)

        if self.disk_store_dir.exists():
            shutil.rmtree(self.disk_store_dir)
        temp_dir.replace(self.disk_store_dir)

    def _build_disk_store_from_legacy_pickle(self):
        data = self._load_legacy_storage()
        try:
            self._build_disk_store_from_data(data)
        finally:
            del data
            gc.collect()

    def _close_disk_vectors(self):
        self._disk_vectors = {}
        gc.collect()

    def _load_disk_store(self):
        self._close_disk_vectors()
        with self.disk_manifest_path.open("rb") as f:
            manifest = pickle.load(f)

        self._disk_lookup = {e_type: {} for e_type in self.VECTOR_TYPES}
        self._disk_row_keys = {e_type: [] for e_type in self.VECTOR_TYPES}
        self._disk_vectors = {}
        self._metadata_lookup = manifest.get("metadata", {}) or {}
        self._storage_mode = "disk"

        for e_type in self.VECTOR_TYPES:
            bucket_info = manifest.get("buckets", {}).get(e_type, {})
            self._disk_lookup[e_type] = bucket_info.get("lookup", {}) or {}
            self._disk_row_keys[e_type] = bucket_info.get("keys", []) or []
            vector_path = self.disk_store_dir / bucket_info.get("file_name", f"{e_type}.npy")
            self._disk_vectors[e_type] = np.load(vector_path, mmap_mode="r")

    def _materialize_full_storage(self):
        data = {"text": {}, "visual": {}, "multi": {}, "metadata": dict(self._metadata_lookup)}
        if self._storage_mode == "disk":
            for e_type in self.VECTOR_TYPES:
                vectors = self._disk_vectors.get(e_type)
                keys = self._disk_row_keys.get(e_type, [])
                if vectors is None:
                    continue
                for row_index, key in enumerate(keys):
                    data[e_type][key] = np.asarray(vectors[row_index], dtype=self.vector_dtype).tolist()
        else:
            for e_type in self.VECTOR_TYPES:
                data[e_type].update(self.embeddings.get(e_type, {}))
            data["metadata"].update(self.embeddings.get("metadata", {}))

        for e_type in self.VECTOR_TYPES:
            for key, vector in self.embeddings.get(e_type, {}).items():
                data[e_type][key] = np.asarray(vector, dtype=self.vector_dtype).tolist()
        data["metadata"].update(self.embeddings.get("metadata", {}))
        return data

    def _resolve_disk_row(
        self,
        e_type: str,
        text: str = None,
        image_paths_or_urls: list = None,
        storage_key=None,
    ):
        lookup = self._disk_lookup.get(e_type, {})
        if not lookup:
            return None

        normalized_storage_key = self._normalize_storage_key(storage_key)
        if normalized_storage_key and normalized_storage_key in lookup:
            return lookup[normalized_storage_key]

        c_hash = self.get_content_hash(text, image_paths_or_urls)
        if c_hash in lookup:
            return lookup[c_hash]

        normalized_text = self._normalize_storage_key(text)
        if normalized_text and normalized_text in lookup:
            return lookup[normalized_text]

        return None

    def resolve_cached_reference(
        self,
        e_type: str,
        text: str = None,
        image_paths_or_urls: list = None,
        storage_key=None,
    ):
        bucket = self.embeddings.get(e_type, {})
        c_hash = self.get_content_hash(text, image_paths_or_urls)
        if c_hash in bucket:
            return {"source": "runtime", "e_type": e_type, "key": c_hash}

        normalized_storage_key = self._normalize_storage_key(storage_key)
        if normalized_storage_key and normalized_storage_key in bucket:
            return {"source": "runtime", "e_type": e_type, "key": normalized_storage_key}

        normalized_text = self._normalize_storage_key(text)
        if normalized_text and normalized_text in bucket:
            return {"source": "runtime", "e_type": e_type, "key": normalized_text}

        row_index = self._resolve_disk_row(
            e_type,
            text=text,
            image_paths_or_urls=image_paths_or_urls,
            storage_key=storage_key,
        )
        if row_index is None:
            return None
        return {"source": "disk", "e_type": e_type, "row_index": row_index}

    def get_vector_from_reference(self, ref):
        if not ref:
            return None
        if ref.get("source") == "runtime":
            return self.embeddings.get(ref.get("e_type"), {}).get(ref.get("key"))
        if ref.get("source") == "disk":
            vectors = self._disk_vectors.get(ref.get("e_type"))
            row_index = ref.get("row_index")
            if vectors is None or row_index is None:
                return None
            return vectors[row_index]
        return None

    def get_vectors_from_references(self, refs, dtype=np.float64):
        vectors = []
        for ref in refs:
            vec = self.get_vector_from_reference(ref)
            if vec is None:
                continue
            vectors.append(np.asarray(vec, dtype=dtype))
        if not vectors:
            return np.zeros((0, 0), dtype=dtype)
        return np.asarray(vectors, dtype=dtype)

    def get_storage_mode(self):
        return self._storage_mode

    def get_storage_counts(self):
        if self._storage_mode == "disk":
            return {e_type: len(self._disk_row_keys.get(e_type, [])) for e_type in self.VECTOR_TYPES}
        return {e_type: len(self.embeddings.get(e_type, {})) for e_type in self.VECTOR_TYPES}

    def _cache_lookup(self, e_type: str, text: str = None, image_paths_or_urls: list = None):
        ref = self.resolve_cached_reference(
            e_type,
            text=text,
            image_paths_or_urls=image_paths_or_urls,
        )
        return self.get_vector_from_reference(ref)

    def _extract_frame(self, video_path):
        try:
            import cv2

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None

            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_count // 2)
            ret, frame = cap.read()
            cap.release()

            if ret:
                tf = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                cv2.imwrite(tf.name, frame)
                return tf.name
        except Exception as e:
            print(f"    ?좑툘 Frame extraction failed: {e}")
        return None

    def _upload_media(self, path_or_url):
        if path_or_url in self._file_cache:
            return self._file_cache[path_or_url]

        target_path = path_or_url
        is_temp = False

        if str(path_or_url).startswith("http"):
            try:
                response = requests.get(path_or_url, timeout=15)
                if response.status_code == 200:
                    ct = response.headers.get("Content-Type", "").lower()
                    if "video" in ct or "mp4" in ct or "quicktime" in ct:
                        suffix = ".mp4"
                    elif "png" in ct:
                        suffix = ".png"
                    elif "webp" in ct:
                        suffix = ".webp"
                    else:
                        suffix = ".jpg"

                    tf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                    tf.write(response.content)
                    tf.close()
                    target_path = tf.name
                    is_temp = True
                else:
                    return None
            except Exception as e:
                print(f"    ?좑툘 Download fail: {e}")
                return None

        try:
            if not os.path.exists(target_path):
                return None

            import mimetypes

            m_type, _ = mimetypes.guess_type(target_path)
            actual_upload_path = target_path

            if m_type and m_type.startswith("video/"):
                extracted_path = self._extract_frame(target_path)
                if extracted_path:
                    actual_upload_path = extracted_path
                else:
                    return None

            with open(actual_upload_path, "rb") as f:
                img_data = f.read()

            if actual_upload_path != path_or_url and os.path.exists(actual_upload_path):
                try:
                    os.remove(actual_upload_path)
                except Exception:
                    pass

            return img_data, "image/jpeg"
        except Exception as e:
            print(f"    ?좑툘 File API Upload Error: {e}")
            return None
        finally:
            if is_temp and os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except Exception:
                    pass

    def _prepare_parts(self, text=None, image_paths_or_urls=None):
        parts = []
        if text:
            parts.append(text)

        if image_paths_or_urls:
            if isinstance(image_paths_or_urls, str):
                image_paths_or_urls = [image_paths_or_urls]

            if image_paths_or_urls:
                target_one = image_paths_or_urls[0]
                res = self._upload_media(target_one)
                if res:
                    data, m_type = res
                    parts.append(types.Part.from_bytes(data=data, mime_type=m_type))

        return parts

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retriable),
        reraise=True,
    )
    def get_multimodal_embedding(
        self,
        text=None,
        image_paths_or_urls=None,
        task_type="RETRIEVAL_DOCUMENT",
        use_cache=True,
        only_cache=False,
        persist=True,
    ):
        if not text and not image_paths_or_urls:
            return None

        c_hash = self.get_content_hash(text, image_paths_or_urls)
        if text and image_paths_or_urls:
            e_type = "multi"
        elif image_paths_or_urls:
            e_type = "visual"
        else:
            e_type = "text"

        if use_cache:
            cached = self._cache_lookup(e_type, text, image_paths_or_urls)
            if cached is not None:
                return cached

        if only_cache:
            return None

        parts = self._prepare_parts(text, image_paths_or_urls)
        if not parts:
            return None

        try:
            clean_parts = []
            only_text_part = None
            for part in parts:
                if isinstance(part, str):
                    stripped = part.strip()
                    clean_parts.append(stripped)
                    only_text_part = stripped
                else:
                    clean_parts.append(part)

            try:
                result = self.client.models.embed_content(model=self.model_id, contents=clean_parts)
            except Exception as inner_e:
                if "400" in str(inner_e) or "INVALID_ARGUMENT" in str(inner_e):
                    if only_text_part:
                        print("    ?좑툘  Multimodal Embedding 400 Error. Falling back to Text-Only...")
                        result = self.client.models.embed_content(
                            model=self.model_id,
                            contents=only_text_part,
                        )
                    else:
                        raise inner_e
                else:
                    raise inner_e

            vector = result.embeddings[0].values
            if use_cache and persist:
                self.embeddings.setdefault(e_type, {})
                self.embeddings[e_type][c_hash] = vector
            return vector
        except Exception as e:
            print(f"    ??Embedding API Error: {e}")
            return None

    def get_text_embedding(
        self,
        text,
        task_type="RETRIEVAL_DOCUMENT",
        use_cache=True,
        only_cache=False,
        persist=True,
    ):
        return self.get_multimodal_embedding(
            text=text,
            task_type=task_type,
            use_cache=use_cache,
            only_cache=only_cache,
            persist=persist,
        )

    def get_visual_embedding(
        self,
        image_paths_or_urls,
        task_type="RETRIEVAL_DOCUMENT",
        use_cache=True,
        only_cache=False,
        persist=True,
    ):
        return self.get_multimodal_embedding(
            image_paths_or_urls=image_paths_or_urls,
            task_type=task_type,
            use_cache=use_cache,
            only_cache=only_cache,
            persist=persist,
        )

    def get_many_text_embeddings(self, texts, task_type="RETRIEVAL_DOCUMENT"):
        results = []
        for text in texts:
            results.append(self.get_text_embedding(text, task_type=task_type))
        self.save_storage()
        return results

    def get_embeddings_matrix(self, texts):
        vectors = self.get_many_text_embeddings(texts)
        valid_vectors = [vector for vector in vectors if vector is not None]
        if not valid_vectors:
            return np.zeros((0, 3072))
        return np.array(valid_vectors)
