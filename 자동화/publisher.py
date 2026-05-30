import re
import time
import requests
import sys
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "작동중코드"))
from app_config import GlobalConfig
from content_guard import (
    DEFAULT_MAX_BODY_LINES,
    DEFAULT_MAX_REPLY_LINES,
    MAX_THREADS_TEXT_LENGTH,
    get_text_rejection,
    rejection_category,
)


NON_RETRIABLE_ERROR_CATEGORIES = {
    "account_restricted",
    "action_blocked",
    "media_uri_unavailable",
}

URL_PATTERN = re.compile(r"https?://\S+")


def _get_retry_session():
    """Create a retrying session for transient network/server errors only."""
    session = requests.Session()
    
    # ==== 봇 탐지 방지 방어막: User-Agent 위장 설정 (Galaxy S22+) ====
    user_agent = getattr(GlobalConfig, "MOBILE_USER_AGENT", "Mozilla/5.0 (Linux; Android 14; SM-S906N)")
    session.headers.update({
        "User-Agent": user_agent,
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    # =================================================================
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _parse_error_payload(resp):
    try:
        payload = resp.json()
    except ValueError:
        payload = {"error": {"message": resp.text}}

    error = payload.get("error") or {}
    message = str(error.get("message", ""))
    user_title = str(error.get("error_user_title", ""))
    user_msg = str(error.get("error_user_msg", ""))
    combined = " ".join([message, user_title, user_msg]).lower()
    code = error.get("code")
    subcode = error.get("error_subcode")
    is_transient = bool(error.get("is_transient"))

    if subcode == 4279013 or "user access is restricted" in combined:
        category = "account_restricted"
    elif subcode == 2207051 or ("action" in combined and "blocked" in combined):
        category = "action_blocked"
    elif subcode == 2207052 or "media uri" in combined or "uri" in combined:
        category = "media_uri_unavailable"
    elif is_transient:
        category = "transient_api"
    else:
        category = "api_error"

    return {
        "error_category": category,
        "error_code": code,
        "error_subcode": subcode,
        "error_message": message,
        "error_user_title": user_title,
        "error_user_msg": user_msg,
        "is_transient": is_transient,
        "raw_error": payload,
    }


def _failure_result(stage, resp, *, item_index=None):
    details = _parse_error_payload(resp)
    result = {
        "ok": False,
        "stage": stage,
        **details,
    }
    if item_index is not None:
        result["item_index"] = item_index
    return result


def _exception_result(stage, exc):
    return {
        "ok": False,
        "stage": stage,
        "error_category": "exception",
        "error_code": None,
        "error_subcode": None,
        "error_message": str(exc),
        "error_user_title": "",
        "error_user_msg": "",
        "is_transient": False,
        "raw_error": None,
    }


def _success_result(**extra):
    return {
        "ok": True,
        "stage": extra.pop("stage", "publish"),
        "error_category": None,
        "error_code": None,
        "error_subcode": None,
        "error_message": "",
        "error_user_title": "",
        "error_user_msg": "",
        "is_transient": False,
        "raw_error": None,
        **extra,
    }


def _content_rejection_result(field_name, rejection):
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
        "error_user_title": "",
        "error_user_msg": "",
        "is_transient": False,
        "raw_error": None,
        "field_name": field_name,
        "text_length": text_length,
        "max_text_length": max_length,
        "rejection_reason": rejection["reason"],
    }


def get_reply_text_rejection(reply_text):
    return get_text_rejection(
        reply_text,
        reject_repeated=True,
        reject_meta=True,
        reject_urls=False,
        reject_disclosure=False,
        max_lines=DEFAULT_MAX_REPLY_LINES,
        min_hangul_chars=5,
    )


def collapse_duplicate_reply_urls(reply_text):
    """Keep the first occurrence of each URL and remove duplicate URL lines."""
    if not reply_text:
        return reply_text

    seen_urls = set()

    def replace(match):
        url = match.group(0)
        if url in seen_urls:
            return ""
        seen_urls.add(url)
        return url

    collapsed = URL_PATTERN.sub(replace, reply_text)
    collapsed = re.sub(r"[ \t]+\n", "\n", collapsed)
    collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
    return collapsed.strip()


def _create_text_or_single_media(session, creation_url, access_token, text, image_urls):
    if not image_urls:
        return session.post(
            creation_url,
            data={"media_type": "TEXT", "text": text, "access_token": access_token},
        )

    media_type = "VIDEO" if any(ext in image_urls[0].lower() for ext in [".mp4", ".mov"]) else "IMAGE"
    payload = {"media_type": media_type, "text": text, "access_token": access_token}
    payload["video_url" if media_type == "VIDEO" else "image_url"] = image_urls[0]
    return session.post(creation_url, data=payload)


def _create_carousel_children(session, creation_url, access_token, image_urls):
    item_ids = []
    expected_count = len(image_urls[:10])

    for idx, url in enumerate(image_urls[:10], start=1):
        media_type = "VIDEO" if any(ext in url.lower() for ext in [".mp4", ".mov"]) else "IMAGE"
        payload = {"media_type": media_type, "is_carousel_item": "true", "access_token": access_token}
        payload["video_url" if media_type == "VIDEO" else "image_url"] = url

        time.sleep(3)
        last_resp = None

        for attempt in range(3):
            last_resp = session.post(creation_url, data=payload)
            if last_resp.status_code == 200:
                item_id = last_resp.json().get("id")
                item_ids.append(item_id)
                retry_suffix = f" (retry {attempt})" if attempt > 0 else ""
                print(f"    - 슬라이드 항목 #{idx}/{expected_count} 생성 성공 (ID: {item_id}){retry_suffix}")
                break

            error_info = _parse_error_payload(last_resp)
            print(f"    ⚠️ 슬라이드 항목 #{idx} 생성 시도 {attempt + 1}/3 실패: {error_info['raw_error']}")
            if error_info["error_category"] in NON_RETRIABLE_ERROR_CATEGORIES:
                print(
                    f"    ⛔ 슬라이드 항목 #{idx}은 재시도 가치가 없는 오류({error_info['error_category']})로 판단해 즉시 중단합니다."
                )
                return None, {
                    "ok": False,
                    "stage": "create_child",
                    "item_index": idx,
                    **error_info,
                }

            time.sleep(5 * (attempt + 1))

        else:
            print(f"    ❌ 슬라이드 항목 #{idx} 최종 생성 실패. 게시를 중단합니다.")
            return None, _failure_result("create_child", last_resp, item_index=idx)

    return item_ids, None


def _wait_until_finished(session, base_url, access_token, container_ids, label):
    print(f"    - {label} 처리 대기 중..", end="", flush=True)
    # 36 * 5초 = 180초 (3분) 대기
    for _ in range(36):
        time.sleep(5)
        pending = False
        for container_id in container_ids:
            try:
                resp = session.get(f"{base_url}/{container_id}?fields=status&access_token={access_token}").json()
                if resp.get("status") not in ("FINISHED", "PUBLISHED"):
                    pending = True
                    break
            except:
                pending = True
                break
        if not pending:
            print(" 완료!")
            return True
        print(".", end="", flush=True)
    
    print(" 타임아웃! (미디어 처리가 너무 오래 걸립니다.)")
    return False


def upload_to_threads(user_id, access_token, text, image_urls=None, reply_text=None, reply_image_url=None):
    """
    Upload a Threads post and return structured success/failure details.
    """
    if not user_id or not access_token:
        raise ValueError("Threads User ID와 Access Token이 필요합니다.")

    body_rejection = get_text_rejection(
        text,
        reject_repeated=True,
        reject_meta=True,
        reject_urls=True,
        reject_disclosure=True,
        max_lines=DEFAULT_MAX_BODY_LINES,
        min_hangul_chars=5,
    )
    if body_rejection is not None:
        result = _content_rejection_result("본문", body_rejection)
        print(f"[FAIL] {result['error_message']}")
        return result

    if reply_text:
        reply_rejection = get_reply_text_rejection(reply_text)
        if reply_rejection is not None:
            fallback_reply_text = collapse_duplicate_reply_urls(reply_text)
            fallback_rejection = (
                get_reply_text_rejection(fallback_reply_text)
                if fallback_reply_text != reply_text
                else reply_rejection
            )
            if fallback_reply_text != reply_text and fallback_rejection is None:
                print("[WARN] 첫댓글 위생 컷 감지: 중복 링크를 1회로 줄여 업로드합니다.")
                reply_text = fallback_reply_text
            else:
                result = _content_rejection_result("첫댓글", reply_rejection)
                print(f"[FAIL] {result['error_message']}")
                return result

    base_url = "https://graph.threads.net/v1.0"
    creation_url = f"{base_url}/{user_id}/threads"
    publish_url = f"{base_url}/{user_id}/threads_publish"
    session = _get_retry_session()

    print(f"[STEP] 1단계: 미디어 컨테이너 생성 중 (총 {len(image_urls) if image_urls else 0}개 미디어)")

    try:
        if not image_urls or len(image_urls) == 1:
            resp = _create_text_or_single_media(session, creation_url, access_token, text, image_urls)
        else:
            if len(image_urls) < 2:
                print(f"    [FAIL] 미디어 개수 부족 (최소 2개 필요, 현재: {len(image_urls)}개). 중단합니다.")
                return {
                    "ok": False,
                    "stage": "create_child",
                    "error_category": "media_count_insufficient",
                    "error_code": None,
                    "error_subcode": None,
                    "error_message": "insufficient media count",
                    "error_user_title": "",
                    "error_user_msg": "",
                    "is_transient": False,
                    "raw_error": None,
                }

            item_ids, child_error = _create_carousel_children(session, creation_url, access_token, image_urls)
            if child_error:
                return child_error

            if not _wait_until_finished(session, base_url, access_token, item_ids, f"{len(item_ids)}개 자식 컨테이너"):
                return {
                    "ok": False,
                    "stage": "create_child",
                    "error_category": "timeout",
                    "error_message": "자식 컨테이너 처리 타임아웃",
                }

            resp = session.post(
                creation_url,
                data={
                    "media_type": "CAROUSEL",
                    "children": ",".join(item_ids),
                    "text": text,
                    "access_token": access_token,
                },
            )

        if resp.status_code != 200:
            print(f"[FAIL] 컨테이너 생성 실패: {resp.json()}")
            return _failure_result("create_parent", resp)

        creation_id = resp.json().get("id")
        if not _wait_until_finished(session, base_url, access_token, [creation_id], f"부모 컨테이너({creation_id})"):
            return {
                "ok": False,
                "stage": "create_parent",
                "error_category": "timeout",
                "error_message": "부모 컨테이너 처리 타임아웃",
            }

        pub_resp = session.post(publish_url, data={"creation_id": creation_id, "access_token": access_token})
        if pub_resp.status_code != 200:
            print(f"[FAIL] 게시물 업로드 실패: {pub_resp.json()}")
            return _failure_result("publish", pub_resp)

        media_id = pub_resp.json().get("id")
        print(f"[SUCCESS] 성공! Threads 업로드 완료 (Media ID: {media_id})")

        if reply_text or reply_image_url:
            print("[STEP] 3단계: 첫댓글 작성 중..")
            reply_payload = {"reply_to_id": media_id, "access_token": access_token}
            if reply_image_url:
                reply_type = "VIDEO" if any(ext in reply_image_url.lower() for ext in [".mp4", ".mov"]) else "IMAGE"
                reply_payload.update(
                    {
                        "media_type": reply_type,
                        "text": reply_text or "",
                        "video_url" if reply_type == "VIDEO" else "image_url": reply_image_url,
                    }
                )
            else:
                reply_payload.update({"media_type": "TEXT", "text": reply_text})

            reply_resp = session.post(creation_url, data=reply_payload)
            if reply_resp.status_code == 200:
                reply_id = reply_resp.json().get("id")
                time.sleep(20 if reply_image_url else 3)
                session.post(publish_url, data={"creation_id": reply_id, "access_token": access_token})
                print("[SUCCESS] 성공! 첫댓글 업로드 완료")
            else:
                reply_error = _parse_error_payload(reply_resp)
                print(f"    [WARN] 첫댓글 생성 실패: {reply_error['raw_error']}")

        return _success_result(stage="publish", media_id=media_id, creation_id=creation_id)
    except Exception as exc:
        print(f"[FAIL] [Publisher] 실행 오류: {exc}")
        return _exception_result("exception", exc)
