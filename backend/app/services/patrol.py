"""巡查任务业务规则：状态流转、字段校验、批量作废与筛选口径都收在这里。"""
from __future__ import annotations

import uuid
from typing import Any

from app.store import store

MODULE = "patrol"
REQUIRED_FIELDS = ["巡查单号", "巡查路线", "巡查人员"]
STATUS_ORDER = ["待派发", "巡查中", "已提交", "已作废"]
FINAL_STATUS = "已作废"
ACTION_RULES = {"派发巡查": "巡查中", "提交结果": "已提交", "作废巡查": "已作废"}
NEGATIVE_ACTIONS = ["作废巡查"]
# 作废时需要一并清掉的结果字段：巡查单废了，提交结果不能继续挂在账上。
RESULT_FIELDS = ["巡查里程", "发现问题数", "巡查时长"]
DISPLAY_STATUS_FIELD = "巡查状态"
# 各动作允许的来源状态，不在表里的状态流转一律拦下。
ACTION_GUARDS: dict[str, set[str]] = {
    "派发巡查": {"待派发"},
    "提交结果": {"巡查中"},
    "作废巡查": {"待派发", "巡查中"},
}
VOIDABLE_STATUSES = ACTION_GUARDS["作废巡查"]


class PatrolService:
    def __init__(self) -> None:
        # batch_no -> 整批作废回执，同一个批次号再提交时原样返回，不重复落作废记录。
        self._void_batches: dict[str, dict[str, Any]] = {}

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

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry[DISPLAY_STATUS_FIELD] = entry["status"]
        for field in RESULT_FIELDS:
            entry.setdefault(field, "")
        entry["void_logs"] = []
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"巡查单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于巡查任务可执行范围"
        return self._apply_action(entry, action, batch_no=None)

    def void_many(
        self, entry_ids: list[int], *, batch_no: str | None = None
    ) -> tuple[dict[str, Any], str | None]:
        """批量作废：逐条处理、逐条回执，一张单的成败不影响同批其他单。

        同一个批次号重复提交时直接回放首次回执，保证中断后可续走、且同一批只算一次。
        """
        if not entry_ids:
            return {}, "请至少选择一张巡查单再提交批量作废"
        batch_no = batch_no or f"VB-{uuid.uuid4().hex[:12]}"
        previous = self._void_batches.get(batch_no)
        if previous is not None:
            return previous, None

        receipts: list[dict[str, Any]] = []
        # 同一批里重复勾选同一张单只处理一次，但回执仍逐条给出。
        seen: set[int] = set()
        success_count = 0
        for raw_id in entry_ids:
            try:
                entry_id = int(raw_id)
            except (TypeError, ValueError):
                receipts.append({
                    "id": raw_id, "巡查单号": "", "ok": False, "voided": False,
                    "reason": "巡查单编号无法识别",
                })
                continue
            if entry_id in seen:
                receipts.append({
                    "id": entry_id, "巡查单号": "", "ok": False, "voided": False,
                    "reason": "该巡查单在本批中重复提交，已去重",
                })
                continue
            seen.add(entry_id)

            entry = store.find(MODULE, entry_id)
            if entry is None:
                receipts.append({
                    "id": entry_id, "巡查单号": "", "ok": False, "voided": False,
                    "reason": "巡查单不存在或已归档",
                })
                continue

            order_no = str(entry.get("巡查单号", ""))
            if entry.get("status") == FINAL_STATUS:
                # 已经作废过的单不再落新记录，回执说明是重复作废。
                receipts.append({
                    "id": entry_id, "巡查单号": order_no, "ok": True, "voided": False,
                    "reason": "该巡查单此前已作废，本次未重复记录",
                })
                continue

            updated, message = self._apply_action(entry, "作废巡查", batch_no=batch_no)
            if updated is None:
                receipts.append({
                    "id": entry_id, "巡查单号": order_no, "ok": False, "voided": False,
                    "reason": message,
                })
            else:
                success_count += 1
                receipts.append({
                    "id": entry_id, "巡查单号": order_no, "ok": True, "voided": True,
                    "reason": "作废成功",
                })

        result = {
            "batch_no": batch_no,
            "total": len(entry_ids),
            "success_count": success_count,
            "failed_count": sum(1 for item in receipts if not item["ok"]),
            "receipts": receipts,
        }
        self._void_batches[batch_no] = result
        return result, None

    def get_void_batch(self, batch_no: str) -> dict[str, Any] | None:
        return self._void_batches.get(batch_no)

    def _apply_action(
        self, entry: dict[str, Any], action: str, *, batch_no: str | None
    ) -> tuple[dict[str, Any] | None, str]:
        target = ACTION_RULES[action]
        current = str(entry.get("status") or "")
        allowed = ACTION_GUARDS.get(action, set())
        if current not in allowed:
            label = self._status_hint(current)
            return None, f"巡查单 {entry.get('巡查单号', entry.get('id'))} 当前为{label}，不允许{action}"
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        entry["status"] = target
        entry["pending"] = target != FINAL_STATUS
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        entry[DISPLAY_STATUS_FIELD] = target
        if action == "作废巡查":
            self._void_entry(entry, batch_no=batch_no)
        return entry, f"巡查单已{action}"

    def _void_entry(self, entry: dict[str, Any], *, batch_no: str | None) -> None:
        # 清掉提交结果类字段，避免作废后路线/问题数还挂着造成账实不符。
        for field in RESULT_FIELDS:
            entry[field] = ""
        logs = entry.setdefault("void_logs", [])
        logs.append({"action": "作废巡查", "batch_no": batch_no})

    @staticmethod
    def _status_hint(status: str) -> str:
        if status == "已提交":
            return "已提交状态（已提交结果的巡查单不允许作废）"
        return status or "未知状态"
