"""Purchase-order data, preserving printed values rather than guessing missing cells."""
from typing import Literal
from pydantic import Field, model_validator
from .schema import StrictModel


class POSizeRow(StrictModel):
    size: str | None = None
    quantity: str | None = None
    unit_price: str | None = None
    amount: str | None = None
    currency: str | None = None
    source_page: int | None = None


class PurchaseOrder(StrictModel):
    contract_number: str | None = None
    tech_pack_reference: str | None = None
    model_id: str | None = None
    quality_id: str | None = None
    color_id: str | None = None
    registered_date: str | None = None
    shipping_date: str | None = None
    total_quantity: str | None = None
    modified_by: str | None = None
    signed_by: str | None = None
    total_amount: str | None = None
    currency: str | None = None
    size_rows: list[POSizeRow] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class POPageResult(StrictModel):
    page_kind: Literal['purchase_order', 'empty', 'other']
    orders: list[PurchaseOrder] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def consistent_outcome(self):
        if self.page_kind != 'purchase_order' and self.orders:
            raise ValueError('Only purchase_order pages may contain orders')
        return self


class POPageTable(StrictModel):
    page_number: int
    result: POPageResult


class POExtraction(StrictModel):
    orders: list[PurchaseOrder] = Field(default_factory=list)
    page_results: list[POPageTable] = Field(default_factory=list)
    request_usage: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    processing_complete: bool = False


class POCorrections(StrictModel):
    """Only orders are editable; processing evidence remains server-owned."""
    orders: list[PurchaseOrder]
