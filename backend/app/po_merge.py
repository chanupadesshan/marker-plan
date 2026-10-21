"""Conservative PO grouping; repeated size rows are evidence, never duplicates to drop."""
from decimal import Decimal
import re
from .po_schema import POExtraction, POPageTable, PurchaseOrder

HEADER_FIELDS = tuple(name for name in PurchaseOrder.model_fields
                      if name not in ('size_rows', 'source_pages', 'warnings'))


def number(value):
    """Accept an ungrouped decimal with either comma or dot; reject ambiguous grouping."""
    if value is None or not re.fullmatch(r'[+-]?\d+(?:[.,]\d+)?', value.strip()):
        return None
    return Decimal(value.strip().replace(',', '.'))


def validate_totals(order):
    total = number(order.total_quantity)
    quantities = [number(row.quantity) for row in order.size_rows]
    if total is None or not quantities or any(q is None for q in quantities):
        order.warnings.append('Quantity validation incomplete: total or size quantities are missing/unreadable')
    elif sum(quantities, Decimal(0)) != total:
        order.warnings.append('Size quantity sum differs from the printed total quantity')


def combine_po_pages(pages):
    result = POExtraction()
    for page_number, page in pages:
        result.page_results.append(POPageTable(page_number=page_number, result=page.model_copy(deep=True)))
        result.warnings.extend(f'Page {page_number}: {warning}' for warning in page.warnings)
        for original in page.orders:
            order = original.model_copy(deep=True)
            order.source_pages = [page_number]
            for row in order.size_rows:
                row.source_page = page_number
            candidates = [existing for existing in result.orders
                          if order.contract_number and existing.contract_number == order.contract_number]
            compatible = [existing for existing in candidates if all(
                not getattr(order, field) or not getattr(existing, field)
                or getattr(order, field) == getattr(existing, field) for field in HEADER_FIELDS)]
            # Once an identity is conflicted, subsequent continuations remain ambiguous.
            if len(candidates) == 1 and len(compatible) == 1:
                existing = compatible[0]
                for field in HEADER_FIELDS:
                    if not getattr(existing, field):
                        setattr(existing, field, getattr(order, field))
                existing.size_rows.extend(order.size_rows)
                existing.source_pages = sorted(set(existing.source_pages + order.source_pages))
                existing.warnings.extend(order.warnings)
            else:
                if candidates or not order.contract_number:
                    warning = f'Page {page_number}: ambiguous or conflicting contract identity; kept separate'
                    result.warnings.append(warning)
                    order.warnings.append(warning)
                result.orders.append(order)
    for order in result.orders:
        validate_totals(order)
    return result
