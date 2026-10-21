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
    return uuid4()


class TechPack(Base):
    """
    techpack table contains the metadata for the techpack documents that are uploaded to the system. 
    It has a one-to-one relationship with the BomExtraction table, which contains the extracted BOM data for the techpack. 
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
    bom_extractions table contains the extracted BOM data for the techpack documents. 
    It has a one-to-one relationship with the TechPack table, which contains the metadata for the techpack documents. 
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
    woven_materials table contains the extracted woven material data for the techpack documents.
    It has a many-to-one relationship with the TechPack table, which contains the metadata for the techpack documents. 
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
