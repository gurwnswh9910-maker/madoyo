import sys
import os
import io
import re
import time
from difflib import SequenceMatcher
import numpy as np
import pandas as pd
from scipy.stats import rankdata

# UTF-8 출력 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

# 현재 파일 디렉토리를 경로에 추가하여 로컬 모듈(app_config 등) 임포트 보장
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from concurrent.futures import ThreadPoolExecutor
from app_config import (
    GlobalConfig, GEMINI_API_KEY, MODEL_NAME, MAX_WORKERS, BASE_PATH, 
    ORIGINAL_COPY, PRODUCT_FOCUS, STATIC_STRATEGIES
)

from data_feedback_loop_v2 import MSSDataIntegrator
from copy_scorer_soft_ensemble import CopyScorerSoftEnsemble
from copy_generator_v2 import DynamicCopyGenerator
from contrastive_prompter import ContrastivePrompter

SIBLING_COPY_COUNT = 3
DUPLICATE_SIMILARITY_THRESHOLD = 0.985
RETRIEVAL_SIMILARITY_CHUNK_SIZE = max(64, int(os.getenv("MADOYO_RETRIEVAL_CHUNK_SIZE", "256")))
REPEATED_CHAR_PATTERN = re.compile(r"([^\s])\1{5,}")

def is_korean(text):
    if not isinstance(text, str): return False
    kor_count = len(re.findall('[가-힣]', text))
    return (kor_count / max(len(text), 1)) > 0.3

def clean_marketing_text(text):
    """마케팅 카피에 불필요한 페이지 표시, 번역기 문구 등을 제거합니다."""
    if not text: return ""
    text = re.sub(r'\d+\s*[/\n\\]\s*\d+', '', text).strip()
    noises = ['See translation', 'See original']
    for n in noises:
        text = text.replace(n, '')
    return text.strip()

def get_copy_hygiene_rejection(text):
    """명백한 생성 붕괴 후보를 채점 전에 제외합니다."""
    text = text or ""
    repeated = REPEATED_CHAR_PATTERN.search(text)
    if repeated:
        return {
            "reason": "same_char_repeat_6",
            "repeat_char": repeated.group(1),
            "repeat_len": len(repeated.group(0)),
            "repeat_index": repeated.start(),
            "repeat_preview": repeated.group(0)[:12],
        }

    return None

def get_block(text, start_key, end_key=None):
    if start_key not in text: return None
    start_idx = text.find(start_key) + len(start_key)
    if end_key and end_key in text[start_idx:]:
        end_idx = text.find(end_key, start_idx)
        return text[start_idx:end_idx].strip()
    return text[start_idx:].strip()

def extract_fields(block):
    if not block: return None
    lines = block.split('\n')
    name, desc = "동적 전략", ""
    for line in lines:
        if '명칭' in line or '이름' in line:
            name = line.split(':')[-1].strip().strip('* ')
        elif '설명' in line or '내용' in line:
            desc = line.split(':')[-1].strip().strip('* ')
    if not desc: desc = block
    return name, desc

def extract_tag_block(text, tag):
    marker = f"[{tag}]"
    if marker not in text:
        return None
    start_idx = text.find(marker) + len(marker)
    end_idx = text.find("[", start_idx)
    if end_idx == -1:
        return text[start_idx:].strip()
    return text[start_idx:end_idx].strip()

def normalize_copy_for_similarity(text):
    text = clean_marketing_text(text or "")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"([!?~])\1+", r"\1", text)
    text = re.sub(r"^[^\w가-힣]+|[^\w가-힣]+$", "", text)
    return text.strip()

def normalize_similarity_text(text):
    text = clean_marketing_text(text or "")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"([!?~])\1+", r"\1", text)
    text = re.sub(r"^[^\w]+|[^\w]+$", "", text)
    return text.strip()

def character_similarity(text_a, text_b):
    normalized_a = normalize_similarity_text(text_a)
    normalized_b = normalize_similarity_text(text_b)
    if not normalized_a or not normalized_b:
        return 0.0
    if normalized_a == normalized_b:
        return 1.0
    return SequenceMatcher(None, normalized_a, normalized_b).ratio()

def candidate_variant_suffix(index):
    if 0 <= index < 26:
        return chr(ord("A") + index)
    return str(index + 1)

def build_candidate_cache_key(text, image_ref=None):
    image_key = str(image_ref or "")
    return f"{image_key}::{normalize_similarity_text(text)}"

def generate_single_task(client, model, task):
    cid = task['cid']
    prompt = task['prompt']
    strat_label = task['strat_label']
    t_gen = time.time()
    try:
        for attempt in range(2):
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                gen_time = time.time() - t_gen
                raw_text = response.text.strip()
                
                # 가이드 태그 기반 파싱 로직
                copies = []
                
                for tag in [f"FINAL_COPY_{i}" for i in range(1, SIBLING_COPY_COUNT + 1)]:
                    tagged_copy = extract_tag_block(raw_text, tag)
                    if tagged_copy:
                        copies.append(tagged_copy)

                if not copies:
                    draft = extract_tag_block(raw_text, "DRAFT_COPY")
                    final = extract_tag_block(raw_text, "FINAL_COPY")
                    if draft: copies.append(draft)
                    if final: copies.append(final)
                
                # 에러헨들링: 태그가 없으면 전체 텍스트를 하나로 처리
                if not copies:
                    clean_text = re.sub(r'^[`"\'\s]+|[`"\'\s]+$', '', raw_text)
                    clean_text = re.sub(r'^```.*?\n|```$', '', clean_text, flags=re.MULTILINE).strip()
                    copies = [clean_text]
                
                return {"success": True, "cid": cid, "copies": copies, "strategy": strat_label, "time": gen_time}
            except Exception as e:
                if "429" in str(e) and attempt == 0:
                    time.sleep(10)
                    continue
                raise e
    except Exception as e:
        return {"success": False, "cid": cid, "error": str(e)}

def extract_dynamic_all(client, model, product_info, pairs, static_strats=None):
    # 정적 전략 컨텍스트
    static_context = ""
    if static_strats:
        static_context = "\n[참고: 우리가 평소 사용하는 성공 공식(정적 전략)]\n"
        for i, (name, desc) in enumerate(static_strats, 1):
            static_context += f"{i}. {name}: {desc}\n"

    # 대조용 데이터를 프롬프트에 삽입
    pairs_context = ""
    if pairs:
        pairs_context = "\n[실제 데이터: 고성과 vs 저성과 게시물 Pair]\n"
        for i, p in enumerate(pairs, 1):
            h_preview = str(p.get('high_text', '')).replace('\n', ' / ')[:150]
            l_preview = str(p.get('low_text', '')).replace('\n', ' / ')[:150]
            pairs_context += f"\n쌍 {i}:\n"
            pairs_context += f"  🟢 HIGH (MSS {p.get('high_mss', 0):.0f}): {h_preview}\n"
            pairs_context += f"  🔴 LOW  (MSS {p.get('low_mss', 0):.0f}): {l_preview}\n"

    # ### [PROMPT_LOCATION: STRATEGY_EXTRACTION] ###
    prompt = f"""당신은 10년차 탑 바이럴 마케터입니다.
아래는 '{product_info}'와 유사한 카테고리에서 작성된 {len(pairs)}개의 고성과/저성과 게시물 쌍(Pair)입니다. 

{pairs_context}
{static_context}

이 예시 데이터와 성공 공식을 분석하여, 오늘 우리가 카피를 쓸 때 적용할 '서로 다른 접근 방식의 강력한 전술(전략)' 3가지와, 모든 전략에서 공통으로 피해야 할 '실패 패턴' 1가지를 추출하세요.

형식:
[동적 전략 A]
- 명칭: (예: 일상 반전 서사형)
- 설명: (데이터의 특징을 철저히 분석하여 도출한 구조 2~3문장)

[동적 전략 B]
- 명칭: (예: 제3자 관찰 증언형)
- 설명: (전략 A와는 완전히 다른 각도의 데이터 기반 접근법 2~3문장)

[하이브리드 전략 C]
- 명칭: (예: 성공 공식 결합형)
- 설명: (실시간 데이터의 특징과 제공된 '성공 공식' 중 하나를 영리하게 결합한 전술 2~3문장)

[최우선 금기 사항]
- 내용: (저성과 게시물들의 공통 실패 원인을 분석하여, 이번 카피에서 절대 하지 말아야 할 1~2가지)
"""
    try:
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text.strip()
    except Exception as e:
        print(f"    ⚠️ 동적 전략 추출 실패: {e}")
        return None

def run_optimization(original_copy: str, product_focus, input_image_urls: list = None,
                       api_key: str = None, model_name: str = None, base_path: str = None,
                       shared_resources: dict = None, return_metadata: bool = False,
                       raw_candidate_collector: list | None = None,
                       generator_version: str = "upgrade_v10"):
    import concurrent.futures
    from google import genai
    from embedding_utils import EmbeddingManager
    from mab_engine_v2 import DynamicMAB
    
    _api_key = api_key or GlobalConfig.GEMINI_API_KEY
    _model = model_name or GlobalConfig.MODEL_NAME
    _base_path = base_path or str(GlobalConfig.BASE_DIR)
    if shared_resources is None:
        shared_resources = {}
    client = shared_resources.get("genai_client")
    if not client:
        client = genai.Client(api_key=_api_key)
        shared_resources["genai_client"] = client
    MODEL = _model

    print("=" * 80)
    print("MAB 하이브리드 최적화 시스템 v4.1 (Hybrid Retrieval)")
    print(f"Mode: {'multimodal' if input_image_urls else 'text-only'}")
    print("=" * 80)
    
    t_start = time.time()
    gen_times = []
    duplicate_rejections = []
    duplicate_pool = []
    candidate_count_before_filter = 1
    rerank_reused_embedding_count = 0
    embedding_session_stats = {"hits": 0, "misses": 0}
    candidate_embedding_cache = {}
    generation_stats = {
        "static_strategy_count": 0,
        "dynamic_strategy_count": 0,
        "static_generation_task_count": 0,
        "dynamic_generation_task_count": 0,
        "scheduled_generation_tasks": 0,
        "completed_generation_tasks": 0,
        "successful_generation_tasks": 0,
        "failed_generation_tasks": 0,
        "expected_generated_copy_count": 0,
        "returned_generated_copy_count": 0,
        "accepted_generated_copy_count": 0,
        "hygiene_rejection_count": 0,
        "hygiene_rejections": [],
        "undersized_generation_tasks": 0,
        "undersized_generation_details": [],
        "generation_failures": [],
    }
    target_img = input_image_urls[0] if input_image_urls else None

    def get_candidate_embedding(text):
        cache_key = build_candidate_cache_key(text, target_img)
        if cache_key in candidate_embedding_cache:
            embedding_session_stats["hits"] += 1
            return candidate_embedding_cache[cache_key]

        embedding_session_stats["misses"] += 1
        if target_img:
            vec = emb_mgr.get_multimodal_embedding(text=text, image_paths_or_urls=[target_img], persist=False)
        else:
            vec = emb_mgr.get_text_embedding(text, persist=False)
        candidate_embedding_cache[cache_key] = vec
        return vec

    # shared_resources is initialized above.
    
    # 1-1. Integrator 및 데이터 로드
    integrator = shared_resources.get('integrator')
    if not integrator:
        integrator = MSSDataIntegrator(_base_path)
        shared_resources['integrator'] = integrator
        
    korean_data = shared_resources.get('korean_data')
    if korean_data is None:
        all_data = integrator.process_all_data(DynamicMAB())
        # '본문' 컬럼 사용 (data_feedback_loop_v2에서 보장됨)
        korean_data = all_data[all_data['본문'].apply(is_korean)].drop_duplicates(subset='본문').copy()
        shared_resources['korean_data'] = korean_data
        
    # 1-2. EmbeddingManager 로드
    emb_mgr = shared_resources.get('emb_mgr')
    if not emb_mgr:
        pkl_full_path = os.path.join(_base_path, '작동중코드', 'embeddings_v2_final.pkl')
        if not os.path.exists(pkl_full_path):
            pkl_full_path = os.path.join(_base_path, 'embeddings_v2_final.pkl')
        emb_mgr = EmbeddingManager(storage_path=pkl_full_path)
        shared_resources['emb_mgr'] = emb_mgr
    
    # 2. 하이브리드 회수 (Retrieval)
    print(f"\n2. 데이터 회수 및 컨텍스트 분석 시작...")
    
    filtered_subset = pd.DataFrame()
    query_vec = None
    
    if original_copy and input_image_urls:
        print(f"   🎯 [Case 3] 2D Alpha Score (Multi) 회수 중.. (Sim 30% : MSS 70%)")
        query_vec = emb_mgr.get_multimodal_embedding(text=original_copy, image_paths_or_urls=input_image_urls)
    elif input_image_urls:
        print(f"   🎯 [Case 2] 2D Alpha Score (Visual) 회수 중.. (Sim 30% : MSS 70%)")
        query_vec = emb_mgr.get_visual_embedding(input_image_urls)
    else:
        print(f"   🎯 [Case 1] 2D Alpha Score (Text) 회수 중.. (Sim 30% : MSS 70%)")
        query_vec = emb_mgr.get_text_embedding(original_copy)

    valid_indices = []
    vector_refs = []
    mss_values = []
    
    for idx, row in korean_data.iterrows():
        text = str(row.get('본문', '')).strip()
        link_key = str(row['링크']).strip() if '링크' in row and pd.notna(row['링크']) else ''
        
        ref = emb_mgr.resolve_cached_reference('text', text=text, storage_key=link_key)
        if ref is None:
            ref = emb_mgr.resolve_cached_reference('multi', text=text, storage_key=link_key)
        if ref is None:
            ref = emb_mgr.resolve_cached_reference('visual', text=text, storage_key=link_key)

        if ref is not None:
            valid_indices.append(idx)
            vector_refs.append(ref)
            mss_values.append(row['MSS'])

    if valid_indices and query_vec is not None:
        query_arr = np.asarray(query_vec, dtype=np.float64)
        mss_arr = np.asarray(mss_values, dtype=np.float64)
        if query_arr.ndim == 1 and query_arr.size > 0:
            sims = np.zeros(len(vector_refs), dtype=np.float64)
            query_norm = np.linalg.norm(query_arr) + 1e-10
            for start in range(0, len(vector_refs), RETRIEVAL_SIMILARITY_CHUNK_SIZE):
                chunk_refs = vector_refs[start:start + RETRIEVAL_SIMILARITY_CHUNK_SIZE]
                arr = emb_mgr.get_vectors_from_references(chunk_refs, dtype=np.float64)
                if arr.size == 0 or arr.ndim != 2 or arr.shape[1] != query_arr.shape[0]:
                    continue
                arr_norm = np.linalg.norm(arr, axis=1) + 1e-10
                sims[start:start + len(chunk_refs)] = np.dot(arr, query_arr) / (arr_norm * query_norm)
            sims_pct = rankdata(sims) / len(sims) * 100
            mss_pct = rankdata(mss_arr) / len(mss_arr) * 100
            alpha_scores = (sims_pct * 0.3) + (mss_pct * 0.7)
            top_k = min(100, len(alpha_scores))
            top_k_indices = np.argsort(alpha_scores)[-top_k:][::-1]
            idx_list = [valid_indices[i] for i in top_k_indices]
            
            filtered_subset = korean_data.loc[idx_list].copy()
            filtered_subset['alpha_score'] = [alpha_scores[i] for i in top_k_indices]
            
            print(f"   ✅ [Alpha Score Sort] {len(filtered_subset)}개 최적화 데이터 확보 완료 (최고점: {filtered_subset.iloc[0]['alpha_score']:.1f})")
            
            print(f"\n   [회수된 상위 10개 원본 데이터 목록]")
            print(f"   {'No':<3} | {'MSS':<5} | {'Alpha':<6} | {'본문 미리보기'}")
            print(f"   {'-'*65}")
            for i, (_, row) in enumerate(filtered_subset.head(10).iterrows(), 1):
                preview = str(row['본문']).replace('\n', ' ')[:45]
                print(f"   {i:<3} | {row['MSS']:<5.1f} | {row['alpha_score']:<6.1f} | {preview}...")
            print(f"   {'-'*65}\n")

    if filtered_subset is None or filtered_subset.empty:
        print(f"   ⚠️ 회수된 데이터가 없어 전체 데이터 중 고성과 10개를 사용합니다.")
        filtered_subset = korean_data.nlargest(10, 'MSS')

    best_similar_posts = filtered_subset.head(10)
    top_examples_for_gen = best_similar_posts[['본문', 'MSS']].to_dict('records')
    generator = DynamicCopyGenerator(top_examples_for_gen, prompt_version=generator_version)
    generation_stats["repeated_char_hard_limit"] = 6
    print("   ✅ 카피 위생 하드컷: 같은 글자 6회 반복 제외")
    contrastive = ContrastivePrompter(embedding_manager=emb_mgr, all_data=korean_data)
    
    # 3. MAB Prior Injection
    print("\n3. MAB 사전 지식(Contextual Prior) 주입 중..")
    mab = DynamicMAB()
    for s_name, _ in STATIC_STRATEGIES:
        mab.add_arm(s_name)
    
    context_weights = {s_name: 1.0 for s_name, _ in STATIC_STRATEGIES}
    if 'arm_name' in filtered_subset.columns:
        top_arms = best_similar_posts['arm_name'].value_counts()
        for arm, count in top_arms.items():
            if arm in context_weights:
                context_weights[arm] += (count * 0.5) 
    
    # 4. 전략 추출 및 카피 생성
    print("\n4. 전략 추출 및 카피 생성...")
    scorer = shared_resources.get('scorer')
    if not scorer:
        scorer = CopyScorerSoftEnsemble()
        shared_resources['scorer'] = scorer
    
    orig_vec = emb_mgr.get_multimodal_embedding(text=original_copy, image_paths_or_urls=input_image_urls) if input_image_urls else emb_mgr.get_text_embedding(original_copy)
    if orig_vec is None:
        print("    ⚠️ 원본 카피 임베딩 실패. 0번 기본값으로 진행합니다.")
        orig_vec = np.zeros(3072)
    orig_scores = scorer.score_candidates(np.array([orig_vec]), candidate_texts=[original_copy])
    
    if not orig_scores:
        orig_score_data = {
            'index': 0, 'reg_score': 0.0, 'hurdle_prob': 0.0, 
            'pass_hurdle': False, 'league_wins': 0, 'total_score': 0.0
        }
    else:
        orig_score_data = orig_scores[0]

    orig_rerank_embedding = get_candidate_embedding(original_copy) if original_copy else None

    scored = [{
        "success": True, 
        "cid": "Original", 
        "copy": original_copy, 
        "score_data": orig_score_data,
        "total_score": orig_score_data.get('total_score', 0.0),
        "rerank_embedding": orig_rerank_embedding
    }]
    duplicate_pool.append({
        "cid": "Original",
        "copy": original_copy,
    })
    
    contrastive_restricted = ContrastivePrompter(embedding_manager=emb_mgr, all_data=filtered_subset)
    
    dynamic_pairs = []
    for _, row in best_similar_posts.head(5).iterrows():
        low_text, low_mss = contrastive_restricted._find_dynamic_contrastive_pair(row['본문'], row['MSS'])
        if low_text:
            dynamic_pairs.append({'high_text': row['본문'], 'high_mss': row['MSS'], 'low_text': low_text, 'low_mss': low_mss})

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        strat_future = executor.submit(extract_dynamic_all, client, MODEL, product_focus, dynamic_pairs, STATIC_STRATEGIES)
        
        prioritized_static = []
        for _ in range(len(STATIC_STRATEGIES)):
            selected = mab.select_arm(context_weights=context_weights)
            if selected and selected not in [p[0] for p in prioritized_static]:
                desc = next(d for n, d in STATIC_STRATEGIES if n == selected)
                prioritized_static.append((selected, desc))
        
        generation_futures = {}
        
        def push_tasks(strat_list, start_idx_offset=0, task_group="static"):
            generation_stats[f"{task_group}_strategy_count"] += len(strat_list)
            for s_idx, (name, desc) in enumerate(strat_list):
                num = 4 if task_group == "dynamic" else 2
                for v_idx in range(num):
                    cid = f"DYN_{s_idx}_{v_idx}" if num > 2 else f"S_{s_idx+start_idx_offset}_{v_idx}"
                    prompt = generator.generate_prompt(
                        product_info=product_focus, strategy_name=name, strategy_desc=desc,
                        original_copy=original_copy, variation_idx=v_idx+1,
                        sibling_count=SIBLING_COPY_COUNT
                    )
                    task = {"cid": cid, "prompt": prompt, "strat_label": name}
                    fut = executor.submit(generate_single_task, client, MODEL, task)
                    generation_futures[fut] = task
                    generation_stats["scheduled_generation_tasks"] += 1
                    generation_stats[f"{task_group}_generation_task_count"] += 1
                    generation_stats["expected_generated_copy_count"] += SIBLING_COPY_COUNT

        push_tasks(prioritized_static, start_idx_offset=10, task_group="static")
        
        dynamic_done = False
        while len(generation_futures) > 0 or not dynamic_done:
            if strat_future.done() and not dynamic_done:
                dynamic_raw = strat_future.result()
                dynamic_done = True
                if dynamic_raw:
                    d_strats = []
                    res_a = extract_fields(get_block(dynamic_raw, "전략 A]", "전략 B]"))
                    if res_a: d_strats.append((f"[동적A] {res_a[0]}", res_a[1]))
                    res_b = extract_fields(get_block(dynamic_raw, "전략 B]", "전략 C]"))
                    if res_b: d_strats.append((f"[동적B] {res_b[0]}", res_b[1]))
                    res_c = extract_fields(get_block(dynamic_raw, "전략 C]", "금기 사항"))
                    if res_c: d_strats.append((f"[하이브리드C] {res_c[0]}", res_c[1]))
                    push_tasks(d_strats, start_idx_offset=0, task_group="dynamic")

            done_futs, _ = concurrent.futures.wait(generation_futures.keys(), timeout=0.1, return_when=concurrent.futures.FIRST_COMPLETED)
            for fut in list(done_futs):
                if fut in generation_futures:
                    task_info = generation_futures.pop(fut)
                    generation_stats["completed_generation_tasks"] += 1
                    try:
                        res = fut.result()
                    except Exception as e:
                        generation_stats["failed_generation_tasks"] += 1
                        generation_stats["generation_failures"].append({"cid": task_info.get("cid", ""), "strategy": task_info.get("strat_label", ""), "error": str(e)})
                        continue
                    if not res["success"]:
                        generation_stats["failed_generation_tasks"] += 1
                        generation_stats["generation_failures"].append({"cid": res.get("cid", task_info.get("cid", "")), "strategy": res.get("strategy", task_info.get("strat_label", "")), "error": res.get("error", "unknown_error")})
                        continue

                    generation_stats["successful_generation_tasks"] += 1
                    returned_count = len(res.get("copies", []))
                    generation_stats["returned_generated_copy_count"] += returned_count
                    for i, t_copy in enumerate(res["copies"]):
                        raw_copy = "" if t_copy is None else str(t_copy)
                        cleaned_copy = clean_marketing_text(raw_copy)
                        c_suffix = f"_{candidate_variant_suffix(i)}"
                        candidate_id = f"{res.get('cid', task_info.get('cid', ''))}{c_suffix}"
                        if raw_candidate_collector is not None:
                            raw_candidate_collector.append({
                                "generator_version": generator_version,
                                "task_cid": res.get("cid", task_info.get("cid", "")),
                                "candidate_id": candidate_id,
                                "variant_index": i,
                                "strategy": res.get("strategy", task_info.get("strat_label", "")),
                                "raw_copy": raw_copy,
                                "cleaned_copy": cleaned_copy,
                                "generation_time_sec": res.get("time", 0),
                            })
                        t_copy = cleaned_copy
                        candidate_count_before_filter += 1

                        hygiene_rejection = get_copy_hygiene_rejection(t_copy)
                        if hygiene_rejection is not None:
                            hygiene_rejection.update({
                                "rejected_cid": candidate_id,
                                "strategy": res.get("strategy", task_info.get("strat_label", "")),
                                "variant_index": i,
                                "copy_preview": t_copy[:120],
                            })
                            generation_stats["hygiene_rejection_count"] += 1
                            generation_stats["hygiene_rejections"].append(hygiene_rejection)
                            print(f"   🟡 [{candidate_id:>8}] 위생 컷({hygiene_rejection['reason']}) | {t_copy[:30]}...")
                            continue

                        duplicate_match = None
                        duplicate_similarity = 0.0
                        for existing in duplicate_pool:
                            duplicate_similarity = character_similarity(t_copy, existing["copy"])
                            if duplicate_similarity >= DUPLICATE_SIMILARITY_THRESHOLD:
                                duplicate_match = existing
                                break

                        if duplicate_match is not None:
                            duplicate_rejections.append({
                                "kept_cid": duplicate_match["cid"],
                                "kept_copy": duplicate_match["copy"],
                                "rejected_cid": candidate_id,
                                "rejected_copy": t_copy,
                                "similarity": round(duplicate_similarity, 6),
                            })
                            continue
                        c_vec = get_candidate_embedding(t_copy)
                        if c_vec is None:
                            print(f"    ⚠️  [{res['cid']}] 임베딩 실패 (None). 점수 0점 처리.")
                            continue

                        ai_results = scorer.score_candidates(np.array([c_vec]), candidate_texts=[t_copy])
                        ai_res = ai_results[0]
                            
                        item = {
                            "cid": res["cid"] + c_suffix, 
                            "copy": t_copy, 
                            "strategy": res["strategy"],
                            "score_data": ai_res,
                            "total_score": ai_res['total_score'],
                            "rerank_embedding": c_vec
                        }
                        scored.append(item)
                        duplicate_pool.append({"cid": item["cid"], "copy": t_copy})
                        gen_times.append(res["time"])
                        generation_stats["accepted_generated_copy_count"] += 1
                            
                        h_mark = "[PASS]" if ai_res['pass_hurdle'] else "      "
                        print(f"   🟢 [{res['cid']+c_suffix:>8}] {ai_res['total_score']:>5.1f} {h_mark} | {t_copy[:30]}...")

    scored = sorted(scored, key=lambda x: x['total_score'], reverse=True)
    
    print(f"\n5. 최종 토너먼트 리랭킹 (Top 10 리그전)...")
    final_candidates_vecs = []
    for item in scored[:10]:
        v = item.get("rerank_embedding")
        if v is not None:
            rerank_reused_embedding_count += 1
        else:
            v = get_candidate_embedding(item['copy'])
        item["rerank_embedding"] = v
        if v is None: v = np.zeros(3072)
        final_candidates_vecs.append(v)
    
    if final_candidates_vecs:
        orig_idx_in_final = next((i for i, item in enumerate(scored[:10]) if item['cid'] == 'Original'), None)
        final_candidate_texts = [item['copy'] for item in scored[:10]]
        refined_results = scorer.score_candidates(np.array(final_candidates_vecs), orig_index=orig_idx_in_final, candidate_texts=final_candidate_texts)
        
        for r_res in refined_results:
            orig_list_idx = r_res['index']
            scored[orig_list_idx]['total_score'] = r_res['total_score']
            scored[orig_list_idx]['score_data'] = r_res
            
        print(f"   ✅ 토너먼트 변수 반영 완료 (원본 대비 승리 여부 및 승률 점수 합산)")
    
    scored = sorted(scored, key=lambda x: x['total_score'], reverse=True)
    
    orig_item = next((item for item in scored if item['cid'] == 'Original'), None)
    orig_rank = next((i+1 for i, item in enumerate(scored) if item['cid'] == 'Original'), -1)
    orig_reg = orig_item['score_data'].get('reg_score', 0) if orig_item else 0
    
    print(f"\n[Benchmark] original rank: {orig_rank} / {len(scored)}")
    print(f"   🚩 원본 평가 점수: {orig_reg:.1f}")
    print(f"\n🏆 [최종 최적화 TOP 3 상세 내역]")
    for idx, item in enumerate(scored[:3]):
        reg = item['score_data'].get('reg_score', 0)
        wins = item['score_data'].get('league_wins', 0)
        gate = item['score_data'].get('confidence_gate', {}) or {}
        gate_summary = ""
        if gate:
            gate_summary = (
                f" | Gate 강승/강패: {gate.get('strong_wins', 0)}/{gate.get('strong_losses', 0)}"
                f" | Gate 주장승/패: {gate.get('claimed_wins', 0)}/{gate.get('claimed_losses', 0)}"
            )
        print(f"[{idx+1}위] 평가 점수: {reg:.1f} | 토너먼트 승수: {wins}{gate_summary}")
        print(f"텍스트:\n{item['copy']}\n" + "-"*40)
        
    if orig_rank == 1:
        print(f"   👑 원본 카피가 실전 대조 결과 최종 1위를 수성했습니다!")
    elif orig_rank <= 5:
        print(f"   🔥 원본이 상위권 {orig_rank}위에 입성했습니다.")
    else:
        print(f"   🚀 원본보다 실질 성과 기대치가 높은 AI 카피가 {orig_rank-1}개 발견되었습니다.")

    print(f"\n✨ 최적화 완료! (총 {len(scored)}개 분석, 소요시간: {time.time()-t_start:.1f}초)")

    if return_metadata:
        def serialize_candidate(idx, item):
            score_data = item.get("score_data", {}) or {}
            return {
                "rank": idx, "cid": item.get("cid"), "copy": item.get("copy", ""),
                "strategy": item.get("strategy", ""), "total_score": item.get("total_score", 0),
                "reg_score": score_data.get("reg_score", 0), "league_wins": score_data.get("league_wins", 0),
                "pass_hurdle": score_data.get("pass_hurdle", False),
                "scorer_mode": score_data.get("scorer_mode", ""),
                "confidence_gate_score": score_data.get("confidence_gate_score", 0),
                "confidence_gate_final_score": score_data.get("confidence_gate_final_score", 0),
                "confidence_gate": score_data.get("confidence_gate", {}),
                "ensemble_components": score_data.get("ensemble_components", {}),
            }

        top_candidates = [serialize_candidate(idx, item) for idx, item in enumerate(scored[:10], 1)]
        all_candidates = [serialize_candidate(idx, item) for idx, item in enumerate(scored, 1)]

        return {
            "top_results": scored[:3],
            "meta": {
                "original_rank": orig_rank,
                "candidate_count": len(scored),
                "candidate_count_before_filter": candidate_count_before_filter,
                "candidate_count_after_filter": len(scored),
                "original_reg_score": orig_reg,
                "embedding_cache_hits": embedding_session_stats["hits"],
                "embedding_cache_misses": embedding_session_stats["misses"],
                "embedding_cache_size": len(candidate_embedding_cache),
                "embedding_store_mode": emb_mgr.get_storage_mode(),
                "embedding_storage_counts": emb_mgr.get_storage_counts(),
                "precomputed_retrieval_count": len(vector_refs),
                "retrieval_chunk_size": RETRIEVAL_SIMILARITY_CHUNK_SIZE,
                "repeated_char_hard_limit": generation_stats["repeated_char_hard_limit"],
                "hygiene_rejection_count": generation_stats["hygiene_rejection_count"],
                "hygiene_rejections": generation_stats["hygiene_rejections"],
                "duplicate_similarity_threshold": DUPLICATE_SIMILARITY_THRESHOLD,
                "duplicate_rejection_count": len(duplicate_rejections),
                "duplicate_rejected_pairs": duplicate_rejections,
                "rerank_reused_embedding_count": rerank_reused_embedding_count,
                "generation_sibling_count": SIBLING_COPY_COUNT,
                "generation_output_mode": "tagged_siblings",
                "generator_version": generator_version,
                "raw_candidate_count": len(raw_candidate_collector) if raw_candidate_collector is not None else None,
                "static_strategy_count": generation_stats["static_strategy_count"],
                "dynamic_strategy_count": generation_stats["dynamic_strategy_count"],
                "static_generation_task_count": generation_stats["static_generation_task_count"],
                "dynamic_generation_task_count": generation_stats["dynamic_generation_task_count"],
                "scheduled_generation_tasks": generation_stats["scheduled_generation_tasks"],
                "completed_generation_tasks": generation_stats["completed_generation_tasks"],
                "successful_generation_tasks": generation_stats["successful_generation_tasks"],
                "failed_generation_tasks": generation_stats["failed_generation_tasks"],
                "expected_generated_copy_count": generation_stats["expected_generated_copy_count"],
                "returned_generated_copy_count": generation_stats["returned_generated_copy_count"],
                "accepted_generated_copy_count": generation_stats["accepted_generated_copy_count"],
                "undersized_generation_tasks": generation_stats["undersized_generation_tasks"],
                "undersized_generation_details": generation_stats["undersized_generation_details"],
                "generation_failures": generation_stats["generation_failures"],
                "top_candidates": top_candidates,
                "all_candidates": all_candidates,
            },
        }

    return scored[:3]

def main():
    run_optimization(ORIGINAL_COPY, PRODUCT_FOCUS)

if __name__ == "__main__":
    main()
