# 반자동 업로드 파이프라인

`반자동/semi_auto_publish.py`는 `수동화/manual_pipeline.py`가 만든 결과 엑셀을 읽고, Threads 업로드 API만 호출합니다. 스크래핑, 쿠팡 조회, Gemini 카피 생성, 미디어 재호스팅은 수동화 단계에서 끝내는 전제입니다.

## 폴더

- 입력: `반자동/반자동참조`
- 결과: `반자동/반자동결과`
- 완료 이동 옵션: `반자동/반자동참조/업로드완료`

## 기본 실행

```powershell
$env:THREADS_CURRENT_ACCOUNT='1,2,3'
python .\반자동\semi_auto_publish.py --hours 8 --original-limit 30
```

`--original-limit 30`의 `30`은 원본 개수입니다. 계정이 3개여서 총 업로드 시도가 최대 90개여도, 시간 계산의 k는 30으로 잡습니다.

## 사전 점검

```powershell
python .\반자동\semi_auto_publish.py --hours 8 --original-limit 30 --dry-run
```

## 필요한 엑셀 컬럼

- `링크` 또는 URL 계열 컬럼
- `처리상태=completed`
- `카피1`, `카피2`, `카피3` 중 하나 이상
- `내쿠팡링크`
- `업로드미디어URL`

`업로드미디어URL`은 수동화 단계에서 Wi-Fi로 미리 만들어 둔 공개 미디어 URL 목록입니다. 반자동 단계에서는 이 URL을 그대로 Threads API에 넘기며, 로컬 미디어를 다시 재호스팅하지 않습니다.
