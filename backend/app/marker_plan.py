"""Cutting plans: turn the chosen PO size rows and BOM materials into solver inputs, run the
solver once per material and describe the result for the Marker Plan screen.

The solver (app/marker_planner) chooses marker size combinations and lay plies so that every
size is produced exactly. It does not nest pattern pieces or measure real fabric use, so
nothing here reports marker lengths, efficiency or fabric savings.
"""
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Literal
from uuid import UUID
from time import monotonic
from pydantic import Field, field_validator, model_validator
from .marker_planner import PlannerInput, PlanResult, capacity_from_length, solve_plan, validate_plan
from .marker_planner.planner import _validate_inputs
from .po_merge import number
from .techpack_schema import StrictModel, Colorway

# Consumption units accepted for the capacity calculation, as metres per unit.
LENGTH_UNITS = {'m': Decimal('1'), 'cm': Decimal('0.01'), 'mm': Decimal('0.001'), 'yd': Decimal('0.9144')}
# Statuses that come with a complete, validated plan.
PLAN_STATUSES = ('OPTIMAL', 'FEASIBLE')
# The least search time per material a plan may ask for, and the value used when none is given.
MIN_TIME_LIMIT_SECONDS = 60.0


# Purpose: One printed size line of a chosen purchase order, sent as extracted (text quantity).
# Input: size label and quantity (text such as '32' or '1 002', or a whole number).
# Output: a validated PlanSizeRow; true/false is rejected as a quantity.
class PlanSizeRow(StrictModel):
    size: str | None = Field(default=None, max_length=100)
    quantity: str | int | None = None

    @field_validator('quantity', mode='before')
    @classmethod
    def no_booleans(cls, value):
        """
        Purpose: Stop true/false from being read as the quantities 1/0.
        Input: value - the submitted quantity.
        Output: the same value, or a ValueError for a boolean.
        """
        if isinstance(value, bool):
            raise ValueError('Quantity must be a whole number')
        return value


# Purpose: One chosen purchase order (contract) with its size rows.
# Input: label - the contract number shown in messages; size_rows - its printed size lines.
# Output: a validated PlanOrder.
class PlanOrder(StrictModel):
    label: str | None = Field(default=None, max_length=200)
    tech_pack_reference: str | None = Field(default=None, max_length=200)
    model_id: str | None = Field(default=None, max_length=200)
    quality_id: str | None = Field(default=None, max_length=200)
    color_id: str | None = Field(default=None, max_length=200)
    source_filename: str | None = Field(default=None, max_length=255)
    size_rows: list[PlanSizeRow] = Field(default_factory=list, max_length=500)


# Purpose: One chosen BOM material row with the cutting settings that apply to it.
# Input: material_code, description, placement and page_number (for display); consumption - length per
# garment in 'unit'; max_plies - the most layers one lay of this material may have.
# Output: a validated PlanMaterial.
class NestingMarker(StrictModel):
    label: str | None = Field(default=None, max_length=200)
    length_m: Decimal = Field(gt=0, le=1000)
    width_cm: Decimal | None = Field(default=None, gt=0, le=10000)
    efficiency_percent: Decimal | None = Field(default=None, ge=0, le=100)
    verified: Literal[True]
    size_rows: list[PlanSizeRow] = Field(min_length=1, max_length=500)


class PlanMaterial(StrictModel):
    material_code: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    placement: str | None = Field(default=None, max_length=500)
    placement_type: str | None = Field(default=None, max_length=500)
    composition: str | None = Field(default=None, max_length=1000)
    colorways: list[Colorway] = Field(default_factory=list, max_length=100)
    page_number: int | None = None
    consumption: Decimal = Field(gt=0, le=100_000)
    unit: Literal['m', 'cm', 'mm', 'yd'] = 'm'
    max_plies: int = Field(ge=1, le=1_000_000)
    nesting_markers: list[NestingMarker] = Field(default_factory=list, max_length=2000)


# Purpose: A request to plan the cutting of the chosen POs for each chosen material.
# Input: orders, materials, table_length_m (usable table length in metres), min_plies (normal minimum
# layers per lay) and time_limit_seconds (solver budget for each material, 60 to 300 seconds; 60 if not given).
# Output: a validated PlanRequest.
class PlanRequest(StrictModel):
    tech_pack_id: UUID | None = None
    tech_pack_filename: str | None = Field(default=None, max_length=255)
    style_number: str | None = Field(default=None, max_length=200)
    tech_pack_number: str | None = Field(default=None, max_length=200)
    orders: list[PlanOrder] = Field(min_length=1, max_length=100)
    materials: list[PlanMaterial] = Field(min_length=1, max_length=50)
    table_length_m: Decimal = Field(gt=0, le=1000)
    min_plies: int = Field(ge=1, le=1_000_000)
    time_limit_seconds: float = Field(default=MIN_TIME_LIMIT_SECONDS, ge=MIN_TIME_LIMIT_SECONDS, le=300)

    @model_validator(mode='after')
    def validate_nesting(self):
        known = {' '.join(str(row.size or '').split()).casefold() for order in self.orders for row in order.size_rows}
        for material in self.materials:
            for marker in material.nesting_markers:
                if marker.length_m > self.table_length_m:
                    raise ValueError('Every verified marker length must fit the usable table length.')
                counts = [whole_quantity(row.quantity) for row in marker.size_rows]
                if any(count is None for count in counts) or not 1 <= sum(counts) <= 1000:
                    raise ValueError('Verified marker ratios must contain whole counts and 1 to 1000 sets.')
                if any(not row.size or ' '.join(row.size.split()).casefold() not in known for row in marker.size_rows):
                    raise ValueError('Verified marker sizes must match the selected purchase orders.')
        return self


class PlanInputError(ValueError):
    """
    Purpose: Report every problem found in the chosen PO rows at once, so they can all be fixed together.
    Input: problems - a list of readable messages.
    Output: an exception whose text joins the messages.
    """
    def __init__(self, problems):
        super().__init__(' '.join(problems))
        self.problems = list(problems)


# Purpose: The combined size demand of the chosen purchase orders, in first-printed size order.
# Input: sizes, quantities (whole numbers, same order) and warnings about how rows were combined.
# Output: an OrderDemand.
@dataclass
class OrderDemand:
    sizes: tuple[str, ...]
    quantities: tuple[int, ...]
    warnings: list[str] = field(default_factory=list)


def whole_quantity(value):
    """
    Purpose: Read a printed PO quantity as a whole number of garments.
    Input: value - text such as '32', '1 002' or '32.0', a whole number, or None.
    Output: a nonnegative int, or None when the value is missing, unreadable, negative or fractional.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    parsed = number(str(value))
    if parsed is None or parsed < 0 or parsed != parsed.to_integral_value():
        return None
    return int(parsed)


def order_demand(orders):
    """
    Purpose: Add up the chosen orders' size rows into one demand per size. Size labels are matched
    after trimming, ignoring case; the first printed spelling and position are kept.
    Input: orders - a list of PlanOrder.
    Output: an OrderDemand. Raises PlanInputError when a row has no size or no readable whole-number
    quantity, or when there are no garments at all.
    """
    index, sizes, quantities, problems, warnings = {}, [], [], [], []
    for number_in_list, order in enumerate(orders, 1):
        name = f'Contract {order.label}' if order.label else f'Purchase order {number_in_list}'
        if not order.size_rows:
            problems.append(f'{name} has no size rows.')
        repeats = {}
        for row_number, row in enumerate(order.size_rows, 1):
            where = f'{name}, size row {row_number}'
            label = ' '.join((row.size or '').split())
            if not label:
                problems.append(f'{where} has no size.')
                continue
            quantity = whole_quantity(row.quantity)
            if quantity is None:
                problems.append(f'{where} ({label}) has no quantity.' if row.quantity in (None, '') else
                                f'{where} ({label}): quantity "{row.quantity}" is not a whole number of garments.')
                continue
            key = label.casefold()
            if key not in index:
                index[key] = len(sizes)
                sizes.append(label)
                quantities.append(0)
            quantities[index[key]] += quantity
            repeats[key] = repeats.get(key, 0) + 1
        for key, count in repeats.items():
            if count > 1:
                warnings.append(f'{name} lists size {sizes[index[key]]} in {count} rows; their quantities were added together.')
    if problems:
        raise PlanInputError(problems)
    if not sum(quantities):
        raise PlanInputError(['The chosen purchase orders have no garments to cut.'])
    return OrderDemand(tuple(sizes), tuple(quantities), warnings)


def consumption_in_metres(material):
    """
    Purpose: Convert a material's consumption per garment to metres.
    Input: material - a PlanMaterial.
    Output: the consumption in metres as a Decimal.
    """
    return material.consumption * LENGTH_UNITS[material.unit]


def material_capacity(table_length_m, material):
    """
    Purpose: Work out how many garment sets fit on one marker: floor(table length / consumption),
    with both lengths in metres.
    Input: table_length_m - usable table length in metres; material - a PlanMaterial.
    Output: the capacity as an int (can be 0 when one garment is longer than the table).
    """
    if material.nesting_markers:
        return max(sum(whole_quantity(row.quantity) for row in marker.size_rows) for marker in material.nesting_markers)
    return capacity_from_length(float(table_length_m), float(consumption_in_metres(material)))


def nesting_details(material, sizes):
    details = {}
    normalize = lambda value: ' '.join(str(value or '').split()).casefold()
    for marker in material.nesting_markers:
        by_size = {}
        for row in marker.size_rows:
            key = normalize(row.size)
            by_size[key] = by_size.get(key, 0) + whole_quantity(row.quantity)
        pattern = tuple(by_size.get(normalize(size), 0) for size in sizes)
        if pattern not in details or marker.length_m < Decimal(details[pattern]['length_m']):
            details[pattern] = {'nesting_label': marker.label, 'length_m': str(marker.length_m),
                'width_cm': str(marker.width_cm) if marker.width_cm is not None else None,
                'efficiency_percent': str(marker.efficiency_percent) if marker.efficiency_percent is not None else None}
    return details


def planner_input(demand, material, request):
    """
    Purpose: Build and check the solver input for one material.
    Input: demand - the OrderDemand; material - a PlanMaterial; request - the PlanRequest (table length,
    minimum plies and time budget).
    Output: a PlannerInput. Raises ValueError with a readable reason when the capacity is below 1 or the
    solver would reject the settings (for example a minimum above this material's maximum plies).
    """
    capacity = material_capacity(request.table_length_m, material)
    if capacity < 1:
        raise ValueError(f'One garment needs {consumption_in_metres(material).normalize():f} m, longer than the '
                         f'{request.table_length_m.normalize():f} m table, so the marker capacity is below 1.')
    if request.min_plies > material.max_plies:
        raise ValueError(f'The normal minimum of {request.min_plies} plies is above this material\'s '
                         f'maximum of {material.max_plies} plies.')
    data = PlannerInput(demand.sizes, demand.quantities, capacity, material.max_plies,
                        request.min_plies, float(request.time_limit_seconds),
                        allowed_markers=tuple(nesting_details(material, demand.sizes)) if material.nesting_markers else None)
    _validate_inputs(data)
    return data


def failure(status, message):
    """
    Purpose: Describe a material that has no plan (bad settings or a solver error).
    Input: status - e.g. 'INVALID_INPUT' or 'ERROR'; message - the reason to show.
    Output: a result dict shaped like summarize() with no lays.
    """
    return {'status': status, 'message': message, 'marker_count': 0, 'one_marker_shortcut': False, 'lay_count': 0,
            'secondary_optimal': False, 'marker_lower_bound': None, 'elapsed_seconds': 0.0,
            'validated': False, 'marker_minimum_proven': False, 'lay_minimum_proven': False,
            'markers': [], 'lays': [], 'production': [], 'progress': []}


def summarize(data, result, validated, prefix=''):
    """
    Purpose: Turn a solver PlanResult into the JSON shown on screen: unique markers in first-use order
    with their lays, every lay, and required versus produced quantity per size. All of the solver's own
    fields (status, message, marker_count, secondary_optimal, marker_lower_bound, elapsed time and
    progress) are kept as they are.
    Input: data - the PlannerInput; result - its PlanResult; validated - True when validate_plan() passed;
    prefix - marker ID prefix such as 'B01-'.
    Output: a result dict. one_marker_shortcut is True when the order's size ratio fits on one marker, so the
    plan was worked out directly without a search.
    """
    markers, ids, lays = [], {}, []
    for lay_number, lay in enumerate(result.lays, 1):
        if lay.marker not in ids:
            ids[lay.marker] = len(markers)
            markers.append({'id': f'{prefix}M{len(markers) + 1:02d}', 'counts': list(lay.marker),
                            'sets_per_marker': sum(lay.marker), 'lay_numbers': [], 'lay_count': 0, 'total_plies': 0})
        marker = markers[ids[lay.marker]]
        marker['lay_numbers'].append(lay_number)
        marker['lay_count'] += 1
        marker['total_plies'] += lay.plies
        lays.append({'number': lay_number, 'marker_id': marker['id'], 'counts': list(lay.marker),
                     'plies': lay.plies, 'sets': sum(lay.marker) * lay.plies})
    for marker in markers:
        marker['sets_cut'] = marker['sets_per_marker'] * marker['total_plies']
    produced = [sum(lay.marker[size] * lay.plies for lay in result.lays) for size in range(len(data.sizes))]
    proven = result.status == 'OPTIMAL'
    # solve_plan() answers with one marker only through its ratio shortcut: its searches run only after
    # that check has shown one marker cannot work (the candidate search even requires two or more).
    shortcut = proven and result.marker_count == 1 and data.allowed_markers is None
    return {'status': result.status, 'message': result.message, 'marker_count': result.marker_count,
            'optimization_scope': 'verified_nesting_catalogue' if data.allowed_markers is not None else 'consumption_capacity',
            'one_marker_shortcut': shortcut,
            'lay_count': len(result.lays), 'secondary_optimal': result.secondary_optimal,
            'marker_lower_bound': result.marker_lower_bound, 'elapsed_seconds': round(result.elapsed_seconds, 3),
            'validated': validated, 'marker_minimum_proven': proven,
            'lay_minimum_proven': proven and result.secondary_optimal,
            'markers': markers, 'lays': lays,
            'production': [{'size': size, 'required': required, 'produced': made, 'difference': made - required}
                           for size, required, made in zip(data.sizes, data.quantities, produced)],
            'progress': [progress_dict(event) for event in result.progress]}


def progress_dict(event):
    """
    Purpose: Convert one solver ProgressEvent into JSON.
    Input: event - a ProgressEvent.
    Output: a dict with phase, elapsed_seconds (rounded), marker_count, lay_count, marker_minimum_proven and status.
    """
    value = asdict(event)
    value['elapsed_seconds'] = round(value['elapsed_seconds'], 3)
    return value


def run_material(data, on_progress=None, prefix=''):
    """
    Purpose: Solve one material and independently check the plan before it is shown. The solver picks its
    own search method; nothing here chooses between its compact and direct searches.
    Input: data - a checked PlannerInput; on_progress - optional callback for each ProgressEvent;
    prefix - marker ID prefix.
    Output: a result dict (see summarize). A plan that fails validate_plan(), or a solver crash, becomes
    status 'ERROR' with no lays, never a plan to cut.
    """
    started = monotonic()
    incumbent = None
    if data.incumbent_lays:
        try:
            validate_plan(data, list(data.incumbent_lays))
            incumbent = list(data.incumbent_lays)
        except ValueError:
            pass
    def retained(message):
        return PlanResult('FEASIBLE', incumbent, len({lay.marker for lay in incumbent}),
                          elapsed_seconds=monotonic() - started,
                          message=message)
    try:
        result = solve_plan(data, on_progress)
    except ValueError as exc:
        # Inputs were checked beforehand, so this is the solver's own validation of its plan failing.
        if incumbent is None:
            return failure('ERROR', f'The solver\'s plan failed independent validation: {exc}')
        result = retained('Kept the earlier validated plan after the new search failed validation.')
    except Exception as exc:  # noqa: BLE001 - any solver failure is reported, not raised to the user
        if incumbent is None:
            return failure('ERROR', f'The solver stopped with an error: {exc}')
        result = retained('Kept the earlier validated plan after the new search was interrupted.')
    if incumbent is not None and (result.status not in PLAN_STATUSES or
        (len({lay.marker for lay in incumbent}), len(incumbent)) < (result.marker_count, len(result.lays))):
        result = retained('Kept the best earlier validated plan; this search did not improve it.')
    validated = False
    if result.status in PLAN_STATUSES:
        try:
            validate_plan(data, result.lays)
            validated = True
        except ValueError as exc:
            if incumbent is None:
                return failure('ERROR', f'The solver\'s plan failed independent validation: {exc}')
            result = retained('Kept the earlier validated plan after the new result failed independent validation.')
            validated = True
    return summarize(data, result, validated, prefix)
