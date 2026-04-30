from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


# 最多可登记的站点数（含管理员后续新增）
PRESET_SITE_COUNT = 50
# 首次种子 / reset 时自动创建的站点数量；0 表示不预建，由管理员自行登记
PRESET_SITE_INITIAL_COUNT = 0

# 单次招募批次最多可激活的站点数
RECRUITMENT_BATCH_MAX_ACTIVE_SITES = 10


class Site(Base):
    __tablename__ = "sites"
    site_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SiteDailyPassword(Base):
    """口令在「当日香港时区」同一日历日内生效；起止为精确 UTC 时间戳。"""

    __tablename__ = "site_daily_passwords"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    password_plain: Mapped[str | None] = mapped_column(String(256), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    changed_by: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("site_id", "window_start", "version", name="uq_site_window_version"),)


class RecruitmentBatch(Base):
    __tablename__ = "recruitment_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RecruitmentBatchSite(Base):
    __tablename__ = "recruitment_batch_sites"
    batch_id: Mapped[int] = mapped_column(Integer, ForeignKey("recruitment_batches.id", ondelete="CASCADE"), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(64), primary_key=True)


class QRConfig(Base):
    __tablename__ = "qr_configs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_type: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    qr_value: Mapped[str] = mapped_column(String(512), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    changed_by: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), default="")
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GroupLabel(Base):
    __tablename__ = "group_labels"
    group_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    reason: Mapped[str] = mapped_column(String(255), default="")
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RandomizationRecord(Base):
    __tablename__ = "randomization_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enrollment_no: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    recruiter_id: Mapped[str] = mapped_column(String(64), default="")
    site_id: Mapped[str] = mapped_column(String(64), nullable=False)
    site_name: Mapped[str] = mapped_column(String(128), nullable=False)
    allocation_group: Mapped[str] = mapped_column(String(16), nullable=False)
    randomized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activation_status: Mapped[str] = mapped_column(String(16), default="pending")
    activation_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EnrollmentCounter(Base):
    __tablename__ = "enrollment_counter"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    seq: Mapped[int] = mapped_column(Integer, default=0)


class RandomizationSetting(Base):
    __tablename__ = "randomization_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    max_enrollment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    block_sizes_csv: Mapped[str] = mapped_column(String(64), default="4,8,12")
    h5_show_allocation_group: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[str] = mapped_column(String(64), default="system")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
