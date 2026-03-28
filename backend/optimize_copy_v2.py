import sys
import os
import io
import re
import time
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
from copy_scorer_v4_local import CopyScorerV4
from copy_generator_v2 import DynamicCopyGenerator
from contrastive_prompter import ContrastivePrompter

def is_korean(text):
    if not isinstance(text, str): return False
    kor_count = len(re.findall('[가-힣]', text))
    return (kor_count / max(len(text), 1)) > 0.3

def clean_marketing_text(text):
    """마케팅 카피의 불필요한 노이즈(페이지 표시, 번역기 문구 등)를 제거합니다."""
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
                
                # 폴백: 태그가 없으면 전체 텍스트를 하나로 처리
                if not copies:
                    clean_text = re.sub(r'^[`"\'\s]+|[`"\'\s]+$', '', raw_text)
                    clean_text = re.sub(r'^```.*?\n|```$', '', clean_text, flags=re.MULTILINE).strip()
                    copies = [clean_text]
                
                return {"success": True, "cid": cid, "copies": copies, "strategy": strat_label, "time": gen_time}
            except Exception as e:
                if "429" in str(e) and attempt == 0:
                    time.sleep(10)
                    continue
                # ... 폴백 로직 등 (기존과 동일)
                raise e
    except Exception as e:
        return {"success": False, "cid": cid, "error": str(e)}

def extract_dynamic_all(client, model, product_info, pairs, static_strats=None):
    # 정적 전략 컨텍스트
    static_context = ""
    if static_strats:
        static_context = "\n[참고: 우리가 평소 활용하는 성공 공식(정적 전략)]\n"
        for i, (name, desc) in enumerate(static_strats, 1):
            static_context += f"{i}. {name}: {desc}\n"

    # 대조 쌍 데이터를 프롬프트에 삽입
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

def run_optimization(original_copy: str, product_focus, input_image_urls: list = None,
                       api_key: str = None, model_name: str = None, base_path: str = None,
                       shared_resources: dict = None, user_id: str = None):
    # ═══ google.genai Client 방식 (최신 API) ═══
    import concurrent.futures
    from google import genai
    from embedding_utils import EmbeddingManager
    from mab_engine_v2 import DynamicMAB
    
    _api_key = api_key or GlobalConfig.GEMINI_API_KEY
    _model = model_name or GlobalConfig.MODEL_NAME
    _base_path = base_path or str(GlobalConfig.BASE_DIR)
    client = genai.Client(api_key=_api_key)
    MODEL = _model

    print("=" * 80)
    print("MAB 하이브리드 최적화 시스템 v4.1 (Hybrid Retrieval)")
    print(f"모드: {'멀티모달' if input_image_urls else '텍스트 전용(Original)'}")
    print("=" * 80)
    
    t_start = time.time()
    gen_times = []
    # target_img 정의 (전달된 이미지 리스트 중 첫 번째)
    target_img = input_image_urls[0] if input_image_urls else None
    # 1. 데이터 및 임베딩 매니저 초기화 (싱글톤 패턴 지원)
    if shared_resources is None: shared_resources = {}
    
    # 1-1. Integrator 및 데이터 로드
    integrator = shared_resources.get('integrator')
    if not integrator:
        integrator = MSSDataIntegrator(_base_path)
        shared_resources['integrator'] = integrator
        
    korean_data = shared_resources.get('korean_data')
    if korean_data is None:
        all_data = integrator.process_all_data(DynamicMAB())
        korean_data = all_data[all_data['본문'].apply(is_korean)].drop_duplicates(subset='본문').copy()
        shared_resources['korean_data'] = korean_data
        
    # 1-2. EmbeddingManager 로드
    emb_mgr = shared_resources.get('emb_mgr')
    if not emb_mgr:
        pkl_full_path = os.path.join(_base_path, 'embedding_migration', 'embeddings_v2_final.pkl')
        if not os.path.exists(pkl_full_path):
            pkl_full_path = os.path.join(_base_path, 'embeddings_v2_final.pkl')
        emb_mgr = EmbeddingManager(storage_path=pkl_full_path)
        shared_resources['emb_mgr'] = emb_mgr
    
    # 2. 하이브리드 회수 (Retrieval)
    print(f"\n2. 데이터 회수 및 컨텍스트 분석 시작...")
    
    filtered_subset = pd.DataFrame()
    query_vec = None
    
    if original_copy and input_image_urls:
        print(f"   🔍 [Case 3] 2D Alpha Score (Multi) 회수 중... (Sim 30% : MSS 70%)")
        query_vec = emb_mgr.get_multimodal_embedding(text=original_copy, image_paths_or_urls=input_image_urls)
    elif input_image_urls:
        print(f"   🔍 [Case 2] 2D Alpha Score (Visual) 회수 중... (Sim 30% : MSS 70%)")
        query_vec = emb_mgr.get_visual_embedding(input_image_urls)
    else:
        print(f"   🔍 [Case 1] 2D Alpha Score (Text) 회수 중... (Sim 30% : MSS 70%)")
        query_vec = emb_mgr.get_text_embedding(original_copy)

    valid_indices = []
    vectors = []
    mss_values = []
    
    for idx, row in korean_data.iterrows():
        text = str(row.get('본문', '')).strip()
        link_key = str(row['링크']).strip() if '링크' in row and pd.notna(row['링크']) else ''
        
        # 캡슐화된 캐시 조회 (해시 → 원문 → 링크 키 순 폴백)
        vec = emb_mgr._cache_lookup('text', text)
        if vec is None:
            vec = emb_mgr._cache_lookup('multi', text)
        if vec is None:
            vec = emb_mgr._cache_lookup('visual', text)
        # 링크 키로도 시도 (마이그레이션 데이터가 링크를 키로 저장한 경우)
        if vec is None and link_key:
            for e_type in ('text', 'multi', 'visual'):
                bucket = emb_mgr.embeddings.get(e_type, {})
                if link_key in bucket:
                    vec = bucket[link_key]
                    break
            
        if vec is not None:
            valid_indices.append(idx)
            vectors.append(vec)
            mss_values.append(row['MSS'])

    if valid_indices and query_vec is not None:
        arr = np.array(vectors)
        mss_arr = np.array(mss_values)
        if len(arr) > 0 and len(query_vec) == arr.shape[1]:
            # 유사도 계산
            sims = np.dot(arr, query_vec) / (np.linalg.norm(arr, axis=1) * np.linalg.norm(query_vec) + 1e-10)
            
            # 백분위 점수화
            sims_pct = rankdata(sims) / len(sims) * 100
            mss_pct = rankdata(mss_arr) / len(mss_arr) * 100
            
            # Alpha Score (유사도 30%, MSS 70% 최적화 비율 반영)
            alpha_scores = (sims_pct * 0.3) + (mss_pct * 0.7)
            
            # 상위 100개 확보 (대조학습, 채점 참조 등 충분한 후보 풀)
            top_k = min(100, len(alpha_scores))
            top_k_indices = np.argsort(alpha_scores)[-top_k:][::-1]
            idx_list = [valid_indices[i] for i in top_k_indices]
            
            filtered_subset = korean_data.loc[idx_list].copy()
            # Alpha Score 열 저장 (내림차순 정렬 상태)
            filtered_subset['alpha_score'] = [alpha_scores[i] for i in top_k_indices]
            
            print(f"   ✅ [Alpha Score Sort] {len(filtered_subset)}개 최정예 데이터 확보 완료 (최고점: {filtered_subset.iloc[0]['alpha_score']:.1f})")

    if filtered_subset is None or filtered_subset.empty:
        print(f"   ⚠️ 회수된 데이터가 없어 전체 데이터 중 고성과 10개를 사용합니다.")
        filtered_subset = korean_data.nlargest(10, 'MSS')

    best_similar_posts = filtered_subset.head(10)
    top_examples_for_gen = best_similar_posts[['본문', 'MSS']].to_dict('records')
    generator = DynamicCopyGenerator(top_examples_for_gen)
    contrastive = ContrastivePrompter(embedding_manager=emb_mgr, all_data=korean_data)
    
    # 3. MAB Prior Injection (Contextual Weighting)
    print("\n3. MAB 사전 지식(Contextual Prior) 주입 중...")
    mab = DynamicMAB()
    for s_name, _ in STATIC_STRATEGIES:
        mab.add_arm(s_name)
    
    # 회수된 고성과 데이터의 '전략(arm_name)'이 있다면 가중치 부여
    context_weights = {s_name: 1.0 for s_name, _ in STATIC_STRATEGIES}
    if 'arm_name' in filtered_subset.columns:
        top_arms = best_similar_posts['arm_name'].value_counts()
        for arm, count in top_arms.items():
            if arm in context_weights:
                context_weights[arm] += (count * 0.5) # 개당 50% 가중치 상승
    
    # 4. 전략 추출 및 카피 생성 (Pipelining)
    print("\n4. 전략 추출 및 카피 생성...")
    scorer = shared_resources.get('scorer')
    if not scorer:
        scorer = CopyScorerV4()
        shared_resources['scorer'] = scorer
    
    # 원본 채점 (멀티모달) — None 방어
    orig_vec = emb_mgr.get_multimodal_embedding(text=original_copy, image_paths_or_urls=input_image_urls) if input_image_urls else emb_mgr.get_text_embedding(original_copy)
    if orig_vec is None:
        print("    ⚠️ 원본 카피 임베딩 실패 → 0점 기본값으로 진행합니다.")
        orig_vec = np.zeros(3072)
    orig_scores = scorer.score_candidates(np.array([orig_vec]))
    
    scored = [{
        "success": True, 
        "cid": "Original", 
        "copy": original_copy, 
        "score_data": orig_scores[0],
        "total_score": orig_scores[0]['total_score']
    }]
    
    # 이미지/맥락이 일치하는 'Low' 성과 데이터를 찾기 위해 
    # 전체 데이터가 아닌 filtered_subset(0.8+ Visual 혹은 0.7+ Multi) 내에서 검색
    contrastive_restricted = ContrastivePrompter(embedding_manager=emb_mgr, all_data=filtered_subset)
    
    dynamic_pairs = []
    for _, row in best_similar_posts.head(5).iterrows():
        # High 포스트와 가장 텍스트가 비슷하면서 MSS는 낮은 것을 filtered_subset 내에서 탐색
        low_text, low_mss = contrastive_restricted._find_dynamic_contrastive_pair(row['본문'], row['MSS'])
        if low_text:
            dynamic_pairs.append({'high_text': row['본문'], 'high_mss': row['MSS'], 'low_text': low_text, 'low_mss': low_mss})

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        strat_future = executor.submit(extract_dynamic_all, client, MODEL, product_focus, dynamic_pairs, STATIC_STRATEGIES)
        
        # MAB를 활용한 정적 전략 우선순위 결정
        prioritized_static = []
        for _ in range(len(STATIC_STRATEGIES)):
            selected = mab.select_arm(context_weights=context_weights)
            if selected and selected not in [p[0] for p in prioritized_static]:
                desc = next(d for n, d in STATIC_STRATEGIES if n == selected)
                prioritized_static.append((selected, desc))
            # 톰슨 샘플링이므로 실제로는 다양하게 섞임
        
        generation_futures = {}
        prevent_insight = None
        
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

        push_tasks(prioritized_static, start_idx_offset=10)
        
        dynamic_done = False
        while len(generation_futures) > 0 or not dynamic_done:
            if strat_future.done() and not dynamic_done:
                dynamic_raw = strat_future.result()
                dynamic_done = True
                if dynamic_raw:
                    d_strats = []
                    # ... (필드 추출 로직은 기존과 동일하되 d_strats에 추가)
                    res_a = extract_fields(get_block(dynamic_raw, "전략 A]", "전략 B]"))
                    if res_a: d_strats.append((f"[동적A] {res_a[0]}", res_a[1]))
                    res_b = extract_fields(get_block(dynamic_raw, "전략 B]", "전략 C]"))
                    if res_b: d_strats.append((f"[동적B] {res_b[0]}", res_b[1]))
                    res_c = extract_fields(get_block(dynamic_raw, "전략 C]", "금기 사항"))
                    if res_c: d_strats.append((f"[하이브리드C] {res_c[0]}", res_c[1]))
                    push_tasks(d_strats, start_idx_offset=0)

            done_futs, _ = concurrent.futures.wait(generation_futures.keys(), timeout=0.1, return_when=concurrent.futures.FIRST_COMPLETED)
            for fut in list(done_futs):
                if fut in generation_futures:
                    task_info = generation_futures.pop(fut)
                    res = fut.result()
                    if res["success"]:
                        for i, t_copy in enumerate(res["copies"]):
                            t_copy = clean_marketing_text(t_copy)
                            time.sleep(1.5)
                            
                            if target_img:
                                c_vec = emb_mgr.get_multimodal_embedding(text=t_copy, image_paths_or_urls=[target_img])
                            else:
                                c_vec = emb_mgr.get_text_embedding(t_copy)
                            
                            if c_vec is None:
                                print(f"    ⚠️  [{res['cid']}] 임베딩 실패 (None). 점수 0점 처리.")
                                continue

                            ai_results = scorer.score_candidates(np.array([c_vec]))
                            ai_res = ai_results[0]
                            
                            c_suffix = "_A" if i == 0 else "_B"
                            item = {
                                "cid": res["cid"] + c_suffix, 
                                "copy": t_copy, 
                                "strategy": res["strategy"],
                                "score_data": ai_res,
                                "total_score": ai_res['total_score']
                            }
                            scored.append(item)
                            gen_times.append(res["time"])
                            
                            h_mark = "⭐" if ai_res['pass_hurdle'] else "  "
                            print(f"   ✅ [{res['cid']+c_suffix:>8}] {ai_res['total_score']:>5.1f} {h_mark} | {t_copy[:30]}...")

    # 최종 랭킹 정렬 및 최정예 1위 선발
    scored = sorted(scored, key=lambda x: x['total_score'], reverse=True)
    top_3 = scored[:3]
    
    # Tournament re-ranking — 캐시된 임베딩 재사용 (API 재호출 불필요)
    final_candidates_vecs = []
    for item in scored[:10]:
        if target_img:
            v = emb_mgr.get_multimodal_embedding(text=item['copy'], image_paths_or_urls=[target_img])
        else:
            v = emb_mgr.get_text_embedding(item['copy'])
        if v is None: v = np.zeros(3072)
        final_candidates_vecs.append(v)
    
    if final_candidates_vecs:
        # 벤치마크 대상(Original) 인덱스 찾기
        orig_idx_in_final = next((i for i, item in enumerate(scored[:10]) if item['cid'] == 'Original'), None)
        
        refined_scores = scorer.score_candidates(np.array(final_candidates_vecs), orig_index=orig_idx_in_final)
        for i, r_score in enumerate(refined_scores):
            # refined_scores의 인덱스가 원래 scored 리스트의 순서와 일치하지 않으므로 (score_candidates가 정렬해서 반환함)
            # 여기서는 r_score['index']를 사용하여 원래 item을 찾아 업데이트해야 함
            orig_idx = r_score['index']
            scored[orig_idx]['total_score'] = r_score['total_score']
            scored[orig_idx]['score_data'] = r_score
            
    scored = sorted(scored, key=lambda x: x['total_score'], reverse=True)
    
    # [Benchmark Report] 원본 순위 분석
    orig_rank = next((i+1 for i, item in enumerate(scored) if item['cid'] == 'Original'), -1)
    
    top_1_reg = scored[0]['score_data'].get('reg_score', 0) if len(scored) > 0 else 0
    top_2_reg = scored[1]['score_data'].get('reg_score', 0) if len(scored) > 1 else 0

    print(f"\n📊 [성과 벤치마크] 원본 통합 순위: {orig_rank}위 / {len(scored)}개 중")
    print(f"   🏆 1위 회귀 점수: {top_1_reg:.1f} | 2위 회귀 점수: {top_2_reg:.1f}")
    
    if orig_rank == 1:
        print(f"   ✨ 원본 카피가 실전 대결 승격 및 리그전을 통해 최종 1위를 수성했습니다!")
    elif orig_rank <= 5:
        print(f"   🚀 원본이 상위권({orig_rank}위)에 입성했습니다. (엘리트 리그전 진출)")
    else:
        print(f"   ⚠️ 원본보다 실질적 성과가 높은 AI 카피가 {orig_rank-1}개 발견되었습니다.")

    print(f"\n🏁 최적화 완료! (총 {len(scored)}개 분석, 소요시간: {time.time()-t_start:.1f}초)")
    return scored[:3]

def main():
    # 수동 모드일 때는 app_config.py의 하드코딩된 변수를 사용합니다.
    run_optimization(ORIGINAL_COPY, PRODUCT_FOCUS)

if __name__ == "__main__":
    main()
