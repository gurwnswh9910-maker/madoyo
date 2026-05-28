from pathlib import Path

import pandas as pd


def main():
    out = Path(__file__).resolve().parent / "keyword_research_runs" / "threads_keyword_plan_20260514.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)

    keywords = [
        (1, "외로움", "외로움/고립", "외로움", "외로움 직접 표현 수집", "single-token works in DOM probe"),
        (1, "외롭다", "외로움/고립", "외롭다", "외롭다는 감정 고백 수집", ""),
        (1, "공허함", "외로움/고립", "공허함", "공허/허무 감정 수집", ""),
        (1, "혼자", "외로움/상황", "혼자", "혼자 있음/혼자 생활 맥락", ""),
        (2, "혼밥", "외로움/상황", "혼밥", "혼자 먹기/일상 고립 맥락", ""),
        (2, "주말", "외로움/상황", "주말", "주말 외로움/할 일 없음 맥락", ""),
        (2, "1인가구", "외로움/상황", "1인가구", "생활 형태 기반 외로움", ""),
        (1, "친구", "관계", "친구", "친구 욕구/친구 관련 글", ""),
        (1, "친구없음", "관계", "친구없음", "친구 없음 직접 표현", "space removed for Threads search"),
        (1, "친구만들기", "관계", "친구만들기", "친구 만들기 행동 의향", "space removed for Threads search"),
        (1, "성인친구", "관계", "성인친구", "성인 이후 친구 만들기", "space removed for Threads search"),
        (1, "인간관계", "관계", "인간관계", "관계 고민 전반", ""),
        (1, "인간관계현타", "관계", "인간관계현타", "관계 피로/현타", "space removed for Threads search"),
        (2, "친해지기", "관계", "친해지기", "친해지는 어려움/욕구", ""),
        (2, "연락끊김", "관계", "연락끊김", "후속 연락/관계 지속 실패", "space removed for Threads search"),
        (1, "소모임", "모임", "소모임", "소모임 경험/불만", ""),
        (1, "모임", "모임", "모임", "모임 전반 경험", ""),
        (2, "모임후기", "모임", "모임후기", "모임 후기/만족 불만", "space removed for Threads search"),
        (2, "동호회", "모임", "동호회", "취미 기반 만남 대안", ""),
        (1, "소셜링", "모임/소셜링", "소셜링", "소셜링 공급/후기/불만", ""),
        (2, "소셜링후기", "모임/소셜링", "소셜링후기", "소셜링 후기", "space removed for Threads search"),
        (1, "소개팅", "기존대안", "소개팅", "소개팅 피로/대안 비교", ""),
        (1, "소개팅앱", "기존대안", "소개팅앱", "앱 피로/불만", ""),
        (1, "오픈채팅", "기존대안", "오픈채팅", "오픈채팅 불만/안전 우려", ""),
        (2, "문토", "기존대안/경쟁", "문토", "경쟁/대체 서비스 맥락", ""),
        (2, "타임레프트", "기존대안/경쟁", "타임레프트", "경쟁/대체 서비스 맥락", ""),
        (1, "스몰토크", "대화", "스몰토크", "얕은 대화 불만", ""),
        (1, "깊은대화", "대화", "깊은대화", "깊은 대화 욕구", "space removed for Threads search"),
        (1, "내향인", "성향", "내향인", "내향적 성향과 만남 욕구", ""),
        (2, "낯가림", "성향", "낯가림", "처음 만남/어색함 불안", ""),
    ]

    original_phrases = [
        "외로움 주말",
        "외로움 친구",
        "외로움 직장인",
        "혼자 주말",
        "혼자 밥",
        "친구 없음",
        "친구 만들기",
        "성인 친구",
        "30대 친구",
        "인간관계 현타",
        "친해지기 어렵다",
        "연락 부담",
        "연락 끊김",
        "소모임 후기",
        "소모임 현타",
        "소모임 어색",
        "모임 후기",
        "모임 어색",
        "소셜링 후기",
        "소셜링 현타",
        "소개팅 피곤",
        "소개팅 현타",
        "소개팅앱 현타",
        "오픈채팅 이상한 사람",
        "오픈채팅 현타",
        "스몰토크 지침",
        "스몰토크 싫어",
        "깊은대화",
        "내향인 모임",
        "내향인 친구",
    ]

    label_schema = [
        ("라벨상태", "blank / reviewed / exclude", "라벨링 상태"),
        ("전략보존", "Y / N", "전략 추출 후보 여부"),
        ("적합도점수", "0-5", "사업 핵심 문제 적합도"),
        ("핵심문제라벨", "free text", "강한 문제 프레임"),
        ("세그먼트추정", "free text", "직장인, 내향인, 1인가구 등"),
        ("마케팅각도", "free text", "공감형, 불만형, 오퍼형 등"),
        ("외로움직접표현", "0/1", "외로움 직접 표현"),
        ("사람만나기시도", "0/1", "모임/소개팅/오픈채팅 등 시도"),
        ("모임실패경험", "0/1", "모임 불만/실패 경험"),
        ("관계지속실패", "0/1", "후속 연락/관계 지속 실패"),
        ("스몰토크불만", "0/1", "얕은 대화 불만"),
        ("깊은대화욕구", "0/1", "진짜 이야기/깊은 대화 욕구"),
        ("기존대안피로", "0/1", "기존 서비스/대안 피로"),
        ("첫참석불안", "0/1", "첫 참석/어색함 불안"),
        ("안전품질불안", "0/1", "이상한 사람/품질/안전 우려"),
        ("후속연락욕구", "0/1", "다시 연락할 사람/명분 욕구"),
        ("행동의향", "0/1", "참여/신청/궁금 등 행동 신호"),
        ("경쟁서비스언급", "free text", "문토, 타임레프트 등"),
        ("라벨근거메모", "free text", "라벨 판단 근거"),
    ]

    notes = [
        {"item": "검색 방식", "value": "https://www.threads.com/search?q=<search_query>&serp_type=default"},
        {"item": "DOM 확인", "value": "/search 입력창에서 Enter 시 serp_type=default 결과 DOM 노출 확인"},
        {"item": "저장 형식", "value": "Excel은 라벨링용, JSONL은 원본 보존용"},
        {"item": "상세글 진입", "value": "하지 않음. 검색 결과 카드 DOM만 수집"},
    ]

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        pd.DataFrame(
            keywords,
            columns=["priority", "keyword", "category", "search_query", "intent", "notes"],
        ).to_excel(writer, sheet_name="keywords", index=False)
        pd.DataFrame(
            {"original_phrase": original_phrases, "usage": "기획/라벨링 힌트. Threads 직접 검색은 일부 결과 없음."}
        ).to_excel(writer, sheet_name="original_phrases", index=False)
        pd.DataFrame(label_schema, columns=["label", "value", "description"]).to_excel(
            writer, sheet_name="label_schema", index=False
        )
        pd.DataFrame(notes).to_excel(writer, sheet_name="notes", index=False)

    print(out)


if __name__ == "__main__":
    main()
