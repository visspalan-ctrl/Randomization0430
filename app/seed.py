from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import PRESET_SITE_INITIAL_COUNT, Site


def ensure_preset_sites(db: Session) -> None:
    """按 PRESET_SITE_INITIAL_COUNT 建立首批 SITE_01 …（為 0 時不建立任何列）。
    其餘站點由管理員 POST /admin/sites 新增。
    """
    for i in range(1, PRESET_SITE_INITIAL_COUNT + 1):
        sid = f"SITE_{i:02d}"
        if db.get(Site, sid) is None:
            db.add(Site(site_id=sid, site_name=f"預設站點{i:02d}"))
    db.flush()
