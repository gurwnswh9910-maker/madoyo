import re


MAX_THREADS_TEXT_LENGTH = 500
DEFAULT_MAX_BODY_LINES = 8
DEFAULT_MAX_REPLY_LINES = 10

REPEATED_CHAR_PATTERN = re.compile(r"([^\s])\1{5,}")
URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
HTML_OR_INTERNAL_TAG_PATTERN = re.compile(r"<[^>\n]{2,}>")
JSON_COPY_PATTERN = re.compile(r'(^\s*[\[{])|("[A-Za-z_]*copy[A-Za-z_]*"\s*:)', re.IGNORECASE)
BAD_UNICODE_PATTERN = re.compile(r"[\ufffc\ufffd]")
DISCLOSURE_PATTERN = re.compile(
    r"(쿠팡\s*파트너스|파트너스\s*활동|수수료를\s*제공받|소정의\s*수수료|홍보\s*활동)",
    re.IGNORECASE,
)
META_LEAK_PATTERNS = (
    ("internal_marker", re.compile(r"<_\|[^>]*\|>")),
    ("prompt_rule_marker", re.compile(r"\b(?:dev_rule|user_rule|system_rule|assistant_rule)\b", re.IGNORECASE)),
    ("copy_tag_leak", re.compile(r"\[(?:FINAL_COPY(?:_\d+)?|DRAFT_COPY)\]", re.IGNORECASE)),
    ("code_fence_leak", re.compile(r"```")),
    ("mojibake_explanation_marker", re.compile(r"璇存槑")),
    ("role_or_output_label", re.compile(r"(^|\n)\s*(?:assistant|user|system|model|output|answer|explanation)\s*[:：]", re.IGNORECASE)),
    ("explanation_header", re.compile(r"(^|\n)\s*(?:[-*]\s*)?(?:설명|분석|전략|이유|주의|메타|출력|결과|체크리스트)\s*[:：]")),
)


def rejection_category(reason):
    if reason == "over_500_chars":
        return "content_length_over_limit"
    return "content_hygiene_rejected"


def _line_count(text):
    return len([line for line in text.splitlines() if line.strip()])


def _repeated_phrase_rejection(text):
    normalized = re.sub(r"\s+", " ", text).strip()
    chunks = re.split(r"(?<=[.!?。！？;;])\s+|\n+", normalized)
    seen = {}
    for chunk in chunks:
        chunk = chunk.strip()
        if len(chunk) < 8:
            continue
        seen[chunk] = seen.get(chunk, 0) + 1
        if seen[chunk] >= 4:
            return {
                "reason": "repeated_phrase_4",
                "phrase": chunk[:80],
                "repeat_count": seen[chunk],
            }

    exact_repeat = re.search(r"(.{12,120})\1{2,}", normalized)
    if exact_repeat:
        return {
            "reason": "repeated_block_3",
            "phrase": exact_repeat.group(1)[:80],
            "repeat_count": 3,
        }

    return None


def get_text_rejection(
    text,
    *,
    max_length=MAX_THREADS_TEXT_LENGTH,
    reject_repeated=True,
    reject_meta=True,
    reject_urls=False,
    reject_disclosure=False,
    max_lines=None,
    min_hangul_chars=0,
):
    text = "" if text is None else str(text)
    text_len = len(text)

    if text_len > max_length:
        return {
            "reason": "over_500_chars",
            "text_length": text_len,
            "max_length": max_length,
            "preview": text[:120],
        }

    if max_lines is not None:
        lines = _line_count(text)
        if lines > max_lines:
            return {
                "reason": "too_many_lines",
                "text_length": text_len,
                "line_count": lines,
                "max_lines": max_lines,
                "preview": text[:120],
            }

    if BAD_UNICODE_PATTERN.search(text):
        return {
            "reason": "bad_unicode_marker",
            "text_length": text_len,
            "preview": text[:120],
        }

    if reject_urls and URL_PATTERN.search(text):
        return {
            "reason": "url_in_body",
            "text_length": text_len,
            "preview": text[:120],
        }

    if reject_disclosure and DISCLOSURE_PATTERN.search(text):
        return {
            "reason": "disclosure_in_body",
            "text_length": text_len,
            "preview": text[:120],
        }

    if reject_repeated:
        repeated = REPEATED_CHAR_PATTERN.search(text)
        if repeated:
            return {
                "reason": "same_char_repeat_6",
                "text_length": text_len,
                "repeat_char": repeated.group(1),
                "repeat_len": len(repeated.group(0)),
                "repeat_index": repeated.start(),
                "repeat_preview": repeated.group(0)[:12],
                "preview": text[:120],
            }

        repeated_phrase = _repeated_phrase_rejection(text)
        if repeated_phrase is not None:
            repeated_phrase.update({"text_length": text_len, "preview": text[:120]})
            return repeated_phrase

    if reject_meta:
        for reason, pattern in META_LEAK_PATTERNS:
            match = pattern.search(text)
            if match:
                return {
                    "reason": reason,
                    "text_length": text_len,
                    "match": match.group(0)[:80],
                    "match_index": match.start(),
                    "preview": text[:120],
                }

        if HTML_OR_INTERNAL_TAG_PATTERN.search(text):
            match = HTML_OR_INTERNAL_TAG_PATTERN.search(text)
            return {
                "reason": "angle_tag_leak",
                "text_length": text_len,
                "match": match.group(0)[:80],
                "match_index": match.start(),
                "preview": text[:120],
            }

        if JSON_COPY_PATTERN.search(text):
            match = JSON_COPY_PATTERN.search(text)
            return {
                "reason": "json_or_key_value_leak",
                "text_length": text_len,
                "match": match.group(0)[:80],
                "match_index": match.start(),
            "preview": text[:120],
        }

    if min_hangul_chars > 0 and len(re.findall(r"[가-힣]", text)) < min_hangul_chars:
        return {
            "reason": "too_few_hangul_chars",
            "text_length": text_len,
            "min_hangul_chars": min_hangul_chars,
            "preview": text[:120],
        }

    return None
