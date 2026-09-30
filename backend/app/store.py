"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        self._normalize_patrol()

    def _normalize_patrol(self) -> None:
        """巡查台账的 pending/abnormal/展示状态一律以 status 为准。

        种子数据里可能出现 status=巡查中却 abnormal=True 的脏标记，会让概览「异常量」
        与台账「已作废数」对不上；启动时统一纠正。
        """
        for row in self.rows("patrol"):
            status = str(row.get("status") or "")
            row["pending"] = status != "已作废"
            row["abnormal"] = status == "已作废"
            row["巡查状态"] = status
            row.setdefault("void_logs", [])

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            if name == "patrol":
                # 巡查模块的异常量口径就是「已作废」数量，与巡查台账保持一致。
                pending_count = sum(1 for row in rows if row.get("status") != "已作废")
                abnormal_count = sum(1 for row in rows if row.get("status") == "已作废")
            else:
                pending_count = sum(1 for row in rows if row.get("pending"))
                abnormal_count = sum(1 for row in rows if row.get("abnormal"))
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": pending_count,
                "abnormal": abnormal_count,
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
