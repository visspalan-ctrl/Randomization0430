from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


# 首次種子 / reset 時自動建立的站點數量；0 表示不預建，由管理員自行登記
PRESET_SITE_INITIAL_COUNT = 0

# 單次招募批次最多可啟用的站點數
RECRUITMENT_BATCH_MAX_ACTIVE_SITES = 10


class Site(Base):
    __tablename__ = "sites"
    site_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_name: Mapped[str] = mapped_column(String(128), nullable=False)
    assigned_recruitment_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enrollment_mode: Mapped[str] = mapped_column(String(16), default="trial")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SiteDailyPassword(Base):
    """密碼在「當日香港時區」同一日曆日內生效；起止為精確 UTC 時間戳。"""

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
    qr_mode: Mapped[str] = mapped_column(String(32), default="static_url", nullable=False)
    qr_value: Mapped[str] = mapped_column(String(512), nullable=False)
    qr_logo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
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
    participant_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    whatsapp_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    site_id: Mapped[str] = mapped_column(String(64), nullable=False)
    site_name: Mapped[str] = mapped_column(String(128), nullable=False)
    allocation_group: Mapped[str] = mapped_column(String(16), nullable=False)
    randomized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activation_status: Mapped[str] = mapped_column(String(16), default="pending")
    trial_status: Mapped[str] = mapped_column(String(16), default="trial")
    subject_code: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    assigned_recruitment_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_added: Mapped[bool] = mapped_column(Boolean, default=False)
    activation_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EnrollmentCounter(Base):
    __tablename__ = "enrollment_counter"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    seq: Mapped[int] = mapped_column(Integer, default=0)


class RandomizationSetting(Base):
    __tablename__ = "randomization_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    max_enrollment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_per_group: Mapped[int | None] = mapped_column(Integer, nullable=True)
    block_sizes_csv: Mapped[str] = mapped_column(String(64), default="4,8,12")
    randomization_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recruitment_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    recruitment_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    weekly_plan_weeks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekly_plan_per_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
