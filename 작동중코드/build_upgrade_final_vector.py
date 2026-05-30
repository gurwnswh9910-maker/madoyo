import argparse
import json
import pickle
import shutil
from pathlib import Path

import numpy as np


ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT_DIR / "upgrade_final_vector" / "embeddings_upgrade_final.pkl"
SUMMARY_PATH = ROOT_DIR / "upgrade_final_vector" / "embeddings_upgrade_final.summary.json"
SOURCE_VECTOR_DIR = ROOT_DIR / "upgrade_final_vector" / "source_vectors"
VECTOR_TYPES = ("text", "visual", "multi")

SOURCES = [
    {
        "label": "final_overlay113",
        "category": "final",
        "path": SOURCE_VECTOR_DIR / "embeddings_v2_final_20260522_overlay113.pkl",
    },
    {
        "label": "final_consolidated_master_visual_fill",
        "category": "final",
        "path": ROOT_DIR / "embedding_migration" / "final_consolidated_master.pkl",
    },
    {
        "label": "working_final",
        "category": "final",
        "path": ROOT_DIR / "작동중코드" / "embeddings_v2_final.pkl",
    },
    {
        "label": "external_excel_not_in_pkl_1930",
        "category": "external",
        "path": SOURCE_VECTOR_DIR / "excel_not_in_pkl_1930.pkl",
    },
    {
        "label": "external_original_update_113",
        "category": "external",
        "path": SOURCE_VECTOR_DIR / "original_update_113_candidate.pkl",
    },
    {
        "label": "external_review_0404",
        "category": "external",
        "path": ROOT_DIR / "연구소" / "embeddings_review_0404.pkl",
    },
    {
        "label": "my_account_combined_ml_1083",
        "category": "my_account",
        "path": SOURCE_VECTOR_DIR / "my_accounts_ml_1083.pkl",
    },
    {
        "label": "my_account_0430_0112_text",
        "category": "my_account",
        "path": SOURCE_VECTOR_DIR / "threads_slow_report_0430_0112_text_embeddings_20260501.pkl",
    },
    {
        "label": "my_account_0430_1258_text",
        "category": "my_account",
        "path": SOURCE_VECTOR_DIR / "threads_slow_report_0430_1258_text_embeddings_20260501.pkl",
    },
    {
        "label": "my_account_0430_1724_text",
        "category": "my_account",
        "path": SOURCE_VECTOR_DIR / "threads_slow_report_0430_1724_text_embeddings_20260501.pkl",
    },
    {
        "label": "my_account_0322_0416",
        "category": "my_account",
        "path": ROOT_DIR / "연구소" / "threads_live_report_0322_0416_embeddings_v2_final.pkl",
    },
    {
        "label": "my_account_0415_0055",
        "category": "my_account",
        "path": ROOT_DIR / "연구소" / "threads_live_report_0415_0055_embeddings_v2_final.pkl",
    },
    {
        "label": "my_account_0416_0333",
        "category": "my_account",
        "path": ROOT_DIR / "연구소" / "threads_live_report_0416_0333_embeddings_v2_final.pkl",
    },
    {
        "label": "my_account_0417_0123",
        "category": "my_account",
        "path": ROOT_DIR / "연구소" / "threads_live_report_0417_0123_embeddings_v2_final.pkl",
    },
]


def normalize_key(value):
    if value is None:
        return None
    key = str(value).strip()
    return key or None


def empty_store():
    return {"text": {}, "visual": {}, "multi": {}, "metadata": {}}


def load_store(path):
    with path.open("rb") as f:
        data = pickle.load(f)
    if isinstance(data, dict) and any(bucket in data for bucket in VECTOR_TYPES):
        return data
    return {"text": {}, "visual": {}, "multi": data if isinstance(data, dict) else {}, "metadata": {}}


def merge_metadata(existing, incoming, source):
    if isinstance(existing, dict):
        merged = dict(existing)
    elif existing is None:
        merged = {}
    else:
        merged = {"value": existing}

    if isinstance(incoming, dict):
        for key, value in incoming.items():
            if key not in merged or merged.get(key) in (None, "", [], {}):
                merged[key] = value
    elif incoming is not None and "value" not in merged:
        merged["value"] = incoming

    sources = list(merged.get("_upgrade_sources", []))
    if source["label"] not in sources:
        sources.append(source["label"])
    merged["_upgrade_sources"] = sources
    merged.setdefault("_upgrade_category", source["category"])
    return merged


def merge_source(target, source):
    path = source["path"]
    if not path.exists():
        raise FileNotFoundError(path)

    data = load_store(path)
    source_summary = {
        "label": source["label"],
        "category": source["category"],
        "path": str(path.relative_to(ROOT_DIR)),
        "added": {},
        "duplicates": {},
        "input_counts": {},
    }

    for bucket in VECTOR_TYPES:
        source_bucket = data.get(bucket, {}) if isinstance(data, dict) else {}
        source_summary["input_counts"][bucket] = len(source_bucket) if isinstance(source_bucket, dict) else 0
        source_summary["added"][bucket] = 0
        source_summary["duplicates"][bucket] = 0
        if not isinstance(source_bucket, dict):
            continue

        for raw_key, vector in source_bucket.items():
            key = normalize_key(raw_key)
            if not key:
                continue
            if key in target[bucket]:
                source_summary["duplicates"][bucket] += 1
                continue
            target[bucket][key] = vector
            source_summary["added"][bucket] += 1

    metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
    source_summary["input_counts"]["metadata"] = len(metadata) if isinstance(metadata, dict) else 0
    source_summary["added"]["metadata"] = 0
    source_summary["duplicates"]["metadata"] = 0
    if isinstance(metadata, dict):
        for raw_key, meta in metadata.items():
            key = normalize_key(raw_key)
            if not key:
                continue
            existed = key in target["metadata"]
            target["metadata"][key] = merge_metadata(target["metadata"].get(key), meta, source)
            if existed:
                source_summary["duplicates"]["metadata"] += 1
            else:
                source_summary["added"]["metadata"] += 1

    for bucket in VECTOR_TYPES:
        for key in target[bucket].keys():
            if key not in target["metadata"]:
                target["metadata"][key] = merge_metadata(None, None, source)

    return source_summary


def build_disk_store(data, output_path):
    disk_dir = output_path.parent / f"{output_path.stem}_diskstore"
    temp_dir = output_path.parent / f"{output_path.stem}_diskstore.tmp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "version": 1,
        "source_path": str(output_path),
        "source_size": output_path.stat().st_size,
        "source_mtime_ns": output_path.stat().st_mtime_ns,
        "dtype": "float64",
        "vector_types": list(VECTOR_TYPES),
        "buckets": {},
        "metadata": data.get("metadata", {}),
    }

    for bucket in VECTOR_TYPES:
        vectors = data.get(bucket, {})
        keys = list(vectors.keys())
        dim = 0
        if keys:
            first = np.asarray(vectors[keys[0]], dtype=np.float64)
            dim = int(first.shape[0]) if first.ndim > 0 else 0

        vector_path = temp_dir / f"{bucket}.npy"
        mmap = np.lib.format.open_memmap(
            vector_path,
            mode="w+",
            dtype=np.float64,
            shape=(len(keys), dim),
        )
        for row_index, key in enumerate(keys):
            mmap[row_index] = np.asarray(vectors[key], dtype=np.float64)
        mmap.flush()
        del mmap

        manifest["buckets"][bucket] = {
            "count": len(keys),
            "dim": dim,
            "keys": keys,
            "lookup": {key: row_index for row_index, key in enumerate(keys)},
            "file_name": vector_path.name,
        }

    with (temp_dir / "manifest.pkl").open("wb") as f:
        pickle.dump(manifest, f, protocol=pickle.HIGHEST_PROTOCOL)

    if disk_dir.exists():
        shutil.rmtree(disk_dir)
    temp_dir.replace(disk_dir)


def build(output_path=OUTPUT_PATH, summary_path=SUMMARY_PATH, write_disk_store=True):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = empty_store()
    source_summaries = []

    for source in SOURCES:
        print(f"[merge] {source['label']} <- {source['path'].relative_to(ROOT_DIR)}", flush=True)
        source_summaries.append(merge_source(data, source))

    with output_path.open("wb") as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

    if write_disk_store:
        print("[diskstore] building local disk-backed store", flush=True)
        build_disk_store(data, output_path)

    summary = {
        "output": str(output_path.relative_to(ROOT_DIR)),
        "counts": {bucket: len(data[bucket]) for bucket in ("text", "visual", "multi", "metadata")},
        "sources": source_summaries,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary["counts"], ensure_ascii=False), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-diskstore", action="store_true")
    args = parser.parse_args()
    build(write_disk_store=not args.no_diskstore)


if __name__ == "__main__":
    main()
