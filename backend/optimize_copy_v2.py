import sys
import os
import io
import re
import time
import numpy as np

# UTF-8 출력 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from concurrent.futures import ThreadPoolExecutor
from app_config import (
    GEMINI_API_KEY, MODEL_NAME, MAX_WORKERS, 
    STATIC_STRATEGIES
)

from copy_scorer_v3 import CopyScorer
from copy_generator_v2 import DynamicCopyGenerator
from contrastive_prompter import ContrastivePrompter
from embedding_utils import EmbeddingManager

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
    cid = task['cid']
    prompt = task['prompt']
    strat_label = task['strat_label']
    t_gen = time.time()
    try:
        response = client.models.generate_content(model=model, contents=prompt)
        gen_time = time.time() - t_gen
        copy_text = response.text.strip()
        copy_text = re.sub(r'^[`"\'\s]+|[`"\'\s]+$', '', copy_text)
        copy_text = re.sub(r'^```.*?\n|```$', '', copy_text, flags=re.MULTILINE).strip()
        return {"success": True, "cid": cid, "copy": copy_text, "strategy": strat_label, "time": gen_time}
    except Exception as e:
        return {"success": False, "cid": cid, "error": str(e)}

def extract_dynamic_all(client, model, product_info, pairs, static_strats=None):
    static_context = ""
    if static_strats:
        static_context = "\n[참고: 우리가 평소 활용하는 성공 공식(정적 전략)]\n"
        for i, (name, desc) in enumerate(static_strats, 1):
            static_context += f"{i}. {name}: {desc}\n"

    prompt = f"""당신은 10년차 탑 바이럴 마케터입니다.
아래는 '{product_info}'와 유사한 카테고리에서 작성된 {len(pairs)}개의 고성과/저성과 게시물 쌍(Pair)입니다. 

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
        print(f"전략 추출 실패: {e}")
        return None

def run_optimization(original_copy: str, product_focus, api_key: str = None,
                      model_name: str = None, user_id=None):
    from google import genai
    _api_key = api_key or GEMINI_API_KEY
    _model = model_name or MODEL_NAME
    client = genai.Client(api_key=_api_key)
    
    print("=" * 80)
    print("MAB 성과 극대화 시스템 v4.0 (SaaS / Supabase Powered)")
    print(f"모델: {_model} | 스코어링: pgvector Native")
    print("=" * 80)

    t_start = time.time()
    emb_mgr = EmbeddingManager()
    
    # ═══════════════════════════════════════════════════
    # 1. 제품 기반 유사 고성과 검색 (DB Native)
    # ═══════════════════════════════════════════════════
    print("\n1. DB 유사 클러스터 분석 중...")
    search_query = (product_focus.get('marketing_insight') or product_focus.get('insight')) if isinstance(product_focus, dict) else product_focus
    
    best_similar_posts = emb_mgr.search_weighted(search_query, current_user_id=user_id, limit=5)
    
    top_examples_for_gen = [{'본문': p['text'], 'MSS': p['mss']} for p in best_similar_posts]
    generator = DynamicCopyGenerator(top_examples_for_gen)
    contrastive = ContrastivePrompter(embedding_manager=emb_mgr)
    
    dynamic_pairs = []
    for p in best_similar_posts:
        low_text, low_mss = contrastive._find_dynamic_contrastive_pair(p['text'], p['mss'])
        if low_text:
            dynamic_pairs.append({
                'high_text': p['text'], 'high_mss': p['mss'], 
                'low_text': low_text, 'low_mss': low_mss
            })
    
    # ═══════════════════════════════════════════════════
    # 2. 전략 추출 및 카피 생성 파이프라인
    # ═══════════════════════════════════════════════════
    print(f"\n2. 전략 추출 및 카피 생성 진행...")
    scorer = CopyScorer(embedding_manager=emb_mgr)
    scorer.prepare_reference_vectors(product_info=product_focus, user_id=user_id)
    
    # 원본 채점
    orig_emb = emb_mgr.get_embedding(original_copy)
    orig_results = scorer.score_batch([{"id": "Original", "copy": original_copy, "embedding": orig_emb}], product_info=product_focus)
    scored = [orig_results[0]]
    
    api_calls = 0
    api_errors = 0
    gen_times = []
    
    prevent_insight = None
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        strat_future = executor.submit(extract_dynamic_all, client, _model, product_focus, dynamic_pairs, STATIC_STRATEGIES)
        
        generation_futures = {}
        
        def push_tasks(strat_list, start_idx_offset=0):
            for s_idx, (name, desc) in enumerate(strat_list):
                is_high = "동적" in name or "하이브리드" in name
                num = 4 if is_high else 3
                for v_idx in range(num):
                    cid = f"DYN_{s_idx+start_idx_offset}_{v_idx+1}"
                    prompt = generator.generate_prompt(
                        product_info=product_focus,
                        strategy_name=name,
                        strategy_desc=desc,
                        original_copy=original_copy,
                        variation_idx=f"{v_idx+1}",
                        dynamic_context=prevent_insight
                    )
                    task = {"cid": cid, "prompt": prompt, "strat_label": name}
                    fut = executor.submit(generate_single_task, client, _model, task)
                    generation_futures[fut] = task

        # 정적 전략 우선 투입
        push_tasks(STATIC_STRATEGIES, start_idx_offset=10)
        
        dynamic_done = False
        import concurrent.futures
        while generation_futures or not dynamic_done:
            # 1) 동적 전략 파싱
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
                    
                    if '금기 사항' in dynamic_raw:
                        prevent_insight = dynamic_raw.split('금기 사항')[-1].strip().strip(':*- ')
                    
                    print(f"   🔥 동적 전략 확보 완료 ({len(d_strats)}개)! 추가 투입...")
                    push_tasks(d_strats, start_idx_offset=0)

            # 2) 생성 완료 체크 및 스트리밍 채점
            if generation_futures:
                done, _ = concurrent.futures.wait(generation_futures.keys(), timeout=0.1, return_when=concurrent.futures.FIRST_COMPLETED)
                for fut in list(done):
                    if fut in generation_futures:
                        task_info = generation_futures.pop(fut)
                        res = fut.result()
                        if res["success"]:
                            c_emb = emb_mgr.get_embedding(res["copy"])
                            c_res = scorer.score_batch([{
                                "id": res["cid"], "copy": res["copy"], 
                                "strategy": res["strategy"], "embedding": c_emb
                            }], product_info=product_focus)[0]
                            scored.append(c_res)
                            api_calls += 1
                            gen_times.append(res["time"])
                            print(f"   ✅ [{res['cid']:>8}] {c_res['score_data']['mss_score_estimate']:>5} | {res['copy'][:30]}...")
                        else:
                            api_errors += 1
                            print(f"   ❌ [{res['cid']}] 생성 실패: {res['error']}")
            else:
                time.sleep(0.5)

    top_3 = scorer.select_top_3(scored)
    orig = next((r for r in scored if r['id'] == 'Original'), None)
    orig_score = orig['score_data']['mss_score_estimate'] if orig else 0

    total_time = time.time() - t_start
    print(f"\n{'='*80}\n📊 최적화 완료: {total_time:.1f}초 | 분석 갯수: {len(scored)}개 | 향상: {top_3[0]['score_data']['mss_score_estimate'] - orig_score:+d}점\n{'='*80}")
    return top_3

if __name__ == "__main__":
    from app_config import ORIGINAL_COPY, PRODUCT_FOCUS
    run_optimization(ORIGINAL_COPY, PRODUCT_FOCUS)
