"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS

# 页面上展示状态的业务字段：种子数据里它是占位文案，统一用真实状态覆盖，
# 避免列表页（读业务字段）和详情页（读 status）显示互相矛盾的结果。
STATUS_DISPLAY_FIELDS = {
    "patrol": "巡查状态",
    "pipe": "管段状态",
    "manhole": "检查井状态",
    "valve": "阀门状态",
    "pumpstation": "泵站状态",
    "defect": "缺陷状态",
    "cctv": "检测状态",
    "repair": "修复状态",
    "pressure": "监测状态",
    "flow": "监测状态",
    "leak": "排查状态",
    "dredge": "清淤状态",
    "material": "材料状态",
    "equip": "机械状态",
    "traffic": "许可状态",
    "complaint": "诉求状态",
    "fund": "资金状态",
    "archive": "档案状态",
}


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [self._normalize(name, dict(row)) for row in rows]
            for name, rows in SEED_ROWS.items()
        }
        # 批量动作任务：batch_key -> {"action", "ids", "results"}，
        # 中断后凭同一批次键续跑，已处理的单据不会重复作废。
        self._batch_jobs: dict[str, dict[str, Any]] = {}

    def _normalize(self, module: str, row: dict[str, Any]) -> dict[str, Any]:
        """把状态派生字段对齐到真实 status，保证重开页面、再进详情结果一致。"""
        display_field = STATUS_DISPLAY_FIELDS.get(module)
        status = row.get("status")
        if display_field and status:
            row[display_field] = status
        if module == "patrol":
            # 已作废单据的 pending/abnormal 以状态为准，概览与台账共用这一口径。
            row["pending"] = status in ("待派发", "巡查中")
            row["abnormal"] = status == "已作废"
        return row

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def count_by_status(self, module: str) -> dict[str, int]:
        """按真实 status 统计各状态数量；台账与概览都走这里，避免两处口径漂移。"""
        counts: dict[str, int] = {}
        for row in self.rows(module):
            status = str(row.get("status") or "")
            counts[status] = counts.get(status, 0) + 1
        return counts

    def get_batch_job(self, batch_key: str) -> dict[str, Any] | None:
        return self._batch_jobs.get(batch_key)

    def save_batch_job(self, batch_key: str, job: dict[str, Any]) -> None:
        self._batch_jobs[batch_key] = job

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            status_counts = self.count_by_status(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
                # 已作废数直接按状态统计，巡查台账与概览拿到的是同一个数字。
                "voided": status_counts.get("已作废", 0),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
            {"label": "已作废", "value": sum(int(item["voided"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
