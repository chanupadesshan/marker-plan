"""
define the database tables and their relationships using SQLAlchemy ORM
"""


from datetime import datetime
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Numeric, JSON, Uuid, false, func, true
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def uid():
    """
    Purpose: Generate the default primary key for a new database row.
    Input: none.
    Output: a new random UUID.
    """
    return uuid4()


class MarkerPlanRecord(Base):
    """Durable input and result snapshots; document deletion must not erase plan history."""
    __tablename__ = 'marker_plans'
    id: Mapped[str] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uid)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    request_json: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, 'postgresql'), nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, 'postgresql'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class User(Base):
    """
    Purpose: Table users: one row per person an admin has created who can sign in.
    Input: email (stored lower-case, unique), full_name, password_hash (salted scrypt, never the password),
    is_admin (full access plus user management), is_active (False blocks sign-in), permissions (a feature ->
    'view' | 'edit' map, ignored for admins) and created_at.
    Output: a User row.
    """
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    permissions: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """
    Purpose: Table audit_log: an append-only record of who did what (edits and approvals), kept for admins.
    Input: user_id (cleared if the user is deleted), user_email and user_name (copied at the time, so they survive
    that), action (e.g. 'techpack.approve'), target_type ('techpack' or 'po'), target_id and target_name (the file
    name at the time, so it survives deletion), details (what changed) and created_at.
    Output: an AuditLog row. Nothing in the app updates or deletes these rows.
    """
    __tablename__ = 'audit_log'
    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), index=True)
    user_email: Mapped[str] = mapped_column(String(254), nullable=False)
    user_name: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    target_name: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, 'postgresql'), default=dict, nullable=False)


class UsageArchive(Base):
    """
    Purpose: Table usage_archive: the model usage of a Tech Pack or purchase order that was deleted, kept so the
    Usage page still counts what was spent. Deleting a document removes its extraction, which is where usage lives.
    Input: kind ('techpack' or 'po'), document_id and filename (as they were), status, uploaded_by (cleared if the
    user is deleted), document_created_at (the upload date, which the Usage page groups by), usage (the request_usage
    list) and deleted_at.
    Output: a UsageArchive row. Nothing in the app updates or deletes these rows.
    """
    __tablename__ = 'usage_archive'
    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    document_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), index=True)
    document_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    usage: Mapped[list] = mapped_column(JSON().with_variant(JSONB, 'postgresql'), default=list, nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TechPack(Base):
    """
    Purpose: Table tech_packs: one row per uploaded Tech Pack PDF (the document's details, not its extracted data).
    Input: original_filename, minio_key (where the PDF is stored), sha256, status, error_message, page_count,
    selected_pages (the Wovens pages found), uploaded_by (the user who uploaded it; empty for older uploads) and created_at.
    Output: a TechPack row linked one-to-one to its BomExtraction; deleting it also removes that extraction and its materials.
    """
    __tablename__ = "tech_packs"
    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    minio_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    selected_pages: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    extraction: Mapped["BomExtraction | None"] = relationship(back_populates="document", uselist=False, cascade="all, delete-orphan")


class BomExtraction(Base):
    """
    Purpose: Table bom_extractions: the extracted Wovens data for one Tech Pack, stored as JSON.
    Input: document_id (the Tech Pack), model_name, extracted_json, raw_page_results (per-page progress and
    groups), warnings and updated_at.
    Output: a BomExtraction row linked one-to-one to its TechPack.
    """
    __tablename__ = "bom_extractions"
    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("tech_packs.id", ondelete="CASCADE"), unique=True, nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    extracted_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_page_results: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    warnings: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    document: Mapped[TechPack] = relationship(back_populates="extraction")


class WovenMaterial(Base):
    """
    Purpose: Table woven_materials: the Wovens and Knits materials of a Tech Pack as flat, searchable rows
    (the table keeps its original name).
    Input: document_id (the Tech Pack), category ('wovens' or 'knits'), material_code, description, composition,
    placement, quantity, unit, colorways and source_pages.
    Output: a WovenMaterial row; many rows belong to one Tech Pack and are rewritten whenever its extraction is saved.
    """
    __tablename__ = "woven_materials"
    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("tech_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(10), default='wovens', server_default='wovens', nullable=False)
    material_code: Mapped[str | None] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    composition: Mapped[str | None] = mapped_column(Text)
    placement: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[float | None] = mapped_column(Numeric(12, 4))
    unit: Mapped[str | None] = mapped_column(String(40))
    colorways: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    source_pages: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)


class PurchaseOrderDocument(Base):
    """
    Purpose: Table purchase_order_documents: one row per uploaded PO PDF, processed independently of any Tech Pack.
    Input: original_filename, minio_key, sha256, status, error_message, page_count, created_at, uploaded_by (the
    user who uploaded it; empty for older uploads) and an optional tech_pack_id linking it to a Tech Pack.
    Output: a PurchaseOrderDocument row linked one-to-one to its PurchaseOrderExtraction. Deleting the linked
    Tech Pack only clears tech_pack_id; deleting the PO removes its extraction.
    """
    __tablename__ = 'purchase_order_documents'
    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    tech_pack_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey('tech_packs.id', ondelete='SET NULL'))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    minio_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default='queued', nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    uploaded_by: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    extraction: Mapped['PurchaseOrderExtraction | None'] = relationship(
        back_populates='document', uselist=False, cascade='all, delete-orphan')


class PurchaseOrderExtraction(Base):
    """
    Purpose: Table purchase_order_extractions: the extracted contracts and size rows for one PO, stored as JSON.
    Input: document_id (the PO), model_name, extracted_json, raw_page_results (per-page progress), warnings and updated_at.
    Output: a PurchaseOrderExtraction row linked one-to-one to its PurchaseOrderDocument.
    """
    __tablename__ = 'purchase_order_extractions'
    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey('purchase_order_documents.id', ondelete='CASCADE'), unique=True, nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    extracted_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_page_results: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    warnings: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    document: Mapped[PurchaseOrderDocument] = relationship(back_populates='extraction')


class Ply(Base):
    """
    Purpose: Table plies: a lookup list of three values per row, edited from the Plies dashboard.
    Input: col_b (a whole number), col_c (a code, required), col_d (a value or range such as '90-100', optional);
    id is generated automatically.
    Output: a Ply row. The columns keep the neutral names of the source file's columns B, C and D.
    """
    __tablename__ = 'plies'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    col_b: Mapped[int] = mapped_column(Integer, nullable=False)
    col_c: Mapped[str] = mapped_column(Text, nullable=False)
    col_d: Mapped[str | None] = mapped_column(Text)
