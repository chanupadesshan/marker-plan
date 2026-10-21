"""Purchase-order data, preserving printed values rather than guessing missing cells."""
from typing import Literal
from copy import deepcopy
from pydantic import Field, model_validator
from .techpack_schema import StrictModel


class POSizeRow(StrictModel):
    size: str | None = None
    quantity: str | None = None
    source_page: int | None = None


class PurchaseOrder(StrictModel):
    contract_number: str | None = None
    tech_pack_reference: str | None = None
    model_id: str | None = None
    quality_id: str | None = None
    color_id: str | None = None
    total_quantity: str | None = None
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


def load_saved_extraction(payload: dict) -> POExtraction:
    """Read older saved results without exposing fields removed from the PO contract.

    This compatibility adapter is only for database reads. New model responses and
    user corrections still use strict schemas and reject unexpected fields.
    """
    data = deepcopy(payload)
    orders = list(data.get('orders', []))
    for page in data.get('page_results', []):
        orders.extend(page.get('result', {}).get('orders', []))
    for order in orders:
        for field in ('registered_date', 'shipping_date', 'modified_by', 'signed_by', 'total_amount', 'currency'):
            order.pop(field, None)
        for row in order.get('size_rows', []):
            for field in ('unit_price', 'amount', 'currency'):
                row.pop(field, None)
    return POExtraction.model_validate(data)
