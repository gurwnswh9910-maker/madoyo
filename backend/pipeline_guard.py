"""
파이프라인 가드 - 각 단계의 출력 검증 및 오염 데이터 차단

카피 생성 파이프라인의 각 단계를 통과한 결과값이 유효한지 자동 검증하고,
유해 값(빈 문자열, Access Denied 등)이 다음 단계로 넘어가는 것을 차단합니다.
"""
import traceback as tb
import re

# 오염 키워드 목록 (소문자 비교)
POISON_KEYWORDS = [
    "access denied", "액세스 거부", "액세스가 거부",
    "403 forbidden", "404 not found",
    "error occurred", "오류가 발생",
]

# 무의미 패턴 (이미지 넘김 표시 등)
NOISE_PATTERNS = [
    r'^\d+\s*/\s*\d+$',       # "1 / 2", "3/5"
    r'^https?://\S+$',         # URL만 있는 경우
]


class PipelineValidationError(Exception):
    """파이프라인 검증 실패 시 발생하는 커스텀 예외"""
    def __init__(self, stage, reason, value=None):
        self.stage = stage
        self.reason = reason
        self.value = value
        super().__init__(f"[{stage}] {reason}")


def _report_to_db(stage, reason, value=None, error_type="pipeline"):
    """검증 실패를 bug_reports DB에 자동 기록 (비동기 안전)"""
    try:
        from api.database import SessionLocal, BugReport
        db = SessionLocal()
        report = BugReport(
            layer="pipeline",
            error_type=error_type,
            message=f"[{stage}] {reason}",
            traceback=tb.format_stack()[-5:] if tb else "",
            context={"stage": stage, "value_preview": str(value)[:500] if value else None},
            code_ref=stage,
        )
        db.add(report)
        db.commit()
        db.close()
    except Exception as e:
        print(f"    ⚠️ [PipelineGuard] DB 기록 실패 (무시됨): {e}")


def guard_not_empty(value, stage_name):
    """값이 비어있지 않은지 검증"""
    if value is None or (isinstance(value, str) and not value.strip()):
        _report_to_db(stage_name, "빈 값 감지", value)
        raise PipelineValidationError(stage_name, "빈 값 감지", value)
    if isinstance(value, (list, dict)) and len(value) == 0:
        _report_to_db(stage_name, "빈 리스트/딕셔너리", value)
        raise PipelineValidationError(stage_name, "빈 리스트/딕셔너리", value)
    return value


def guard_no_poison(text, stage_name):
    """텍스트에 오염 키워드가 포함되어 있지 않은지 검증"""
    if not isinstance(text, str):
        return text
    text_lower = text.lower()
    for kw in POISON_KEYWORDS:
        if kw in text_lower:
            _report_to_db(stage_name, f"오염 키워드 감지: {kw}", text)
            raise PipelineValidationError(stage_name, f"오염 키워드: {kw}", text)
    return text


def guard_no_noise(text, stage_name):
    """무의미 패턴(이미지 넘김 등)만으로 이루어진 텍스트를 걸러냄"""
    if not isinstance(text, str):
        return text
    stripped = text.strip()
    for pattern in NOISE_PATTERNS:
        if re.match(pattern, stripped):
            _report_to_db(stage_name, f"무의미 패턴: {stripped}", text)
            raise PipelineValidationError(stage_name, f"무의미 패턴: {stripped}", text)
    return text


def guard_copy_quality(copy_text, stage_name="카피 생성"):
    """생성된 카피 1건의 품질을 검증"""
    guard_not_empty(copy_text, stage_name)
    guard_no_poison(copy_text, stage_name)
    guard_no_noise(copy_text, stage_name)
    
    # 최소 길이 검증 (너무 짧은 카피는 생성 실패)
    if len(copy_text.strip()) < 10:
        _report_to_db(stage_name, f"카피 길이 부족 ({len(copy_text)}자)", copy_text)
        raise PipelineValidationError(stage_name, f"카피 길이 부족: {len(copy_text)}자", copy_text)
    return copy_text


def guard_score(score, stage_name="채점"):
    """MSS 점수가 유효 범위인지 검증"""
    if score is None or score <= 0:
        _report_to_db(stage_name, f"점수 이상: {score}")
        # 점수가 0 이하인 경우 경고만 하고 진행 (차단하지는 않음)
        print(f"    ⚠️ [PipelineGuard] {stage_name}: 점수 {score} (이상 감지)")
    return score


def guard_batch_count(expected, actual, stage_name="배치 검증"):
    """요청 N개 = 완료 N개 인지 검증"""
    if expected != actual:
        msg = f"예상 {expected}건 != 실제 {actual}건"
        _report_to_db(stage_name, msg)
        print(f"    ⚠️ [PipelineGuard] {stage_name}: {msg}")
    return actual


def guard_top3(results, stage_name="최종 결과"):
    """최종 top_3 결과가 유효한지 검증"""
    if not results or len(results) < 1:
        _report_to_db(stage_name, "최종 결과 비어있음", results)
        raise PipelineValidationError(stage_name, "최종 결과 비어있음")
    
    for i, item in enumerate(results):
        copy_text = item.get("copy", "")
        try:
            guard_copy_quality(copy_text, f"top_{i+1}")
        except PipelineValidationError:
            # 개별 카피 실패는 로깅만 하고 전체 실패로 이어지지 않음
            print(f"    ⚠️ [PipelineGuard] top_{i+1} 카피 품질 검증 실패 (패스)")
    return results
