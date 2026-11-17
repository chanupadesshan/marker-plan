"""Conservative PO grouping; repeated size rows are evidence, never duplicates to drop."""
from decimal import Decimal
import re
from .po_schema import POExtraction, POPageTable, PurchaseOrder

HEADER_FIELDS = tuple(name for name in PurchaseOrder.model_fields
                      if name not in ('size_rows', 'source_pages', 'warnings'))


def number(value):
    """
    Purpose: Convert a printed quantity into a number. Accepts a decimal with comma or dot, and a
    space (or no-break space) between groups of exactly three digits, as in '1 002'. Ambiguous
    comma/dot grouping such as '1,234.50' is rejected.
    Input: value - the quantity text, or None.
    Output: a Decimal, or None when the value is empty, not numeric, or ambiguous.
    """
    if value is None:
        return None
    text = value.strip()
    if re.fullmatch(r'[+-]?\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?', text):
        text = re.sub(r'[   ]', '', text)
    if not re.fullmatch(r'[+-]?\d+(?:[.,]\d+)?', text):
        return None
    return Decimal(text.replace(',', '.'))


def validate_totals(order):
    """
    Purpose: Check that an order's size quantities add up to its printed total quantity.
    Input: order - a PurchaseOrder.
    Output: nothing. A warning is added to order.warnings when quantities are missing or
    unreadable, or when their sum differs from the total.
    """
    # Refresh only warnings owned by this validator, keeping extraction/review notes.
    order.warnings = [warning for warning in order.warnings
                      if not warning.startswith(('Quantity validation incomplete:', 'Size quantity sum differs'))]
    totals = {number(order.total_quantity)}
    printed = (order.total_quantity or '').strip()
    # A grouped total is accepted only when the actual size sum supports it. Keep
    # number() unchanged: a single comma or dot can genuinely be a decimal mark.
    for separator in (',', '.'):
        if re.fullmatch(r'[+-]?\d{1,3}(?:' + re.escape(separator) + r'\d{3})+', printed):
            totals.add(Decimal(printed.replace(separator, '')))
    totals.discard(None)
    quantities = [number(row.quantity) for row in order.size_rows]
    if not totals or not quantities or any(q is None for q in quantities):
        order.warnings.append('Quantity validation incomplete: total or size quantities are missing/unreadable')
    elif sum(quantities, Decimal(0)) not in totals:
        order.warnings.append('Size quantity sum differs from the printed total quantity')


def combine_po_pages(pages):
    """
    Purpose: Combine the per-page PO results into one list of orders. A contract that continues
    on a later page is merged into one order only when its identity and headers are compatible;
    ambiguous or conflicting ones stay separate with a warning. Repeated size rows are kept.
    Input: pages - a list of (page_number, POPageResult) pairs.
    Output: a POExtraction with the combined orders, the page results and warnings; every
    order's quantities are validated against its total.
    """
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
