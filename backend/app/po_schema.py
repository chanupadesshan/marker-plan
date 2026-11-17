"""Purchase-order data, preserving printed values rather than guessing missing cells."""
from typing import Literal
from copy import deepcopy
from pydantic import Field, model_validator
from .techpack_schema import StrictModel


# Purpose: One size line of a purchase order, kept exactly as printed (for example size '-C52', quantity '32').
# Input: size and quantity (text) and source_page (set by the backend, never by the model).
# Output: a validated POSizeRow; missing values stay None.
class POSizeRow(StrictModel):
    size: str | None = None
    quantity: str | None = None
    source_page: int | None = None


# Purpose: One purchase-order contract: its identifiers, total quantity and size breakdown.
# Input: contract_number, tech_pack_reference, model_id, quality_id, color_id, total_quantity, size_rows, source_pages and warnings.
# Output: a validated PurchaseOrder. Prices, dates and signatures are deliberately not part of it.
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


# Purpose: The few identifiers printed in the header of a PO page, read cheaply to decide whether the page belongs to a Tech Pack.
# Input: contract_number, model_id and quality_id as printed (null when not printed on this page).
# Output: a validated POHeader. This class is also sent to the model as the required reply format.
class POHeader(StrictModel):
    contract_number: str | None = None
    model_id: str | None = None
    quality_id: str | None = None


# Purpose: What the model returns for one PO page: the kind of page and any contracts found on it.
# Input: page_kind ('purchase_order', 'empty' or 'other'), orders and warnings.
# Output: a validated POPageResult. Only a 'purchase_order' page may contain orders.
class POPageResult(StrictModel):
    page_kind: Literal['purchase_order', 'empty', 'other']
    orders: list[PurchaseOrder] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def consistent_outcome(self):
        """
        Purpose: Validator that rejects a contradictory page result: only a 'purchase_order' page may contain orders.
        Input: none (runs on the finished POPageResult).
        Output: the same POPageResult, or a ValueError when an 'empty' or 'other' page lists orders.
        """
        if self.page_kind != 'purchase_order' and self.orders:
            raise ValueError('Only purchase_order pages may contain orders')
        return self


# Purpose: One page's result together with its real PDF page number.
# Input: page_number and result (a POPageResult).
# Output: a validated POPageTable.
class POPageTable(StrictModel):
    page_number: int
    result: POPageResult


# Purpose: The complete extracted result for one purchase-order PDF: combined orders, per-page results, warnings and token usage.
# Input: orders, page_results, request_usage, warnings and processing_complete (true once every page finished).
# Output: a validated POExtraction, which is what gets saved in the database.
class POExtraction(StrictModel):
    orders: list[PurchaseOrder] = Field(default_factory=list)
    page_results: list[POPageTable] = Field(default_factory=list)
    request_usage: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    processing_complete: bool = False


class POCorrections(StrictModel):
    """
    Purpose: The body of a PO correction request. Only the orders are editable; the processing
    evidence (page results, usage) stays owned by the server.
    Input: orders - the corrected list of PurchaseOrder objects.
    Output: a validated POCorrections that the correction endpoint applies.
    """
    orders: list[PurchaseOrder]


def load_saved_extraction(payload: dict) -> POExtraction:
    """
    Purpose: Read a saved PO extraction from the database, including older results that still
    contain fields since removed (dates, prices, currencies, names). Those fields are dropped.
    Only database reads use this; new model responses and user corrections still use the
    strict schemas and reject unexpected fields.
    Input: payload - the saved extraction as a dict.
    Output: a validated POExtraction.
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
