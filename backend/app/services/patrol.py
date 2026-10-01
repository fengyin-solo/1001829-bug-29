"""巡查任务业务规则：状态流转、字段校验与筛选口径都收在这里。

作废相关约定：
- 只有「待派发」「巡查中」的巡查单允许作废，已提交结果的一律拦下；
- 作废会清掉巡查执行/结果数据，操作记录只在首次作废时写一条，重复作废不多留；
- 批量作废逐条给出成功与失败原因，并按批次键持久化进度，中断后可接着走。
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "patrol"
REQUIRED_FIELDS = ["巡查单号", "巡查路线", "巡查人员"]
STATUS_ORDER = ["待派发", "巡查中", "已提交", "已作废"]
ACTION_RULES = {"派发巡查": "巡查中", "提交结果": "已提交", "作废巡查": "已作废"}
NEGATIVE_ACTIONS = ["作废巡查"]
VOID_ACTION = "作废巡查"

# 作废后要清掉的巡查执行/结果字段；巡查单号、路线、人员是派单时留下的事实，保留备查。
VOID_CLEAR_FIELDS = ["巡查日期", "巡查里程", "发现问题数", "巡查时长"]
# 提交结果时允许写入的执行/结果字段。
RESULT_FIELDS = ["巡查日期", "巡查里程", "发现问题数", "巡查时长"]
DISPLAY_STATUS_FIELD = "巡查状态"

# 各动作允许的源状态；不在这里面就拦下并说明原因。
ACTION_SOURCE_STATUSES = {
    "派发巡查": ["待派发"],
    "提交结果": ["巡查中"],
    "作废巡查": ["待派发", "巡查中"],
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _code(entry: dict[str, Any] | None, entry_id: int) -> str:
    if entry and entry.get("巡查单号"):
        return str(entry["巡查单号"])
    return f"巡查单{entry_id}"


def _append_log(entry: dict[str, Any], action: str, detail: str) -> None:
    entry.setdefault("logs", []).append({"action": action, "time": _now(), "detail": detail})


class PatrolService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("巡查单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def status_stats(self) -> dict[str, int]:
        """巡查台账口径：各状态数量都按真实 status 统计，已作废数与概览同源。"""
        counts = store.count_by_status(MODULE)
        rows = store.rows(MODULE)
        return {
            "total": len(rows),
            "待派发": counts.get("待派发", 0),
            "巡查中": counts.get("巡查中", 0),
            "已提交": counts.get("已提交", 0),
            "已作废": counts.get("已作废", 0),
        }

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry[DISPLAY_STATUS_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        for field in VOID_CLEAR_FIELDS:
            entry.setdefault(field, "")
        entry["logs"] = []
        rows.append(entry)
        return entry, []

    # -- 状态流转 -------------------------------------------------------------

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"巡查单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于巡查任务可执行范围"

        current = str(entry.get("status") or "")
        if action == VOID_ACTION:
            return self._void_entry(entry_id, entry, current, batch=False)
        if current not in ACTION_SOURCE_STATUSES[action]:
            return None, f"{_code(entry, entry_id)}当前状态为「{current}」，不允许{action}"

        target = ACTION_RULES[action]
        if action == "提交结果":
            for field in RESULT_FIELDS:
                if values and str(values.get(field) or "").strip():
                    entry[field] = values[field]
        entry["status"] = target
        entry[DISPLAY_STATUS_FIELD] = target
        entry["pending"] = target in ("待派发", "巡查中")
        entry["abnormal"] = False
        _append_log(entry, action, f"状态由「{current}」流转为「{target}」")
        return entry, f"巡查单已{action}"

    def _void_entry(
        self, entry_id: int, entry: dict[str, Any], current: str, *, batch: bool
    ) -> tuple[dict[str, Any] | None, str]:
        """作废单条巡查单；已作废的直接幂等返回，已提交结果的不允许作废。"""
        code = _code(entry, entry_id)
        if current == "已作废":
            # 同一批再提交一次时不新写作废记录，按已处理成功回执。
            return entry, f"{code}已作废，无需重复作废"
        if current == "已提交":
            return None, f"{code}已提交巡查结果，不允许作废"
        if current not in ACTION_SOURCE_STATUSES[VOID_ACTION]:
            return None, f"{code}当前状态为「{current}」，不允许作废"

        entry["status"] = "已作废"
        entry[DISPLAY_STATUS_FIELD] = "已作废"
        entry["pending"] = False
        entry["abnormal"] = True
        for field in VOID_CLEAR_FIELDS:
            entry[field] = ""
        _append_log(entry, VOID_ACTION, f"状态由「{current}」作废为「已作废」，执行与结果数据已清空")
        return entry, f"{code}已作废"

    # -- 批量作废（逐条回执、断点续跑、同一批只算一次） --------------------------

    def batch_key(self, ids: list[int]) -> str:
        unique = sorted(set(ids))
        raw = ",".join(str(i) for i in unique) + f"|{VOID_ACTION}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    def batch_void(
        self, ids: list[int]
    ) -> dict[str, Any]:
        # 同批内去重，保留首次出现顺序；同一批巡查任务只算一次。
        unique_ids = list(dict.fromkeys(ids))
        if not unique_ids:
            return {
                "ok": False,
                "message": "未选择任何巡查单，无法批量作废",
                "action": VOID_ACTION,
                "batch_key": "",
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "finished": True,
                "results": [],
            }

        batch_key = self.batch_key(unique_ids)
        job = store.get_batch_job(batch_key)
        if job is None:
            job = {"action": VOID_ACTION, "ids": unique_ids, "results": {}}
            store.save_batch_job(batch_key, job)

        results = job["results"]
        for entry_id in unique_ids:
            if entry_id in results:
                # 中断后续跑：已回执的不再处理，作废记录不会重复。
                continue
            entry = store.find(MODULE, entry_id)
            if entry is None:
                receipt = {
                    "id": entry_id,
                    "code": f"巡查单{entry_id}",
                    "ok": False,
                    "status": "",
                    "message": f"巡查单 {entry_id} 不存在或已归档",
                }
                results[entry_id] = receipt
                continue
            current = str(entry.get("status") or "")
            try:
                target, message = self._void_entry(entry_id, entry, current, batch=True)
            except Exception as exc:  # 意外中断不写回执，下次提交接着走这一张
                return self._batch_summary(batch_key, unique_ids, results, interrupted=True, error=str(exc))
            receipt = {
                "id": entry_id,
                "code": _code(entry, entry_id),
                "ok": target is not None,
                "status": (target or entry or {}).get("status", current),
                "message": message,
            }
            results[entry_id] = receipt

        return self._batch_summary(batch_key, unique_ids, results, interrupted=False)

    def _batch_summary(
        self,
        batch_key: str,
        ids: list[int],
        results: dict[int, dict[str, Any]],
        *,
        interrupted: bool,
        error: str = "",
    ) -> dict[str, Any]:
        ordered = [results[entry_id] for entry_id in ids if entry_id in results]
        success_count = sum(1 for item in ordered if item["ok"])
        failed_count = len(ordered) - success_count
        finished = not interrupted and len(ordered) == len(ids)
        if interrupted:
            message = f"批量作废中断：{error or '处理未完成'}，可再次提交接着处理，已成功 {success_count} 张"
            ok = False
        elif failed_count:
            message = f"批量作废完成：成功 {success_count} 张，失败 {failed_count} 张，详见逐条回执"
            ok = False
        else:
            message = f"批量作废完成：{success_count} 张巡查单全部作废成功"
            ok = True
        return {
            "ok": ok,
            "message": message,
            "action": VOID_ACTION,
            "batch_key": batch_key,
            "total": len(ids),
            "success_count": success_count,
            "failed_count": failed_count,
            "finished": finished,
            "results": ordered,
        }
