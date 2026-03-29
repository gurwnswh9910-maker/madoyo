"""
[ONLINE VERSION] optimize_copy_v2.py의 Online 이식판.
로컬 엔진의 전체 파이프라인을 SQL(pgvector) 기반으로 동일하게 구현합니다.
차이점: pkl 대신 DB, DynamicMAB 대신 static priority, CopyScorerV4 대신 CopyScorer(DB native)
"""
import os
import re
import time
import numpy as np
import pandas as pd
import concurrent.futures
from typing import List, Dict, Any
from google import genai

from embedding_utils_online import EmbeddingManager
from contrastive_prompter_online import ContrastivePrompter
from copy_generator_v2 import DynamicCopyGenerator
from copy_scorer_v5_online import CopyScorerV5
from api.config import STATIC_STRATEGIES


def clean_marketing_text(text):
    """마케팅 카피의 불필요한 노이즈를 제거합니다."""
    if not text: return ""
    text = re.sub(r'\d+\s*[/\n\\]\s*\d+', '', text).strip()
    noises = ['번역하기', 'See translation', 'See original', '원문 보기', '번역 보기', '...더보기']
    for n in noises:
        text = text.replace(n, '')
    return text.strip()


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


def generate_single_task(client, model, task):
    """단일 카피 LLM 호출 (로컬 엔진과 동일)"""
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

                copies = []
                def extract(tag):
                    if f"[{tag}]" not in raw_text: return None
                    start = raw_text.find(f"[{tag}]") + len(f"[{tag}]")
                    end = raw_text.find("[", start)
                    if end == -1: return raw_text[start:].strip()
                    return raw_text[start:end].strip()

                draft = extract("DRAFT_COPY")
                final = extract("FINAL_COPY")
                if draft: copies.append(draft)
                if final: copies.append(final)

                if not copies:
                    clean_text = re.sub(r'^[`"\'\\s]+|[`"\'\\s]+$', '', raw_text)
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
    """대조 쌍 기반 동적 전략 추출 (로컬 엔진과 동일)"""
    static_context = ""
    if static_strats:
        static_context = "\n[참고: 우리가 평소 활용하는 성공 공식(정적 전략)]\n"
        for i, (name, desc) in enumerate(static_strats, 1):
            static_context += f"{i}. {name}: {desc}\n"

    pairs_context = ""
    if pairs:
        pairs_context = "\n[실제 데이터: 고성과 vs 저성과 게시물 쌍]\n"
        for i, p in enumerate(pairs, 1):
            h_preview = str(p.get('high_text', '')).replace('\n', ' / ')[:150]
            l_preview = str(p.get('low_text', '')).replace('\n', ' / ')[:150]
            pairs_context += f"\n쌍 {i}:\n"
            pairs_context += f"  ✅ HIGH (MSS {p.get('high_mss', 0):.0f}): {h_preview}\n"
            pairs_context += f"  ❌ LOW  (MSS {p.get('low_mss', 0):.0f}): {l_preview}\n"

    prompt = f"""당신은 10년차 탑 바이럴 마케터입니다.
아래는 '{product_info}'와 유사한 카테고리에서 작성된 {len(pairs)}개의 고성과/저성과 게시물 쌍(Pair)입니다. 

{pairs_context}
{static_context}

위 예시 데이터와 성공 공식을 분석하여, 오늘 우리가 카피를 쓸 때 적용할 '서로 다른 접근 방식의 강력한 전술(전략)' 3가지와, 모든 전략에서 공통으로 피해야 할 '실패 패턴' 1가지를 도출하세요.

형식:
[동적 전략 A]
- 명칭: (예: 일상 반전 서사형)
- 설명: (데이터의 특징만 철저히 분석하여 도출한 훅 구조 2~3문장)

[동적 전략 B]
- 명칭: (예: 제3자 관찰 증언형)
- 설명: (전략 A와는 완전히 다른 각도의 데이터 기반 접근법 2~3문장)

[하이브리드 전략 C]
- 명칭: (예: 성공 공식 결합형)
- 설명: (실시간 데이터의 특징과 제공된 '성공 공식' 중 하나를 영리하게 결합한 전술 2~3문장)

[🚨 핵심 금기 사항]
- 내용: (저성과 게시물들의 공통 실패 원인을 분석하여, 이번 카피에서 절대로 하지 말아야 할 1~2가지)
"""
    try:
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text.strip()
    except Exception as e:
        print(f"    ⚠️ 동적 전략 추출 실패: {e}")
        return None


def run_optimization_online(
    original_copy: str,
    product_focus: Any,
    api_key: str,
    model_name: str,
    input_image_urls: List[str] = None,
    user_id: str = None,
    shared_resources: Dict = None
):
    """[ONLINE VERSION] SQL(pgvector) 기반 실시간 하이브리드 카피 최적화 엔진"""
    
    print(f"\n{'='*80}")
    print(f"🚀 [ONLINE ENGINE] MAB 하이브리드 최적화 시스템 v4.1 (SQL Native)")
    print(f"모드: {'멀티모달' if input_image_urls else '텍스트 전용'}")
    print(f"{'='*80}")
    
    t_start = time.time()
    client = genai.Client(api_key=api_key)
    MODEL = model_name
    
    if shared_resources is None: shared_resources = {}
    target_img = input_image_urls[0] if input_image_urls else None
    
    # ══════════════════════════════════════════════════════════════
    # 1. SQL 기반 임베딩 매니저 & 스코어러 로드
    # ══════════════════════════════════════════════════════════════
    emb_mgr = shared_resources.get('emb_mgr')
    if not emb_mgr:
        emb_mgr = EmbeddingManager()
        shared_resources['emb_mgr'] = emb_mgr
    
    scorer = shared_resources.get('scorer')
    if not scorer:
        # 512MB 램 제한을 위해 내부 GC 통제 버전
        scorer = CopyScorerV5()
        shared_resources['scorer'] = scorer
    
    # ══════════════════════════════════════════════════════════════
    # 2. 하이브리드 회수 (Online SQL Retrieval)
    # ══════════════════════════════════════════════════════════════
    print(f"\n2. SQL 하이브리드 회수 중 (pgvector)...")
    
    query_vec = None
    if original_copy and input_image_urls:
        query_vec = emb_mgr.get_multimodal_embedding(text=original_copy, image_paths_or_urls=input_image_urls)
    elif input_image_urls:
        query_vec = emb_mgr.get_multimodal_embedding(image_paths_or_urls=input_image_urls)
    else:
        query_vec = emb_mgr.get_text_embedding(original_copy)

    filtered_subset = pd.DataFrame(columns=['본문', 'MSS', 'alpha_score'])
    if query_vec is not None:
        results = emb_mgr.get_hybrid_top_k(query_vec, k=100, alpha=0.3)
        if results:
            filtered_subset = pd.DataFrame(results)
            filtered_subset = filtered_subset.rename(columns={
                'content_text': '본문', 'mss_score': 'MSS', 'similarity': 'alpha_score'
            })
            print(f"   ✅ [SQL] {len(filtered_subset)}개 데이터 확보 완료")

    if filtered_subset.empty:
        print("   ⚠️ 회수된 데이터가 없습니다. 빈 결과를 반환합니다.")
        return []

    best_similar_posts = filtered_subset.head(10)
    top_examples_for_gen = best_similar_posts[['본문', 'MSS']].to_dict('records')
    
    generator = DynamicCopyGenerator(top_examples_for_gen)
    contrastive = ContrastivePrompter(embedding_manager=emb_mgr)
    
    # ══════════════════════════════════════════════════════════════
    # 3. 원본 채점 + 대조쌍 추출 + 전략 도출 + 카피 생성 (Pipeline)
    # ══════════════════════════════════════════════════════════════
    print(f"\n3. 전략 추출 및 카피 생성 시작...")
    
    # 원본 수집 준비
    orig_vec = query_vec if query_vec is not None else np.zeros(3072)
    
    scored = [{
        "success": True,
        "cid": "Original",
        "copy": original_copy,
        "strategy": "원본",
        "embedding": orig_vec
    }]
    
    # 대조쌍 추출 (SQL 기반)
    dynamic_pairs = []
    for _, row in best_similar_posts.head(5).iterrows():
        low_text, low_mss = contrastive._find_dynamic_contrastive_pair(row['본문'], row['MSS'])
        if low_text:
            dynamic_pairs.append({
                'high_text': row['본문'], 'high_mss': row['MSS'],
                'low_text': low_text, 'low_mss': low_mss
            })
    
    print(f"   📊 대조쌍 {len(dynamic_pairs)}개 확보")
    
    # 병렬 실행: 동적 전략 추출 + 정적 전략 카피 생성
    MAX_WORKERS = 15
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 동적 전략 추출 (비동기)
        strat_future = executor.submit(
            extract_dynamic_all, client, MODEL, product_focus, dynamic_pairs, STATIC_STRATEGIES
        )
        
        generation_futures = {}
        
        def push_tasks(strat_list, start_idx_offset=0):
            for s_idx, (name, desc) in enumerate(strat_list):
                num = 4 if "동적" in name or "하이브리드" in name else 2
                for v_idx in range(num):
                    cid = f"DYN_{s_idx}_{v_idx}" if num > 2 else f"S_{s_idx+start_idx_offset}_{v_idx}"
                    prompt = generator.generate_prompt(
                        product_info=product_focus, strategy_name=name, strategy_desc=desc,
                        original_copy=original_copy, variation_idx=v_idx+1
                    )
                    task = {"cid": cid, "prompt": prompt, "strat_label": name}
                    fut = executor.submit(generate_single_task, client, MODEL, task)
                    generation_futures[fut] = task
        
        # 정적 전략 먼저 투입
        push_tasks(STATIC_STRATEGIES, start_idx_offset=10)
        
        dynamic_done = False
        while len(generation_futures) > 0 or not dynamic_done:
            # 동적 전략 결과 수신 시 추가 투입
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
                    push_tasks(d_strats, start_idx_offset=0)
                    print(f"   🎯 동적 전략 {len(d_strats)}개 주입 완료")
            
            done_futs, _ = concurrent.futures.wait(
                generation_futures.keys(), timeout=0.1,
                return_when=concurrent.futures.FIRST_COMPLETED
            )
            for fut in list(done_futs):
                if fut in generation_futures:
                    task_info = generation_futures.pop(fut)
                    res = fut.result()
                    if res["success"]:
                        for i, t_copy in enumerate(res["copies"]):
                            t_copy = clean_marketing_text(t_copy)
                            time.sleep(1.5)
                            
                            if target_img:
                                c_vec = emb_mgr.get_multimodal_embedding(
                                    text=t_copy, image_paths_or_urls=[target_img]
                                )
                            else:
                                c_vec = emb_mgr.get_text_embedding(t_copy)
                            
                            if c_vec is None:
                                print(f"    ⚠️  [{res['cid']}] 임베딩 실패. 스킵.")
                                continue
                            
                            c_suffix = "_A" if i == 0 else "_B"
                            item = {
                                "cid": res["cid"] + c_suffix,
                                "copy": t_copy,
                                "strategy": res["strategy"],
                                "embedding": c_vec
                            }
                            scored.append(item)
                            print(f"   ✅ [{res['cid']+c_suffix:>8}] 후보군 추가 완료 | {t_copy[:30]}...")
                    else:
                        print(f"   ❌ [{res['cid']}] 생성 실패: {res.get('error', 'unknown')}")
            
            if not generation_futures and dynamic_done:
                break
    
    # ══════════════════════════════════════════════════════════════
    # 4. [V16] 98% 정확도 ML 리그전 통합 채점
    # ══════════════════════════════════════════════════════════════
    print(f"\n4. [V5 엔진] 생성된 {len(scored)}개 카피 전원 ML 리그전 채점 중...")
    
    candidates_embeddings = [c["embedding"] for c in scored]
    orig_idx = next((i for i, c in enumerate(scored) if c["cid"] == "Original"), 0)
    
    try:
        scoring_results = scorer.score_candidates(candidates_embeddings, orig_index=orig_idx)
    except Exception as e:
        print(f"    ⚠️ 채점 실패. 에러: {e}")
        scoring_results = []
    
    for rank_meta in scoring_results:
        idx = rank_meta['index']
        scored[idx]["total_score"] = rank_meta['total_score']
        scored[idx]["score_data"] = {
            "mss_score_estimate": rank_meta['total_score'],
            "reg_score": rank_meta['reg_score'],
            "hurdle_prob": rank_meta['hurdle_prob'],
            "pass_hurdle": rank_meta['pass_hurdle'],
            "league_wins": rank_meta['league_wins']
        }
        
    scored = sorted(scored, key=lambda x: x.get('total_score', 0), reverse=True)
    
    orig_rank = next((i+1 for i, item in enumerate(scored) if item['cid'] == 'Original'), -1)
    print(f"\n📊 [성과 벤치마크] ML 원본 순위: {orig_rank}위 / {len(scored)}개 중")
    print(f"🏁 최적화 완료! (총 {len(scored)}개 분석, 소요시간: {time.time()-t_start:.1f}초)")
    
    return [s for s in scored if 'score_data' in s][:3]
