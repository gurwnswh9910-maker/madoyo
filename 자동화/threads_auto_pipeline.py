import os
import sys
import io
import time
import random
import glob
import shutil
import argparse
import requests
import json
import gc
import pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import tempfile
AUTO_DIR = Path(__file__).resolve().parent
BASE_DIR = AUTO_DIR.parent
CODE_DIR = BASE_DIR / "작동중코드"
# 공유 환경에서는 외장 드라이브를 전제하지 않도록 repo 내부 tmp를 사용합니다.
temp_path = BASE_DIR / "tmp" / "madoyo_temp"
temp_path.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(temp_path)

# UTF-8 출력 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

from dotenv import load_dotenv
# [중요] 시스템 환경변수(터미널 설정) 우선권을 보장하기 위해 override=False 명시
load_dotenv(override=False) 

from google import genai
sys.path.insert(0, str(AUTO_DIR)); sys.path.insert(0, str(CODE_DIR))

from app_config import GlobalConfig
from scraper import (
    scrape_thread_content, scrape_comment_for_coupang, fetch_and_rehost,
    init_driver, fetch_coupang_product_info
)
from coupang_api import extract_and_convert_coupang_link
from publisher import upload_to_threads
from content_guard import (
    DEFAULT_MAX_BODY_LINES,
    DEFAULT_MAX_REPLY_LINES,
    MAX_THREADS_TEXT_LENGTH,
    get_text_rejection,
    rejection_category,
)
from optimize_copy_v2 import run_optimization
from marketing_focus_extractor import extract_marketing_focus
from post_cache import (
    STRONG_ORIGINAL_RANK_THRESHOLD,
    prepare_post_cache,
    persist_post_record,
    rebuild_index_from_metadata,
    write_json_file,
    write_text_file,
)

REF_DIR = GlobalConfig.AUTOMATION_DIR / '자동화참조'
DONE_DIR = REF_DIR / '업로드완료'
PROCESSED_LOG = GlobalConfig.PROCESSED_LOG_PATH
STOP_SIGNAL_FILE = GlobalConfig.AUTOMATION_DIR / "stop.txt"
# [설정] 계정별 이번 세션 최대 포스팅 제한 (None은 무제한)
ACCOUNT_LIMITS = {
    # "1": 10,
    # "2": None,
    # "3": None,
}
DRIVER_RECYCLE_EVERY = 8
DRIVER_RECYCLE_PAUSE = 1
ACCOUNT_PROTECTION_ERROR_CATEGORIES = {"account_restricted", "action_blocked"}
NON_ACCOUNT_FAILURE_CATEGORIES = {
    "text_missing",
    "coupang_missing",
    "coupang_blocked",
    "deeplink_failed",
    "rehost_failed",
    "media_uri_unavailable",
    "media_count_insufficient",
    "content_length_over_limit",
    "content_hygiene_rejected",
}

def check_stop_signal(): return STOP_SIGNAL_FILE.exists()
def load_processed_links(account_name):
    log_path = GlobalConfig.AUTOMATION_DIR / f"processed_{account_name.lower()}.log"
    if not log_path.exists(): return set()
    return set(line.strip() for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip())

def log_processed_link(account_name, url):
    log_path = GlobalConfig.AUTOMATION_DIR / f"processed_{account_name.lower()}.log"
    with log_path.open("a", encoding="utf-8") as f: f.write(url.strip() + "\n")
def shorten_url(url):
    try:
        r = requests.get(f"https://is.gd/create.php?format=json&url={requests.utils.quote(url)}", timeout=5)
        if r.status_code == 200: return r.json().get("shorturl", url)
    except: pass
    return url


def close_driver_quietly(driver):
    if not driver:
        return
    try:
        driver.quit()
    except:
        pass


def recycle_driver(driver, reason, pause_seconds=DRIVER_RECYCLE_PAUSE):
    print(f"  [Driver] 세션 정리 후 재시작: {reason}", flush=True)
    close_driver_quietly(driver)
    gc.collect()
    if pause_seconds > 0:
        time.sleep(pause_seconds)
    return init_driver()

def build_process_result(
    success_accounts,
    failed_accounts,
    *,
    is_blocked=False,
    failure_category=None,
    failed_account_details=None,
):
    return {
        "success_accounts": success_accounts,
        "failed_accounts": failed_accounts,
        "is_blocked": is_blocked,
        "failure_category": failure_category,
        "failed_account_details": failed_account_details or {},
    }


def build_content_rejection_result(field_name, rejection):
    category = rejection_category(rejection["reason"])
    text_length = rejection.get("text_length", 0)
    max_length = rejection.get("max_length", MAX_THREADS_TEXT_LENGTH)
    return {
        "ok": False,
        "stage": "preflight",
        "error_category": category,
        "error_code": None,
        "error_subcode": None,
        "error_message": (
            f"{field_name} 위생 컷({rejection['reason']}): "
            f"{text_length}자 / 최대 {max_length}자. API 호출 전 강제폐기"
        ),
        "field_name": field_name,
        "text_length": text_length,
        "max_text_length": max_length,
        "rejection_reason": rejection["reason"],
    }


class CoupangBlockedError(RuntimeError):
    pass


def resolve_coupang_payload(raw_url, driver):
    p_page = fetch_coupang_product_info(raw_url, driver=driver)
    pname = p_page.get('product_name', '상품')
    c_img = p_page.get('image_url', '')
    is_blocked = p_page.get('is_blocked', False)

    # Akamai가 상품 페이지 렌더링을 막아도 Partners deeplink API는 별도 경로라 시도할 수 있다.
    resolved_url = None if is_blocked else p_page.get('product_url')
    s_url = extract_and_convert_coupang_link(raw_url, resolved_url=resolved_url)
    if not s_url:
        print(f"    ⚠️ [Fallback] 딥링크 생성 실패! 원본 대체 방지 정책에 따라 상품명으로 Search API 폴백 시도: '{pname}'")
        from coupang_api import search_coupang_product
        search_res = search_coupang_product(pname, limit=5)
        if search_res and search_res.get("product_url"):
            s_url = search_res["product_url"]
            print(f"    ✅ [Fallback] Search API를 통한 우회 수익 링크 발급 성공")

    return {
        "p_page": p_page,
        "pname": pname,
        "c_img": c_img,
        "s_url": s_url,
        "is_blocked": is_blocked,
    }


def rebuild_post_index_quietly(stage_label):
    try:
        count = rebuild_index_from_metadata()
        print(f"🗂️ [PostCache] {stage_label} post_index.xlsx 재빌드 완료 ({count}건)", flush=True)
    except Exception as e:
        print(f"⚠️ [PostCache] {stage_label} 인덱스 재빌드 실패: {e}", flush=True)

def process_single_link(url_data, client, accounts_creds, dry_run, idx, total, threads_driver=None, coupang_driver=None, coupang_executor=None, optimization_shared_resources=None):
    url = url_data.get("url"); excel_body = url_data.get("body", "")
    account_names = [acc_name for acc_name, _, _ in accounts_creds]
    cache_info = prepare_post_cache(url)
    artifacts_dir = cache_info["artifacts_dir"]

    persist_post_record(
        cache_info,
        {
            "status": "started",
            "last_stage": "start",
            "target_accounts": account_names,
            "success_accounts": [],
            "failed_accounts": account_names,
            "error_message": "",
        },
    )

    try:
        account_label = ", ".join(account_names)
        print(f"\n─────────────────────────────────────────────────────────────────")
        print(f"[{account_label}] [{idx}/{total}] {url}", flush=True)

        # 🚀 [1/5] 쓰레드 콘텐츠 및 미디어 수집
        print("  [1/5] 쓰레드 원본 자료 수집 중...", flush=True)
        t_info = scrape_thread_content(url, driver=threads_driver)
        raw_imgs = t_info.get("images", [])
        raw_vids = t_info.get("video_urls", [])
        source_media_urls = t_info.get("all_media", []) or (raw_imgs + raw_vids)
        orig = t_info.get("text", "").strip() or excel_body.strip()
        original_copy_path = None
        if orig:
            original_copy_path = write_text_file(cache_info["post_dir"] / "original_copy.txt", orig)

        persist_post_record(
            cache_info,
            {
                "status": "scraped",
                "last_stage": "scrape",
                "original_copy": orig,
                "original_copy_path": original_copy_path,
                "source_media_count": len(source_media_urls),
                "cached_media_count": 0,
                "source_media_urls": source_media_urls,
                "source_media_files": [],
                "error_message": "",
            },
        )

        if not orig:
            print("  ⚠️ [스킵] 본문 텍스트를 수집하지 못했습니다.", flush=True)
            persist_post_record(
                cache_info,
                {
                    "status": "text_missing",
                    "last_stage": "scrape",
                    "error_message": "본문 텍스트를 수집하지 못했습니다.",
                },
            )
            return build_process_result(
                [],
                account_names,
                failure_category="text_missing",
            )
        print(f"    > 본문({len(orig)}자): {orig[:40]}...", flush=True)
        print(f"    > 미디어: 이미지 {len(raw_imgs)}개, 영상 {len(raw_vids)}개", flush=True)

        # 🚀 [2/5] 쿠팡 상품 정보 수집
        print("  [2/5] 쿠팡 상품 정보 수집 중...", flush=True)
        coupang_urls = t_info.get("coupang_urls", [])
        if not coupang_urls:
            c_res = scrape_comment_for_coupang(url, driver=threads_driver)
            coupang_urls = c_res.get("coupang_urls", []) if c_res else []
        raw_url = ""
        p_page = {}
        pname = "상품"
        c_img = ""
        s_url = ""
        is_blocked = False
        if not coupang_urls:
            persist_post_record(
                cache_info,
                {
                    "status": "coupang_missing",
                    "last_stage": "coupang_lookup",
                    "error_message": "쿠팡 링크를 찾지 못했습니다.",
                },
            )
            return build_process_result(
                [],
                account_names,
                failure_category="coupang_missing",
            )
        else:
            raw_url = coupang_urls[0]
            print(f"    > 쿠팡 링크: {raw_url}", flush=True)
            print("    [쿠팡] 별도 브라우저에서 상품/딥링크 처리 시작", flush=True)
            coupang_future = coupang_executor.submit(resolve_coupang_payload, raw_url, coupang_driver)

            p_media = fetch_and_rehost(source_media_urls, driver=threads_driver, video_urls=raw_vids)
            try:
                coupang_payload = coupang_future.result()
            except CoupangBlockedError as e:
                print(f"    ❌ [쿠팡 차단] {e}. 이번 배치를 중단합니다.", flush=True)
                persist_post_record(
                    cache_info,
                    {
                        "status": "coupang_blocked",
                        "last_stage": "coupang_lookup",
                        "coupang_raw_url": raw_url,
                        "error_message": str(e),
                    },
                )
                raise
            p_page = coupang_payload["p_page"]
            pname = coupang_payload["pname"]
            c_img = coupang_payload["c_img"]
            is_blocked = bool(coupang_payload.get("is_blocked", False))
            s_url = coupang_payload["s_url"]
            coupang_status = "coupang_blocked_continue" if is_blocked else "coupang_ready"
            persist_post_record(
                cache_info,
                {
                    "status": coupang_status,
                    "last_stage": "coupang_lookup",
                    "product_name": pname,
                    "coupang_raw_url": raw_url,
                    "coupang_product_url": p_page.get("product_url", ""),
                    "product_image_url": c_img,
                    "product_image_local_path": "",
                    "error_message": "쿠팡 Akamai Access Denied 감지, 딥링크로 업로드 계속" if is_blocked else "",
                },
            )
            print(f"    > 상품명: {pname[:35]}... / 차단여부: {is_blocked}", flush=True)

        # 🚀 [3/5] 딥링크 생성 및 미디어 선(先) 보호(재호스팅)
        print("  [3/5] 딥링크 생성 및 미디어 선 재호스팅 완료 확인 중...", flush=True)
        
        # [궁극의 폴백] 파트너스 링크 변환 실패 시 무조건 Search API로 내 수익 링크 복구를 시도합니다.
        # 주의: 이 경우 원본 링크(raw_url) 유출(남 수익)을 철저히 차단합니다.
        if not s_url:
            print("    ❌ [Skipped] 딥링크 발급 실패로 업로드를 건너뜁니다.", flush=True)
            persist_post_record(
                cache_info,
                {
                    "status": "deeplink_failed",
                    "last_stage": "deeplink",
                    "coupang_raw_url": raw_url,
                    "error_message": "파트너스 딥링크 발급 실패로 인한 스킵",
                },
            )
            return build_process_result(
                [],
                account_names,
                is_blocked=is_blocked,
                failure_category="deeplink_failed",
            )
        rehosted_media_path = write_json_file(
            artifacts_dir / "rehosted_media.json",
            {"rehosted_media_urls": p_media},
        )

        persist_post_record(
            cache_info,
            {
                "status": "rehost_completed",
                "last_stage": "rehost",
                "coupang_deep_link": s_url,
                "rehosted_media_count": len(p_media),
                "rehosted_media_urls": p_media,
                "rehosted_media_path": rehosted_media_path,
                "error_message": "",
            },
        )
        
        # [무결성 체크] 최소 2개 이상 미디어 원칙 준수
        if not p_media or len(p_media) < 2:
            print(f"  ❌ [무결성 오류] 미디어 확보 실패 (기대: 2개 이상, 실제: {len(p_media if p_media else [])}개)")
            persist_post_record(
                cache_info,
                {
                    "status": "rehost_failed",
                    "last_stage": "rehost",
                    "error_message": f"재호스팅 미디어 개수 부족 ({len(p_media if p_media else [])}개)",
                },
            )
            return build_process_result(
                [],
                account_names,
                is_blocked=is_blocked,
                failure_category="rehost_failed",
            )

        # 🚀 [4/5] AI 카피 최적화 (재호스팅된 반영구 링크 및 쿠팡 이미지를 AI에 전달)
        print("  [4/5] 이미지 기반 카피 최적화 중...", flush=True)
        # 쿠팡 상품 이미지가 있으면 함께 전달하여 소구점을 더 정확히 분석하게 함
        m_focus = extract_marketing_focus(client, GlobalConfig.MODEL_NAME, pname, orig, p_media, coupang_images=[c_img] if c_img else None)
        marketing_focus_path = write_json_file(artifacts_dir / "marketing_focus.json", m_focus)
        persist_post_record(
            cache_info,
            {
                "status": "optimization_pending",
                "last_stage": "marketing_focus",
                "marketing_focus_path": marketing_focus_path,
                "error_message": "",
            },
        )

        optimization_payload = run_optimization(
            original_copy=orig,
            product_focus=m_focus,
            input_image_urls=p_media + ([c_img] if c_img else []),
            shared_resources=optimization_shared_resources,
            return_metadata=True,
        )
        if isinstance(optimization_payload, dict) and "top_results" in optimization_payload:
            opt_list = optimization_payload.get("top_results", [])
            opt_meta = optimization_payload.get("meta", {})
        else:
            opt_list = optimization_payload
            opt_meta = {}

        optimization_path = write_json_file(artifacts_dir / "optimization_result.json", optimization_payload)
        duplicate_filter_log_path = write_json_file(
            artifacts_dir / "duplicate_filter_log.json",
            {
                "duplicate_similarity_threshold": opt_meta.get("duplicate_similarity_threshold"),
                "duplicate_rejection_count": opt_meta.get("duplicate_rejection_count", 0),
                "duplicate_rejected_pairs": opt_meta.get("duplicate_rejected_pairs", []),
            },
        )
        # 1등 카피를 기본 메타로 유지 (이전 호환성)
        final_txt = (opt_list[0]['copy'] if opt_list and isinstance(opt_list, list) and len(opt_list) > 0 else orig).strip()
        
        # [Config 분리] 답글 양식을 중앙 설정 파일(app_config.py)에서 불러옵니다.
        r_txt = GlobalConfig.REPLY_TEMPLATE.format(s_url=s_url) if s_url else None
        reply_rejection = None
        if r_txt:
            reply_rejection = get_text_rejection(
                r_txt,
                reject_repeated=True,
                reject_meta=True,
                reject_urls=False,
                reject_disclosure=False,
                max_lines=DEFAULT_MAX_REPLY_LINES,
                min_hangul_chars=5,
            )
        if reply_rejection is not None:
            upload_result = build_content_rejection_result("첫댓글", reply_rejection)
            print(f"  ⛔ [강제폐기] {upload_result['error_message']}", flush=True)
            failed_account_details = {acc_name: dict(upload_result) for acc_name in account_names}
            persist_post_record(
                cache_info,
                {
                    "status": upload_result["error_category"],
                    "last_stage": "preflight",
                    "success_accounts": [],
                    "failed_accounts": account_names,
                    "failed_account_details": failed_account_details,
                    "reply_text_length": upload_result["text_length"],
                    "reply_rejection_reason": upload_result["rejection_reason"],
                    "error_message": upload_result["error_message"],
                },
            )
            return build_process_result(
                [],
                account_names,
                failure_category=upload_result["error_category"],
                failed_account_details=failed_account_details,
            )
        
        original_rank = opt_meta.get("original_rank", -1)
        is_original_strong = 0 < original_rank <= STRONG_ORIGINAL_RANK_THRESHOLD

        persist_post_record(
            cache_info,
            {
                "status": "ready_to_publish",
                "last_stage": "optimization",
                "optimization_path": optimization_path,
                "original_rank": original_rank,
                "is_original_strong": is_original_strong,
                "strong_reason": f"original_rank<={STRONG_ORIGINAL_RANK_THRESHOLD}" if is_original_strong else "",
                "candidate_count_before_filter": opt_meta.get("candidate_count_before_filter", 0),
                "candidate_count_after_filter": opt_meta.get("candidate_count_after_filter", len(opt_list) if isinstance(opt_list, list) else 0),
                "duplicate_similarity_threshold": opt_meta.get("duplicate_similarity_threshold", 0),
                "duplicate_rejection_count": opt_meta.get("duplicate_rejection_count", 0),
                "duplicate_rejected_pairs": opt_meta.get("duplicate_rejected_pairs", []),
                "duplicate_filter_log_path": duplicate_filter_log_path,
                "embedding_cache_hits": opt_meta.get("embedding_cache_hits", 0),
                "embedding_cache_misses": opt_meta.get("embedding_cache_misses", 0),
                "embedding_cache_size": opt_meta.get("embedding_cache_size", 0),
                "rerank_reused_embedding_count": opt_meta.get("rerank_reused_embedding_count", 0),
                "generation_sibling_count": opt_meta.get("generation_sibling_count", 0),
                "generation_output_mode": opt_meta.get("generation_output_mode", ""),
                "static_strategy_count": opt_meta.get("static_strategy_count", 0),
                "dynamic_strategy_count": opt_meta.get("dynamic_strategy_count", 0),
                "static_generation_task_count": opt_meta.get("static_generation_task_count", 0),
                "dynamic_generation_task_count": opt_meta.get("dynamic_generation_task_count", 0),
                "scheduled_generation_tasks": opt_meta.get("scheduled_generation_tasks", 0),
                "completed_generation_tasks": opt_meta.get("completed_generation_tasks", 0),
                "successful_generation_tasks": opt_meta.get("successful_generation_tasks", 0),
                "failed_generation_tasks": opt_meta.get("failed_generation_tasks", 0),
                "expected_generated_copy_count": opt_meta.get("expected_generated_copy_count", 0),
                "returned_generated_copy_count": opt_meta.get("returned_generated_copy_count", 0),
                "accepted_generated_copy_count": opt_meta.get("accepted_generated_copy_count", 0),
                "undersized_generation_tasks": opt_meta.get("undersized_generation_tasks", 0),
                "undersized_generation_details": opt_meta.get("undersized_generation_details", []),
                "generation_failures": opt_meta.get("generation_failures", []),
                "final_copy": final_txt,
                "selected_copy_source": "optimized_best_candidate",
                "error_message": "",
            },
        )

        if dry_run:
            persist_post_record(
                cache_info,
                {
                    "status": "dry_run_completed",
                    "last_stage": "dry_run",
                    "success_accounts": account_names,
                    "failed_accounts": [],
                },
            )
            return build_process_result(
                account_names,
                [],
                is_blocked=is_blocked,
                failure_category="dry_run_completed",
            )

        # 🚀 [5/5] 최종 게시
        success_accounts = []
        failed_accounts = []
        failed_account_details = {}
        account_copy_mapping = {}

        for j, (acc_name, uid, token) in enumerate(accounts_creds):
            print(f"  [게시] {acc_name} 계정에 릴레이 업로드 중...", flush=True)
            
            # 랭크 순환 할당 로직
            if opt_list and isinstance(opt_list, list) and len(opt_list) > 0:
                # (링크 인덱스 + 계정 순서) % 전체 후보 개수를 통해서 안전하게 순환
                copy_index = ((idx - 1) + j) % len(opt_list)
                acc_final_txt = opt_list[copy_index]['copy'].strip()
                selected_rank = copy_index + 1
            else:
                acc_final_txt = orig.strip()
                selected_rank = 0
                
            account_copy_mapping[acc_name] = {
                "rank": selected_rank,
                "copy": acc_final_txt
            }
            
            print(f"    > 할당된 카피 랭크: {selected_rank}위 ({len(acc_final_txt)}자)", flush=True)

            body_rejection = get_text_rejection(
                acc_final_txt,
                reject_repeated=True,
                reject_meta=True,
                reject_urls=True,
                reject_disclosure=True,
                max_lines=DEFAULT_MAX_BODY_LINES,
                min_hangul_chars=5,
            )
            if body_rejection is not None:
                upload_result = build_content_rejection_result("본문", body_rejection)
                print(f"    ⛔ [강제폐기] {upload_result['error_message']}", flush=True)
            else:
                upload_result = upload_to_threads(uid, token, acc_final_txt, p_media, r_txt, None)
            account_copy_mapping[acc_name]["upload_result"] = {
                "ok": bool(upload_result.get("ok")),
                "stage": upload_result.get("stage"),
                "error_category": upload_result.get("error_category"),
                "error_code": upload_result.get("error_code"),
                "error_subcode": upload_result.get("error_subcode"),
                "error_message": upload_result.get("error_message", ""),
                "field_name": upload_result.get("field_name", ""),
                "text_length": upload_result.get("text_length"),
                "max_text_length": upload_result.get("max_text_length"),
                "rejection_reason": upload_result.get("rejection_reason", ""),
            }
            if upload_result.get("ok"):
                success_accounts.append(acc_name)
            else:
                failed_accounts.append(acc_name)
                failed_account_details[acc_name] = {
                    "stage": upload_result.get("stage"),
                    "error_category": upload_result.get("error_category"),
                    "error_code": upload_result.get("error_code"),
                    "error_subcode": upload_result.get("error_subcode"),
                    "error_message": upload_result.get("error_message", ""),
                    "field_name": upload_result.get("field_name", ""),
                    "text_length": upload_result.get("text_length"),
                    "max_text_length": upload_result.get("max_text_length"),
                    "rejection_reason": upload_result.get("rejection_reason", ""),
                }
            
            # 계정 간 무작위 안전 딜레이 (봇 탐지 방지, 20초~45초)
            delay_sec = random.uniform(10.0, 22.5)
            print(f"    ⏳ [안전 대기] 다음 계정 업로드 전 {delay_sec:.1f}초 대기 중...", flush=True)
            time.sleep(delay_sec)

        final_status = "posted" if not failed_accounts else "partial_post_failure"
        final_error = "" if success_accounts else "모든 대상 계정 업로드 실패"
        persist_post_record(
            cache_info,
            {
                "status": final_status,
                "last_stage": "publish",
                "success_accounts": success_accounts,
                "failed_accounts": failed_accounts,
                "account_copy_mapping": account_copy_mapping,
                "failed_account_details": failed_account_details,
                "error_message": final_error,
            },
        )

        dominant_failure_category = None
        if failed_account_details:
            dominant_failure_category = next(
                (
                    detail.get("error_category")
                    for detail in failed_account_details.values()
                    if detail.get("error_category")
                ),
                None,
            )

        return build_process_result(
            success_accounts,
            failed_accounts,
            is_blocked=is_blocked,
            failure_category=dominant_failure_category,
            failed_account_details=failed_account_details,
        )
    except CoupangBlockedError as e:
        persist_post_record(
            cache_info,
            {
                "status": "coupang_blocked",
                "last_stage": "coupang_lookup",
                "failed_accounts": account_names,
                "error_message": str(e),
            },
        )
        print(f"  ❌ [쿠팡 차단] {e}")
        return build_process_result(
            [],
            [acc_name for acc_name, _, _ in accounts_creds],
            failure_category="coupang_blocked",
        )
    except Exception as e:
        persist_post_record(
            cache_info,
            {
                "status": "error",
                "last_stage": "exception",
                "failed_accounts": account_names,
                "error_message": str(e),
            },
        )
        print(f"  ❌ [Error] {e}")
        return build_process_result(
            [],
            [acc_name for acc_name, _, _ in accounts_creds],
            failure_category="exception",
        )

def main(dry_run=False, limit=None, single_url=None, single_body="", max_links=None):
    accounts_str = os.getenv("THREADS_CURRENT_ACCOUNT", "1")
    account_names = [a.strip() for a in accounts_str.split(',') if a.strip()]
    accounts_creds = []
    
    for name in account_names:
        uid, token = GlobalConfig.get_account_credentials(name)
        if uid and token: accounts_creds.append((name, uid, token))
        
    if not accounts_creds:
        raise SystemExit(
            "업로드 가능한 계정 토큰이 없습니다. "
            "THREADS_CURRENT_ACCOUNT와 THREADS_ACCOUNT_<번호>_USER_ID/"
            "THREADS_ACCOUNT_<번호>_ACCESS_TOKEN 환경변수를 확인해주세요."
        )

    print(f"\n🌟 [타겟 계정 로드 완료] 총 {len(accounts_creds)}개 계정에 업로드됩니다: {', '.join([a[0] for a in accounts_creds])}")
    rebuild_post_index_quietly("0단계")

    excel_files = glob.glob(str(REF_DIR / "*.xlsx"))
    if not excel_files and not single_url:
        return
    client = genai.Client(api_key=GlobalConfig.GEMINI_API_KEY)
    optimization_shared_resources = {}
    links = []
    if not single_url:
        for excel in excel_files:
            links.extend(collect_links_from_excel(excel))
        if not links:
            print("⚠️ 자동화참조 엑셀에서 처리할 링크를 찾지 못했습니다.", flush=True)
            return
        if max_links is not None:
            links = links[:max_links]
            print(f"🔎 [검증 범위] 자동화참조 첫 {len(links)}개 링크만 처리합니다.", flush=True)

    processed_by_account = {}
    for acc_name, _, _ in accounts_creds:
        processed_by_account[acc_name] = load_processed_links(acc_name)
        print(
            f"🧹 [{acc_name}] 전용 중복 방지 캐시 로드 완료. "
            f"(총 {len(processed_by_account[acc_name])}개 링크 제외 대상)",
            flush=True,
        )

    # 세션별 업로드 성공 카운터 초기화
    session_counts = {acc_name: 0 for acc_name, _, _ in accounts_creds}

    print("\n🚀 브라우저 세션 초기화 (배치 공유 모드)...", flush=True)
    session_counts = {acc_name: 0 for acc_name, _, _ in accounts_creds}
    requested_success_limit = limit
    limit_notice_shown = set()
    quarantined_accounts = set()
    quarantine_notice_shown = set()

    def reached_account_cap(acc_name):
        caps = []
        account_cap = ACCOUNT_LIMITS.get(acc_name.upper())
        if account_cap is not None:
            caps.append(account_cap)
        if requested_success_limit is not None:
            caps.append(requested_success_limit)
        if not caps:
            return False
        return session_counts.get(acc_name, 0) >= min(caps)

    threads_driver = None
    coupang_driver = None
    coupang_executor = None
    print("Threads 브라우저 세션 초기화...", flush=True)
    threads_driver = init_driver()
    print("Coupang 전용 브라우저 세션 초기화...", flush=True)
    coupang_driver = init_driver()
    coupang_executor = ThreadPoolExecutor(max_workers=1)
    try:
        if single_url:
            result = process_single_link(
                {"url": single_url, "body": single_body or ""},
                client,
                accounts_creds,
                dry_run,
                1,
                1,
                threads_driver=threads_driver,
                coupang_driver=coupang_driver,
                coupang_executor=coupang_executor,
                optimization_shared_resources=optimization_shared_resources,
            )
            success_accounts = result.get("success_accounts", [])
            if success_accounts:
                for acc_name in success_accounts:
                    if dry_run:
                        print(f"  🧪 [Dry Run] {acc_name} processed log 기록은 건너뜁니다.", flush=True)
                    else:
                        log_processed_link(acc_name, single_url)
            return

        consecutive_blocks = 0
        shadow_ban_counter = 0
        links_since_recycle = 0
        links_since_long_nap = 0
        next_nap_threshold = random.randint(5, 7)
        for i, item in enumerate(links):
            if check_stop_signal(): return # 파일 단위 정지 시그널 즉시 반영

            if requested_success_limit is not None and all(
                reached_account_cap(acc_name) for acc_name, _, _ in accounts_creds
            ):
                print(
                    f"✅ 요청한 성공 기준 업로드 수({requested_success_limit}건)에 도달하여 종료합니다.",
                    flush=True,
                )
                return

            if all(
                reached_account_cap(acc_name) or acc_name in quarantined_accounts
                for acc_name, _, _ in accounts_creds
            ):
                print("✅ 이번 런에서 더 진행 가능한 계정이 없어 종료합니다.", flush=True)
                return

            target_accounts = []
            for acc_name, uid, token in accounts_creds:
                if acc_name in quarantined_accounts:
                    continue

                # 1. 이미 처리한 링크인지 확인
                if item['url'] in processed_by_account[acc_name]:
                    continue
                
                # 2. 계정별 세션 제한 도달 확인
                account_limit = ACCOUNT_LIMITS.get(acc_name.upper())
                if reached_account_cap(acc_name):
                    # 처음 제한에 도달했을 때만 한 번 출력 (매 링크마다 출력 방지)
                    if acc_name not in limit_notice_shown:
                        print(f"  🚫 [{acc_name}] 이번 세션 제한({account_limit}개) 도달로 제외됩니다.", flush=True)
                        limit_notice_shown.add(acc_name)
                    continue
                
                target_accounts.append((acc_name, uid, token))

            if not target_accounts:
                continue

            # 봇 탐지 방어를 위해 업로드 순서 무작위 섞기 (Non-Sequential)
            random.shuffle(target_accounts)

            result = process_single_link(
                item,
                client,
                target_accounts,
                dry_run,
                i+1,
                len(links),
                threads_driver=threads_driver,
                coupang_driver=coupang_driver,
                coupang_executor=coupang_executor,
                optimization_shared_resources=optimization_shared_resources,
            )
            links_since_recycle += 1
            success_accounts = result.get("success_accounts", [])
            failed_accounts = result.get("failed_accounts", [])
            blocked = result.get("is_blocked", False)
            failure_category = result.get("failure_category")
            failed_account_details = result.get("failed_account_details", {})

            handled_account_protection = False
            for acc_name, detail in failed_account_details.items():
                category = detail.get("error_category")
                if category in ACCOUNT_PROTECTION_ERROR_CATEGORIES:
                    quarantined_accounts.add(acc_name)
                    handled_account_protection = True
                    if acc_name not in quarantine_notice_shown:
                        subcode = detail.get("error_subcode")
                        print(
                            f"  🛡️ [{acc_name}] 제한 신호({category}, subcode={subcode}) 감지로 이번 런에서 격리합니다.",
                            flush=True,
                        )
                        quarantine_notice_shown.add(acc_name)

            if success_accounts:
                for acc_name in success_accounts:
                    if dry_run:
                        print(f"  🧪 [Dry Run] {acc_name} processed log 기록은 건너뜁니다.", flush=True)
                    else:
                        log_processed_link(acc_name, item['url'])
                    processed_by_account[acc_name].add(item['url'])
                    # 포스팅 성공 시 세션 카운트 증가
                    if acc_name in session_counts:
                        # 이미 메시지를 출력한 상태(limit + 1)가 아닐 때만 정상 증가
                        account_limit = ACCOUNT_LIMITS.get(acc_name.upper())
                        if account_limit is None or session_counts[acc_name] < account_limit:
                            session_counts[acc_name] += 1
                consecutive_blocks = 0
                shadow_ban_counter = 0
                if failed_accounts:
                    print(f"  ⚠️ 일부 계정 업로드 실패: {', '.join(failed_accounts)}", flush=True)
                if not dry_run: time.sleep(GlobalConfig.POST_INTERVAL)
            else:
                if blocked:
                    consecutive_blocks += 1
                    if consecutive_blocks >= 2:
                        print("  🚨 연속 차단 발생! 세션을 갱신합니다.", flush=True)
                        threads_driver = recycle_driver(threads_driver, "연속 차단 감지")
                        consecutive_blocks = 0
                        links_since_recycle = 0
                elif handled_account_protection:
                    consecutive_blocks = 0
                    shadow_ban_counter = 0
                elif failure_category in NON_ACCOUNT_FAILURE_CATEGORIES:
                    consecutive_blocks = 0
                    shadow_ban_counter = 0
                    print(
                        f"  ℹ️ 계정 제한이 아닌 실패({failure_category})로 판단해 보호 카운터는 올리지 않습니다.",
                        flush=True,
                    )
                else: 
                    consecutive_blocks = 0
                    # API 블락/섀도우 밴 위험 감지 처리
                    print(f"  ⚠️ 쉐도우 밴 위험 감지! (현재 카운터: {shadow_ban_counter}) - 사용자 지침에 따라 계속 진행합니다.", flush=True)
                    shadow_ban_counter += 1
                    if shadow_ban_counter >= 2:
                        print("  ⛔ 쉐도우 밴 위험 누적으로 계정 보호를 위해 전체 프로세스를 종료합니다.", flush=True)
                        return
                # 드라이버 생사 확인
                try:
                    threads_driver.current_url
                except:
                    threads_driver = recycle_driver(threads_driver, "드라이버 세션 손상 감지")
                    links_since_recycle = 0

            links_since_long_nap += 1
            if links_since_long_nap >= next_nap_threshold:
                nap_time = random.uniform(300, 450)  # 5분 ~ 7.5분
                print(f"\n💤 [Long Nap] 휴먼 피로도 에뮬레이션: 패턴 교란을 위해 {nap_time/60:.1f}분 동안 휴식합니다...", flush=True)
                time.sleep(nap_time)
                links_since_long_nap = 0
                next_nap_threshold = random.randint(5, 7)

            if links_since_recycle >= DRIVER_RECYCLE_EVERY:
                threads_driver = recycle_driver(threads_driver, f"{links_since_recycle}건 처리 후 메모리 정리")
                links_since_recycle = 0
                consecutive_blocks = 0
            gc.collect()
    finally:
        if coupang_executor:
            coupang_executor.shutdown(wait=False, cancel_futures=True)
        if threads_driver:
            close_driver_quietly(threads_driver)
        if coupang_driver:
            close_driver_quietly(coupang_driver)
        gc.collect()
        rebuild_post_index_quietly("종료")

    print(f"\n🎉 총 {len(accounts_creds)}개 계정 대상 업로드 배치가 성공적으로 완료되었습니다!")

    # 3. 모든 계정이 완료된 뒤에야 엑셀 파일을 '완료' 폴더로 이동 처리
    if not dry_run and limit is None and max_links is None:
        for excel in excel_files:
            move_to_done(excel)


def collect_links_from_excel(path):
    try:
        df = pd.read_excel(path, engine='openpyxl')
        l_col = next((c for c in df.columns if "링크" in str(c) or "URL" in str(c).upper()), None)
        b_col = next((c for c in df.columns if "본문" in str(c) or "TEXT" in str(c).upper()), None)
        res = []
        if l_col:
            for _, r in df.iterrows():
                u = str(r[l_col]).strip()
                if u.startswith("http"): res.append({"url": u, "body": str(r[b_col]) if b_col and pd.notna(r[b_col]) else ""})
        return res
    except: return []

def move_to_done(path):
    os.makedirs(DONE_DIR, exist_ok=True); f = os.path.basename(path); d = os.path.join(DONE_DIR, f)
    if os.path.exists(d): d = os.path.join(DONE_DIR, f"{os.path.splitext(f)[0]}_{int(time.time())}{os.path.splitext(f)[1]}")
    
    # WinError 32 (PermissionError) 대응을 위한 재시도 루틴
    for i in range(5):
        try:
            shutil.move(path, d)
            print(f"✅ 파일을 [{DONE_DIR}] 폴더로 이동 완료.")
            return
        except PermissionError:
            if i < 4:
                print(f"⚠️ 파일이 잠겨 있습니다. 2초 후 재시도 중... ({i+1}/5)")
                time.sleep(2)
            else:
                print(f"❌ 파일이 계속 잠겨 있어 이동에 실패했습니다. (수동 이동 필요)")
        except Exception as e:
            print(f"❌ 파일 이동 중 오류 발생: {e}")
            break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument('--dry-run', action='store_true'); parser.add_argument('--limit', type=int); parser.add_argument('--max-links', type=int); parser.add_argument('--url'); parser.add_argument('--body', default="")
    args = parser.parse_args(); main(dry_run=args.dry_run, limit=args.limit, single_url=args.url, single_body=args.body, max_links=args.max_links)
