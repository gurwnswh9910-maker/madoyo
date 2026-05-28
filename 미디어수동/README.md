# 미디어수동 파이프라인

`미디어수동/media_manual_pipeline.py`는 사용자가 직접 넣은 미디어 폴더를 읽어 카피 생성용 엑셀을 만듭니다.

## 입력 폴더

폴더 1개가 게시물 1개입니다.

```text
미디어수동/
  미디어수동참조/
    001/
      001.jpg
      002.jpg
    002/
      001.mp4
      002.jpg
```

미디어 순서는 파일명 기준입니다. `001.jpg`, `002.jpg`, `003.mp4`처럼 앞에 번호를 붙이면 됩니다.

## 선택 manifest

`미디어수동참조/manifest.xlsx` 또는 `manifest.csv`를 둘 수 있습니다.

권장 컬럼:

- `폴더`
- `상품명`
- `설명`
- `링크`

`내쿠팡링크`는 v1에서 기본 비활성입니다. 나중에 쓸 때만 `--use-manifest-deeplink`를 켭니다.

## 실행 전 형식 검사

```powershell
python .\미디어수동\media_manual_pipeline.py --check-only
```

## 엑셀 생성

```powershell
python .\미디어수동\media_manual_pipeline.py
```

결과는 기본적으로 `미디어수동/미디어수동결과`에 저장됩니다.

## 결과 엑셀 검사

```powershell
python .\미디어수동\media_manual_pipeline.py --validate-output-excel .\미디어수동\미디어수동결과\결과파일.xlsx
```

## 반자동 업로드

v1은 `내쿠팡링크`를 비워둘 수 있으므로 반자동 업로드 때는 아래처럼 실행합니다.

```powershell
python .\반자동\semi_auto_publish.py --input-excel .\미디어수동\미디어수동결과\결과파일.xlsx --allow-missing-deeplink --dry-run
```

검수 후 실제 업로드에서는 `--dry-run`을 빼면 됩니다.
