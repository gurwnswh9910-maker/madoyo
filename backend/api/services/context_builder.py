"""
Context Builder 서비스.
프론트엔드에서 전달받은 입력(텍스트, 이미지, URL)을
코어 엔진이 이해할 수 있는 표준화된 `product_focus`로 변환합니다.
"""
import os
import sys
import json
import requests
import logging

# 코어 모듈 경로 추가
_code_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _code_dir not in sys.path:
    sys.path.insert(0, _code_dir)

from google import genai
from google.genai import types
from marketing_focus_extractor import extract_marketing_focus
from api.logging_utils import get_logger, log_event, preview_text

logger = get_logger(__name__)


def _get_client(api_key: str):
    """Gemini API 클라이언트를 생성합니다."""
    return genai.Client(api_key=api_key)


def _extract_text_only_focus(client: genai.Client, model_name: str, reference_copy: str) -> dict:
    """
    텍스트만 있을 때 LLM으로 마케팅 소구점을 도출합니다.
    기존 IDE 에이전트에서 수동으로 작성하던 분석 단계를 자동화합니다.
    """
    prompt = f"""당신은 10년 차 탑 바이럴 마케터입니다.
아래 참고 카피를 분석하여, 다음 두 가지 관점에서 구조화된 분석 결과를 제공해 주세요.

1. **객관적 묘사 (Objective Description)**: 이 카피가 다루고 있는 제품/서비스/상황을 객관적으로 설명하세요.
2. **마케팅 인사이트 (Marketing Insight)**: 이 카피의 핵심 소구점, 타깃 감성, 유저가 반응할 만한 맥락을 분석하세요.

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
        response_json = json.loads(response.text)
        return {
            "objective_description": response_json.get("objective_description", reference_copy),
            "marketing_insight": response_json.get("marketing_insight", reference_copy),
        }
    except Exception as error:
        logger.warning("context_builder.text_focus.primary_failed | model=%r error=%r", model_name, str(error))
        if model_name != "gemini-2.5-flash":
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                response_json = json.loads(response.text)
                return {
                    "objective_description": response_json.get("objective_description", reference_copy),
                    "marketing_insight": response_json.get("marketing_insight", reference_copy),
                }
            except Exception:
                logger.exception("context_builder.text_focus.fallback_failed | model=%r", model_name)

        print(f"    ⚠️ 텍스트 분석 실패: {error}. 원본 텍스트를 product_focus로 사용합니다.")
        return {
            "objective_description": reference_copy,
            "marketing_insight": reference_copy,
        }


def _scrape_url_content(url: str) -> dict:
    """
    URL에서 텍스트와 이미지를 간단히 추출합니다.
    Threads/Instagram 같은 URL에서 최소한의 메타데이터를 확보하기 위한 폴백입니다.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        text_content = ""
        image_urls = []

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
        parser.feed(response.text)

        text_content = f"{parser.og_title} {parser.og_description}".strip()
        if parser.og_image:
            image_urls.append(parser.og_image)

        return {"text": text_content, "images": image_urls}
    except Exception as error:
        print(f"    ⚠️ URL 스크래핑 실패: {error}")
        return {"text": "", "images": []}


def build_context(
    api_key: str,
    model_name: str,
    reference_copy: str = None,
    image_urls: list = None,
    reference_url: str = None,
    appeal_point: str = None,
) -> tuple:
    """
    세 가지 입력 타입을 표준화된 `product_focus(dict)`와 `original_copy(str)`로 변환합니다.

    Returns:
        tuple: (product_focus: dict, original_copy: str)
               product_focus는 {"objective_description": ..., "marketing_insight": ...} 형식입니다.
    """
    client = _get_client(api_key)
    original_copy = reference_copy or ""
    collected_images = list(image_urls) if image_urls else []

    log_event(
        logger,
        logging.INFO,
        "context_builder.build.started",
        has_reference_copy=bool(reference_copy),
        image_count=len(collected_images),
        has_reference_url=bool(reference_url),
        has_appeal_point=bool(appeal_point),
    )

    if reference_url:
        from api.services.scraper_service import get_threads_full_data

        scraped = get_threads_full_data(reference_url)
        log_event(
            logger,
            logging.INFO,
            "context_builder.reference_url.scraped",
            reference_url=preview_text(reference_url, limit=120),
            scraped_text=bool(scraped and scraped.get("content_text")),
            scraped_image_count=len(scraped.get("image_urls", [])) if scraped else 0,
        )

        if scraped and scraped.get("content_text"):
            scraped_text = scraped["content_text"]
            if original_copy:
                original_copy = f"원본 스레드 카피: {scraped_text}\n\n[사용자 특별 소구점 요청]: {original_copy}"
            else:
                original_copy = scraped_text

        if appeal_point:
            original_copy = f"[중요 소구점]: {appeal_point}\n\n{original_copy}"

        if scraped and scraped.get("image_urls"):
            collected_images.extend(scraped["image_urls"])

    if collected_images:
        for index, image_url in enumerate(collected_images):
            if image_url.startswith("/media/"):
                from api.config import MEDIA_BASE_URL

                collected_images[index] = f"{MEDIA_BASE_URL}{image_url}"

    has_text = bool(original_copy and original_copy.strip())
    has_images = bool(collected_images)

    if has_images:
        product_name = original_copy[:50] if has_text else "제품"
        product_focus = extract_marketing_focus(
            client=client,
            model_name=model_name,
            product_name=product_name,
            original_text=original_copy if has_text else "",
            threads_images=collected_images,
        )
    elif has_text:
        product_focus = _extract_text_only_focus(client, model_name, original_copy)
    else:
        product_focus = {
            "objective_description": "알 수 없음",
            "marketing_insight": "제품 정보 없음",
        }

    log_event(
        logger,
        logging.INFO,
        "context_builder.build.completed",
        has_text=has_text,
        has_images=has_images,
        focus_type=type(product_focus).__name__,
        original_copy_preview=preview_text(original_copy, limit=80),
    )
    return product_focus, original_copy
