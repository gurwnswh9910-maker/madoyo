import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return str(value)


def _record_root() -> Path:
    return Path(__file__).resolve().parent.parent / "benchmark_runs"


def _load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_benchmark_record(record: dict[str, Any], run_id: str | None = None) -> str:
    root = _record_root()
    root.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    safe_run_id = run_id or str(uuid.uuid4())
    file_name = f"{stamp}_{safe_run_id}.json"
    path = root / file_name

    payload = {
        "record_type": "copy_optimization_run_v1",
        "recorded_at_utc": now.isoformat(),
        **_jsonable(record),
    }
    _write_payload(path, payload)
    return str(path)


def _merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def sync_benchmark_record(
    record_path: str | None,
    patch: dict[str, Any] | None = None,
    event: dict[str, Any] | None = None,
) -> str:
    if not record_path:
        return ""

    path = Path(record_path)
    if not path.exists():
        return ""

    payload = _load_payload(path)
    if patch:
        payload = _merge_dict(payload, _jsonable(patch))
    if event:
        events = payload.get("events", [])
        events.append(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                **_jsonable(event),
            }
        )
        payload["events"] = events
    payload["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    _write_payload(path, payload)
    return str(path)


def safe_sync_benchmark_record(
    record_path: str | None,
    patch: dict[str, Any] | None = None,
    event: dict[str, Any] | None = None,
    context: str = "",
) -> str:
    try:
        return sync_benchmark_record(record_path, patch=patch, event=event)
    except Exception:
        logger.exception(
            "benchmark_recorder.sync_failed | context=%r record_path=%r",
            context,
            record_path,
        )
        return ""


def update_benchmark_record(record_path: str | None, patch: dict[str, Any]) -> str:
    return sync_benchmark_record(record_path, patch=patch)


def append_benchmark_event(record_path: str | None, event: dict[str, Any]) -> str:
    return sync_benchmark_record(record_path, event=event)
