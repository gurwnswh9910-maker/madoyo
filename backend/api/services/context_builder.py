"""
Context Builder 서비스.
프론트엔드에서 전달받은 입력(텍스트, 이미지, URL)을
코어 엔진이 이해할 수 있는 표준화된 product_focus로 변환합니다.
"""
import os
import sys
import json
import requests

# 코어 모듈 경로 추가
_code_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _code_dir not in sys.path:
    sys.path.insert(0, _code_dir)

from google import genai
from google.genai import types
from marketing_focus_extractor import extract_marketing_focus


def _get_client(api_key: str):
    """Gemini API 클라이언트 생성"""
    return genai.Client(api_key=api_key)


def _extract_text_only_focus(client: genai.Client, model_name: str, reference_copy: str) -> dict:
    """
    텍스트만 있을 때: LLM으로 마케팅 소구점을 도출합니다.
    기존에 IDE 에이전트에서 수동으로 작성하던 부분을 자동화합니다.
    """
    prompt = f"""당신은 10년 차 탑 바이럴 마케터입니다.
아래 참고 카피를 분석하여, 다음 두 가지 관점에서 구조화된 분석 결과를 제공해 주세요.

1. **객관적 묘사 (Objective Description)**: 이 카피가 다루고 있는 제품/서비스/상황을 객관적으로 설명하세요.
2. **마케팅 인사이트 (Marketing Insight)**: 이 카피의 핵심 소구점, 타겟 감성, 유저가 반응할 만한 맥락을 분석하세요.

[분석 대상 카피]
{reference_copy}

[출력 형식]
반드시 아래와 같은 JSON 형식으로만 답변하세요:
{{
  "objective_description": "카피가 다루는 제품/상황에 대한 객관적 묘사 (1~2문장)",
  "marketing_insight": "마케터 시각의 핵심 소구점 및 맥락 분석 (1~2문장)"
}}
"""
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        res_json = json.loads(response.text)
        return {
            "objective_description": res_json.get("objective_description", reference_copy),
            "marketing_insight": res_json.get("marketing_insight", reference_copy),
        }
    except Exception as e:
        # 폴백: gemini-2.5-flash 시도
        if model_name != "gemini-2.5-flash":
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                res_json = json.loads(response.text)
                return {
                    "objective_description": res_json.get("objective_description", reference_copy),
                    "marketing_insight": res_json.get("marketing_insight", reference_copy),
                }
            except Exception:
                pass
        # 최종 폴백: 원본 텍스트 그대로 사용
        print(f"    ⚠️ 텍스트 분석 실패: {e}. 원본 텍스트를 product_focus로 사용합니다.")
        return {
            "objective_description": reference_copy,
            "marketing_insight": reference_copy,
        }


def _scrape_url_content(url: str) -> dict:
    """
    URL에서 텍스트와 이미지를 추출합니다.
    (간소화 버전 — Threads/Instagram URL 기본 지원)
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()

        text_content = ""
        image_urls = []

        # 간단한 메타태그 기반 추출
        from html.parser import HTMLParser

        class MetaParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.og_title = ""
                self.og_description = ""
                self.og_image = ""

            def handle_starttag(self, tag, attrs):
                if tag != "meta":
                    return
                attrs_dict = dict(attrs)
                prop = attrs_dict.get("property", "")
                content = attrs_dict.get("content", "")
                if prop == "og:title":
                    self.og_title = content
                elif prop == "og:description":
                    self.og_description = content
                elif prop == "og:image":
                    self.og_image = content

        parser = MetaParser()
        parser.feed(r.text)

        text_content = f"{parser.og_title} {parser.og_description}".strip()
        if parser.og_image:
            image_urls.append(parser.og_image)

        return {"text": text_content, "images": image_urls}
    except Exception as e:
        print(f"    ⚠️ URL 스크래핑 실패: {e}")
        return {"text": "", "images": []}


def build_context(
    api_key: str,
    model_name: str,
    reference_copy: str = None,
    image_urls: list = None,
    reference_url: str = None,
) -> tuple:
    """
    3가지 입력 타입을 표준화된 product_focus(dict)와 original_copy(str)로 변환합니다.

    Returns:
        tuple: (product_focus: dict, original_copy: str)
               product_focus는 {"objective_description": ..., "marketing_insight": ...} 형태
    """
    client = _get_client(api_key)
    original_copy = reference_copy or ""
    collected_images = list(image_urls) if image_urls else []

    # ── URL 입력 처리 ──
    # URL이 있으면 스레드용 강력한 스크래퍼를 사용하여 텍스트/이미지를 보충합니다.
    if reference_url:
        from api.services.scraper_service import get_threads_full_data
        scraped = get_threads_full_data(reference_url)
        
        if scraped and scraped.get("content_text"):
            stext = scraped["content_text"]
            if original_copy:
                original_copy = f"원본 스레드 카피: {stext}\n\n[사용자 특별 소구점 요청]: {original_copy}"
            else:
                original_copy = stext
        
        if scraped and scraped.get("image_urls"):
            collected_images.extend(scraped["image_urls"])

    # 로컬/서버 미디어 URL 처리 (호스팅된 이미지 URL 등)
    if collected_images:
        for i, img in enumerate(collected_images):
            # 상대 경로면 절대 경로로 (서버 측 처리용, 로컬호스트 주소 가정)
            # 여기서는 편의상 그대로 넘기고, 마케팅 포커스 분석기에서 요청 시 호스트를 붙이도록 처리하거나 
            # 외부에서 접근 가능하게 처리됨.
            if img.startswith("/media/"):
                collected_images[i] = f"http://localhost:8000{img}"

    # ── 분기 처리 ──
    has_text = bool(original_copy and original_copy.strip())
    has_images = bool(collected_images and len(collected_images) > 0)

    if has_images:
        # 미디어가 있는 경우
        product_name = original_copy[:50] if has_text else "제품"
        product_focus = extract_marketing_focus(
            client=client,
            model_name=model_name,
            product_name=product_name,
            original_text=original_copy if has_text else "",
            threads_images=collected_images,
        )
    elif has_text:
        # Case A: 텍스트만
        product_focus = _extract_text_only_focus(client, model_name, original_copy)
    else:
        # 입력이 없는 경우 (schemas.py의 validator에서 이미 차단되지만 안전장치)
        product_focus = {
            "objective_description": "알 수 없음",
            "marketing_insight": "제품 정보 없음",
        }

    return product_focus, original_copy
