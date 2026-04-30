from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import PRESET_SITE_INITIAL_COUNT, Site


def ensure_preset_sites(db: Session) -> None:
    """按 PRESET_SITE_INITIAL_COUNT 创建首批 SITE_01 …（为 0 时不创建任何行）。

    登记总上限见 models.PRESET_SITE_COUNT；其余站点由管理员 POST /admin/sites 添加。
    """
    for i in range(1, PRESET_SITE_INITIAL_COUNT + 1):
        sid = f"SITE_{i:02d}"
        if db.get(Site, sid) is None:
            db.add(Site(site_id=sid, site_name=f"预设站点{i:02d}"))
    db.flush()
