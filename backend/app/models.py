"""
define the database tables and their relationships using SQLAlchemy ORM
"""


from datetime import datetime
from uuid import uuid4
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Numeric, func
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


class TechPack(Base):
    """
    Purpose: Table tech_packs: one row per uploaded Tech Pack PDF (the document's details, not its extracted data).
    Input: original_filename, minio_key (where the PDF is stored), sha256, status, error_message, page_count,
    selected_pages (the Wovens pages found) and created_at.
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
    Purpose: Table woven_materials: the Wovens materials of a Tech Pack as flat, searchable rows.
    Input: document_id (the Tech Pack), material_code, description, composition, placement, quantity, unit,
    colorways and source_pages.
    Output: a WovenMaterial row; many rows belong to one Tech Pack and are rewritten whenever its extraction is saved.
    """
    __tablename__ = "woven_materials"
    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("tech_packs.id", ondelete="CASCADE"), nullable=False, index=True)
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
    Input: original_filename, minio_key, sha256, status, error_message, page_count, created_at and an optional
    tech_pack_id linking it to a Tech Pack.
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
