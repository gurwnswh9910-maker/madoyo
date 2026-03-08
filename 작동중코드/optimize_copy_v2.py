import sys
import os
import io
import re
import time
import numpy as np

# UTF-8 출력 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

# 현재 파일 디렉토리를 경로에 추가하여 로컬 모듈(app_config 등) 임포트 보장
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from concurrent.futures import ThreadPoolExecutor
from app_config import (
    GEMINI_API_KEY, MODEL_NAME, MAX_WORKERS, BASE_PATH, 
    ORIGINAL_COPY, PRODUCT_FOCUS, STATIC_STRATEGIES
)

from data_feedback_loop_v2 import MSSDataIntegrator
from copy_scorer_v3 import CopyScorer
from copy_generator_v2 import DynamicCopyGenerator
from contrastive_prompter import ContrastivePrompter

def is_korean(text):
    if not isinstance(text, str): return False
    kor_count = len(re.findall('[가-힣]', text))
    return (kor_count / max(len(text), 1)) > 0.3

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
        for attempt in range(2):
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                gen_time = time.time() - t_gen
                copy_text = response.text.strip()
                # 불필요한 마크다운 기호 및 따옴표 제거
                copy_text = re.sub(r'^[`"\'\s]+|[`"\'\s]+$', '', copy_text)
                copy_text = re.sub(r'^```.*?\n|```$', '', copy_text, flags=re.MULTILINE).strip()
                return {"success": True, "cid": cid, "copy": copy_text, "strategy": strat_label, "time": gen_time}
            except Exception as e:
                if "429" in str(e) and attempt == 0:
                    time.sleep(10)
                    continue
                
                # gemini-3-flash-preview 실패 시 gemini-2.5-flash로 자동 폴백
                if model == "gemini-3-flash-preview":
                    print(f"    ⚠️ [{cid}] {model} 생성 실패 ({e}). gemini-2.5-flash로 재시도합니다...")
                    try:
                        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                        gen_time = time.time() - t_gen
                        copy_text = response.text.strip()
                        copy_text = re.sub(r'^[`"\'\s]+|[`"\'\s]+$', '', copy_text)
                        copy_text = re.sub(r'^```.*?\n|```$', '', copy_text, flags=re.MULTILINE).strip()
                        return {"success": True, "cid": cid, "copy": copy_text, "strategy": strat_label, "time": gen_time}
                    except Exception as e2:
                        print(f"    ❌ [{cid}] gemini-2.5-flash 생성도 실패: {e2}")
                        raise e2
                raise e
    except Exception as e:
        return {"success": False, "cid": cid, "error": str(e)}

def extract_dynamic_all(client, model, product_info, pairs, static_strats=None):
    # (기존 코드 유지)
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
    # 테스트용: 전략 추출 프롬프트 저장
    try:
        with open("strategy_extraction_prompt.txt", "w", encoding="utf-8") as f:
            f.write(prompt)
    except: pass

    try:
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text.strip()
    except Exception as e:
        # gemini-3-flash-preview 실패 시 gemini-2.5-flash로 자동 폴백
        if model == "gemini-3-flash-preview":
            print(f"   ⚠️ 동적 전략 추출 실패 ({e}). gemini-2.5-flash로 재시도합니다...")
            try:
                response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                return response.text.strip()
            except Exception as e2:
                print(f"   ❌ gemini-2.5-flash 전략 추출도 실패: {e2}")
                return None
        else:
            print(f"동적 전략 추출 실패: {e}")
            return None

def run_optimization(original_copy: str, product_focus, api_key: str = None,
                      model_name: str = None, base_path: str = None):
    # ═══ google.genai Client 방식 (최신 API) ═══
    from google import genai # 로컬 임포트로 이동
    _api_key = api_key or GEMINI_API_KEY
    _model = model_name or MODEL_NAME
    _base_path = base_path or BASE_PATH
    client = genai.Client(api_key=_api_key)
    MODEL = _model

    print("=" * 80)
    print("MAB 성과 극대화 시스템 v3.2 (Managed Config)")
    print(f"모델: {MODEL} | 스쿠어링: 로컬 임베딩")
    print("=" * 80)
    
    # ══════════════════════════════════════
    # 검증 지표 초기화
    # ══════════════════════════════════════
    api_calls = 0
    api_errors = 0
    gen_times = []
    t_start = time.time()

    # ═══════════════════════════════════════════════════
    # 1. 데이터 로딩
    # ═══════════════════════════════════════════════════
    print("\n1. 데이터 로딩...")
    t0 = time.time()
    integrator = MSSDataIntegrator(_base_path)
    
    class DummyMAB:
        def update_reward(self, *args, **kwargs): pass
        def decay(self, *args, **kwargs): pass
        def update(self, *args, **kwargs): pass
        clusters = {}
    
    all_data = integrator.process_all_data(DummyMAB())
    print(f"   로딩 완료: {time.time()-t0:.1f}초")

    korean_data = all_data[all_data['본문'].apply(is_korean)].drop_duplicates(subset='본문').copy()
    print(f"   한국어: {len(korean_data)}개 / 전체 {len(all_data)}개")
    
    # ═══════════════════════════════════════════════════
    # 2. 제품 기반 유사 고성과 검색 (벡터화 최적화)
    # ═══════════════════════════════════════════════════
    print("\n2. 유사 클러스터 및 전략 도출 중...")
    from embedding_utils import EmbeddingManager # 로컬 임포트로 이동
    emb_mgr = EmbeddingManager(storage_path=os.path.join(_base_path, 'embeddings.pkl'))
    
    # 1) 제품/전체 데이터 행렬 연산
    # product_focus가 딕셔너리인 경우 'insight'를 검색 기준으로 사용 (가장 핵심적인 뉘앙스)
    search_query = (product_focus.get('marketing_insight') or product_focus.get('insight')) if isinstance(product_focus, dict) else product_focus
    product_emb = emb_mgr.get_embedding(search_query)
    all_texts = korean_data['본문'].tolist()
    all_embs = emb_mgr.get_embeddings_matrix(all_texts)
    
    prod_vec = np.array(product_emb).reshape(1, -1)
    # 코사인 유사도 벡터화 계산
    norms = np.linalg.norm(all_embs, axis=1) * np.linalg.norm(prod_vec)
    sims = np.dot(all_embs, prod_vec.T).flatten() / norms
    
    similarities = list(zip(sims, korean_data['MSS'], all_texts))
    
    # 2) 유사도 순위 추출 (유사도 탑 20개 중 MSS 최상위 5개를 선별)
    similarities.sort(key=lambda x: x[0], reverse=True)
    top_similar = similarities[:20]
    top_similar.sort(key=lambda x: x[1], reverse=True)
    best_similar_posts = top_similar[:5]
    
    # Generator 초기화 (유사 클러스터 고성과 데이터 주입)
    top_examples_for_gen = [{'본문': text, 'MSS': mss} for _, mss, text in best_similar_posts]
    generator = DynamicCopyGenerator(top_examples_for_gen)
    
    # 대조 프롬프터 초기화
    contrastive = ContrastivePrompter(embedding_manager=emb_mgr, all_data=korean_data)
    
    # 해당 클러스터 게시물들을 기준으로 여러 개의 High/Low 페어 추출
    dynamic_pairs = []
    for _, best_post_mss, best_post_text in best_similar_posts:
        best_low_text, best_low_mss = contrastive._find_dynamic_contrastive_pair(best_post_text, best_post_mss)
        if best_low_text:
            dynamic_pairs.append({
                'high_text': best_post_text, 
                'high_mss': best_post_mss, 
                'low_text': best_low_text, 
                'low_mss': best_low_mss
            })
    
    static_strategies = STATIC_STRATEGIES

    # ═══════════════════════════════════════════════════
    # 3. 전략 추출 및 카피 생성 병렬 파이프라인 (Pipelining)
    # ═══════════════════════════════════════════════════
    print(f"\n3. 전략 추출 및 카피 생성 (파이프라인 가동)...")
    
    # 1) 스코어링 준비 (기준 벡터 미리 계산)
    scorer = CopyScorer(embedding_manager=emb_mgr)
    scorer.prepare_reference_vectors(korean_data, product_info=product_focus)
    
    all_candidates = [{"id": "Original", "copy": original_copy, "strategy": "원본"}]
    # 원본 채점 (본인 임베딩 사용)
    original_emb = emb_mgr.get_embedding(original_copy)
    orig_results = scorer.score_batch([{"id": "Original", "copy": original_copy, "embedding": original_emb}], korean_data, product_info=product_focus)
    scored = [orig_results[0]]
    
    import concurrent.futures
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # A. 동적 전략 추출 시작 (비동기)
        if dynamic_pairs:
            print(f"   ⏳ 동적 전략 추출 API 호출 중...")
            strat_future = executor.submit(extract_dynamic_all, client, MODEL, product_focus, dynamic_pairs, static_strategies)
        else:
            strat_future = None

        # B. 정적 전략(Static) 태스크 즉시 투입 (선출발)
        generation_futures = {} # {future: task_info}
        prevent_insight = None # 초기화 (NameError 방지)
        
        def push_tasks(strat_list, start_idx_offset=0):
            for s_idx, (main_name, main_desc) in enumerate(strat_list):
                actual_s_idx = s_idx + start_idx_offset
                is_high_priority = "동적" in main_name or "하이브리드" in main_name
                num = 4 if is_high_priority else 3
                
                # 서브 전략용 후보 (자기 자신 제외)
                # 정적 전략만 있을 때는 정적 전략끼리, 전체가 생기면 전체에서 선택 (간소화를 위해 현재 풀에서 선택)
                sub_candidates = [s for s in strat_list if s[0] != main_name]
                if not sub_candidates: sub_candidates = strat_list # 혼자뿐이면 그냥 씀
                
                for v_idx in range(num):
                    cid = f"DYN_{actual_s_idx}_{v_idx+1}" if is_high_priority else f"S{actual_s_idx}_{v_idx+1}"
                    strat_label = main_name if is_high_priority else f"{main_name} (+{v_idx+1})"
                    
                    if is_high_priority:
                        combined_desc = main_desc
                    else:
                        sub_name, sub_desc = sub_candidates[v_idx % len(sub_candidates)]
                        combined_desc = f"【메인 로직】 {main_desc}\n【서브 요소 추가】 {sub_desc}"
                    
                    prompt = generator.generate_prompt(
                        product_info=product_focus,
                        strategy_name=strat_label,
                        strategy_desc=combined_desc,
                        original_copy=original_copy,
                        variation_idx=f"{v_idx+1}",
                        dynamic_context=prevent_insight
                    )
                    task = {"cid": cid, "prompt": prompt, "strat_label": strat_label}
                    fut = executor.submit(generate_single_task, client, MODEL, task)
                    generation_futures[fut] = task

        # 정적 전략 투입
        push_tasks(static_strategies, start_idx_offset=10) # ID 겹침 방지 위해 오프셋
        print(f"   🚀 정적 전략 카피 생성 시작 (API 대기 시간 활용 중...)")

        # C. 동적 전략 파싱 및 추가 투입 (Pipelining)
        dynamic_done = False
        while len(generation_futures) > 0 or not dynamic_done:
            # 1) 전략 추출 완료 체크
            if strat_future and strat_future.done() and not dynamic_done:
                try:
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
                        
                        print(f"   🔥 동적 전략 확보 완료 ({len(d_strats)}개)! 카피 생성 추가 투입...")
                        push_tasks(d_strats, start_idx_offset=0)
                    else:
                        print("   ⚠️ 동적 전략 추출 결과가 비어있습니다.")
                except Exception as e:
                    print(f"   ❌ 동적 전략 추출 중 오류 발생: {e}")
                    dynamic_done = True

            # 2) 생성 완료된 카피 실시간 채점 (Streaming)
            if len(generation_futures) > 0:
                done_futs, _ = concurrent.futures.wait(generation_futures.keys(), timeout=0.1, return_when=concurrent.futures.FIRST_COMPLETED)
                for fut in list(done_futs):
                    if fut in generation_futures:
                        task_info = generation_futures.pop(fut)
                        try:
                            res = fut.result()
                            if res["success"]:
                                # 실시간 채점
                                c_text = res["copy"]
                                c_emb = emb_mgr.get_embedding(c_text)
                                c_res_list = scorer.score_batch([{
                                    "id": res["cid"], 
                                    "copy": c_text, 
                                    "strategy": res["strategy"], 
                                    "embedding": c_emb
                                }], korean_data, product_info=product_focus)
                                
                                if c_res_list:
                                    c_res = c_res_list[0]
                                    scored.append(c_res)
                                    api_calls += 1
                                    gen_times.append(res["time"])
                                    preview = c_text.replace('\n', ' / ')[:35]
                                    print(f"   ✅ [{res['cid']:>8}] {c_res['score_data']['mss_score_estimate']:>5} | {preview}...")
                            else:
                                api_errors += 1
                                print(f"   ❌ [{res['cid']}] 생성 실패: {res['error']}")
                        except Exception as e:
                            api_errors += 1
                            print(f"   ❌ [{task_info['cid']}] 처리 중 시스템 오류: {e}")
            else:
                # 대기 중인 전략 추출이 있다면 잠시 쉼
                time.sleep(0.5)

    print(f"\n   모든 프로세스 완료: {len(scored)}개 카피 분석됨")
    score_time = 0 # 실시간으로 수행되었으므로 별도 측정 불필요

    # ═══════════════════════════════════════════════════
    # 5. Top-3 선정
    # ═══════════════════════════════════════════════════
    top_3 = scorer.select_top_3(scored)
    orig = next((r for r in scored if r['id'] == 'Original'), None)
    orig_score = orig['score_data']['mss_score_estimate'] if orig else 0

    # ═══════════════════════════════════════════════════
    # 6. 결과 출력
    # ═══════════════════════════════════════════════════
    total_time = time.time() - t_start
    avg_gen = sum(gen_times) / max(len(gen_times), 1)
    
    print(f"\n{'═'*80}")
    print(f"📊 초고속 결과 리포트 (v4.0 - Pipelined)")
    print(f"{'═'*80}")
    
    print(f"\n[원본] (점수: {orig_score})")
    print(original_copy)
    
    print(f"\n{'─'*80}")
    for rank, item in enumerate(top_3, 1):
        sd = item['score_data']
        delta = sd['mss_score_estimate'] - orig_score
        arrow = "🔺" if delta > 0 else "🔻"
        print(f"\nRANK {rank} [{item['id']}] {item['strategy']} | 점수: {sd['mss_score_estimate']} ({arrow}{delta:+d})")
        print(item['copy'])
        print(f"💬 {sd['reason']}")
    
    print(f"\n{'═'*80}")
    print(f"🔍 검증")
    print(f"  시간: {total_time:.0f}초 | API: {api_calls}회 | 오류: {api_errors}회")
    print(f"  생성 평균: {avg_gen:.1f}초/건 | 실시간 스트리밍 채점 적용됨")
    print(f"  향상: {top_3[0]['score_data']['mss_score_estimate'] - orig_score:+d}점")
    print(f"{'═'*80}")
    
    return top_3

def main():
    # 수동 모드일 때는 app_config.py의 하드코딩된 변수를 사용합니다.
    run_optimization(ORIGINAL_COPY, PRODUCT_FOCUS)

if __name__ == "__main__":
    main()
