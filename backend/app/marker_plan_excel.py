"""One production sheet: stacked marker groups and colour-coded material columns."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from io import BytesIO
import xlsxwriter
from xlsxwriter.utility import xl_rowcol_to_cell, xl_col_to_name
from .marker_plan import PlanRequest, order_demand, planner_input, whole_quantity, nesting_details
from decimal import Decimal
from .marker_planner import Lay, validate_plan

# Sampled from the user's production-sheet screenshot, in material order.
PLIES_COLORS = ['DAEEF3', 'DDD9C4', 'FCD5B4', 'B8CCE4']
USAGE_COLORS = ['D8E4BC', 'B1A0C7', 'FDE9D9', 'FDE9D9']
HEADER_COLORS = ['DCE6F1', 'E4DFEC', 'FCD5B4', '92CDDC']
SEPARATOR = 'FABF8F'


def validate_export(job):
    if job['status'] != 'complete' or not job.get('saved') or not (job.get('summary') or {}).get('complete'):
        raise ValueError('Only complete, saved plans with a validated result for every material can be downloaded.')
    request = PlanRequest.model_validate(job['request'])
    demand = order_demand(request.orders)
    if list(demand.sizes) != job['sizes'] or list(demand.quantities) != job['quantities']:
        raise ValueError('The saved order quantities do not match the plan.')
    if len(request.materials) != len(job['materials']):
        raise ValueError('The saved materials do not match the plan.')
    for material, entry in zip(request.materials, job['materials']):
        result = entry['result'] or {}
        if result.get('status') not in ('OPTIMAL', 'FEASIBLE') or not result.get('validated'):
            raise ValueError('Every material must have a validated plan.')
        validate_plan(planner_input(demand, material, request),
                      [Lay(tuple(lay['counts']), lay['plies']) for lay in result['lays']])
    return request


def _joined(values):
    return ', '.join(dict.fromkeys(str(v) for v in values if v))


def grouped_markers(lays):
    """Group identical ratios within one material; keep original lay numbers and limits visible."""
    groups = {}
    for lay in lays:
        key = tuple(lay['counts'])
        if key not in groups:
            groups[key] = {'marker_id': lay['marker_id'], 'counts': list(key), 'plies': 0, 'lays': []}
        group = groups[key]
        group['plies'] += lay['plies']
        group['lays'].append((lay['number'], lay['plies']))
    return list(groups.values())


def _label(entry, source, orders):
    colors = source.get('colorways') or []
    selected = {str(order.get('color_id')) for order in orders if order.get('color_id')}
    relevant = [color for color in colors if color.get('code') in selected] or colors
    code = entry.get('material_code') or 'Material'
    number = code[1:] if code.startswith('R') else code
    fabric = _joined(color.get('material_color_code') for color in relevant)
    return f'{number}-{fabric}' if fabric else code


def build_marker_plan_excel(job):
    request = validate_export(job)
    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False})
    workbook.set_properties({'title': 'Marker plan', 'author': 'Concord Apparel'})
    sheet = workbook.add_worksheet('Marker plan')
    sheet.set_zoom(85)
    sheet.set_landscape()
    sheet.set_paper(8)
    sheet.fit_to_pages(1, 0)
    sheet.set_margins(0.2, 0.2, 0.25, 0.25)
    sheet.set_default_row(14)
    sheet.hide_gridlines(2)
    cache = {}

    def fmt(color=None, bold=False, border=True, number='0', align='center', wrap=False):
        key = color, bold, border, number, align, wrap
        if key not in cache:
            options = {'font_name': 'Arial', 'font_size': 8, 'font_color': '#000000',
                       'valign': 'vcenter', 'align': align, 'bold': bold, 'num_format': number,
                       'text_wrap': wrap}
            if color:
                options['bg_color'] = '#' + color
            if border:
                options['border'] = 1
            cache[key] = workbook.add_format(options)
        return cache[key]

    sizes, quantities, orders = job['sizes'], job['quantities'], job['request']['orders']
    materials = list(zip(job['materials'], job['request']['materials']))
    labels = [_label(entry, source, orders) for entry, source in materials]
    repetitions = Counter(labels)
    labels = [f'{label} (B{i+1:02d})' if repetitions[label] > 1 else label for i, label in enumerate(labels)]
    slots = max(12, len(sizes))
    ratio_start, pcs = 5, 5 + slots
    plies_start = pcs + 1
    usage_start = plies_start + len(materials)
    lay_count_col = usage_start + len(materials) * 3
    breakdown_col = lay_count_col + 1
    last_col = breakdown_col
    sheet.set_column(0, 0, 26)
    sheet.set_column(1, 4, 11)
    sheet.set_column(ratio_start, pcs - 1, 5.5)
    sheet.set_column(pcs, pcs, 7)
    sheet.set_column(plies_start, usage_start - 1, 12)
    sheet.set_column(usage_start, lay_count_col, 10)
    sheet.set_column(breakdown_col, breakdown_col, 48)
    model = _joined(order.get('model_id') for order in orders) or request.style_number or ''
    contracts = _joined(order.get('label') for order in orders)
    created = datetime.fromisoformat(job['created_at']).astimezone(timezone(timedelta(hours=5, minutes=30))).replace(tzinfo=None)
    metadata = [('ST:NO', model), ('VA...', model), ('DATE', created),
                ('COLOUR', _joined(order.get('color_id') for order in orders)), ('PO NO', contracts), ('BUYER', '')]
    for row, (title, value) in enumerate(metadata):
        sheet.write_string(row, 0, title, fmt(bold=True, border=False, align='left'))
        if isinstance(value, datetime):
            sheet.write_datetime(row, 1, value, fmt(border=False, number='m/d/yyyy'))
        elif value:
            sheet.write_string(row, 1, str(value), fmt(border=False, bold=True))
        else:
            sheet.write_blank(row, 1, None, fmt(border=False))
    # The top PO/colour block repeats the demand for each selected material, as in the reference.
    sheet.write_string(1, 3, 'PO#', fmt(bold=True))
    sheet.write_string(1, 4, 'COLOUR', fmt(bold=True))
    for offset in range(slots):
        if offset < len(sizes):
            sheet.write_string(2, ratio_start + offset, sizes[offset].lstrip('-'), fmt(bold=True))
        else:
            sheet.write_blank(2, ratio_start + offset, None, fmt(bold=True))
    for index in range(len(materials)):
        sheet.write_string(2, plies_start + index, 'ORD/QTY', fmt(bold=True))
    normalize = lambda value: ' '.join(str(value or '').split()).casefold()
    top_row = 3
    for index, _ in enumerate(materials):
        for order in orders:
            sheet.write_string(top_row, 3, order.get('label') or '', fmt(bold=True))
            sheet.write_string(top_row, 4, labels[index], fmt(bold=True))
            by_size = {}
            for size_row in order['size_rows']:
                key = normalize(size_row['size'])
                by_size[key] = by_size.get(key, 0) + whole_quantity(size_row['quantity'])
            values = [by_size.get(normalize(size), 0) for size in sizes]
            for offset, value in enumerate(values):
                sheet.write_number(top_row, ratio_start + offset, value, fmt())
            sheet.write_formula(top_row, plies_start + index,
                                f'=SUM({xl_rowcol_to_cell(top_row,ratio_start)}:{xl_rowcol_to_cell(top_row,ratio_start+len(sizes)-1)})',
                                fmt(PLIES_COLORS[index % 4], bold=True), sum(values))
            top_row += 1
    header = max(7, top_row)
    for col, title in enumerate(['MARKER\nNAME', 'MARKER\nWIDTH', 'MARKER\nLENGTH', 'LAYER\nLENGTH', 'MARKER\nEFF']):
        sheet.merge_range(header, col, header + 2, col, title, fmt(bold=True, wrap=True))
    sheet.merge_range(header, ratio_start, header, pcs - 1, 'MARKER RATIO BREAKDOWN', fmt(bold=True))
    for offset in range(slots):
        sheet.merge_range(header + 1, ratio_start + offset, header + 2, ratio_start + offset,
                          sizes[offset].lstrip('-') if offset < len(sizes) else '',
                          fmt('FFC000' if offset < 6 else '92D050', bold=True))
    sheet.merge_range(header, pcs, header + 2, pcs, 'PCS', fmt(bold=True))
    for index in range(len(materials)):
        color = PLIES_COLORS[index % 4]
        for line, title in enumerate([labels[index], 'TOTAL', 'PLIES']):
            sheet.write_string(header + line, plies_start + index, title, fmt(color, bold=True, wrap=True))
        start = usage_start + 3 * index
        sheet.merge_range(header, start, header, start + 2, labels[index], fmt(HEADER_COLORS[index % 4], bold=True))
        for offset, title in enumerate(['CUT\nQTY', 'MARKER\nFABRIC (m)', 'USED\nFABRIC (m)']):
            sheet.merge_range(header + 1, start + offset, header + 2, start + offset, title,
                              fmt(HEADER_COLORS[index % 4], bold=True, wrap=True))
    sheet.set_row(header, 23)
    sheet.set_row(header + 1, 17)
    sheet.set_row(header + 2, 17)
    for col, title in [(lay_count_col, 'NO. OF\nLAYS'), (breakdown_col, 'PLY BREAKDOWN\n(per lay)')]:
        sheet.merge_range(header, col, header + 2, col, title, fmt(bold=True, wrap=True))
    first_row = header + 3
    sheet.freeze_panes(first_row, ratio_start)
    sheet.repeat_rows(header, header + 2)
    row = first_row
    fabric_totals = [[Decimal(0), Decimal(0)] for _ in materials]  # cached marker/used fabric (m) per material
    for index, (entry, source) in enumerate(materials):
        # A full orange separator identifies the material belonging to this marker group.
        for col in range(last_col + 1):
            sheet.write_blank(row, col, None, fmt(SEPARATOR))
        sheet.merge_range(row, 0, row, 4, f'B{index+1:02d} - {labels[index]} | {entry.get("placement") or ""}',
                          fmt(SEPARATOR, bold=True, align='left', wrap=True))
        sheet.set_row(row, 26)
        row += 1
        markers = grouped_markers(entry['result']['lays'])
        verified = nesting_details(request.materials[index], sizes)
        for position in range(max(4, len(markers) + 2)):
            lay = markers[position] if position < len(markers) else None
            for col in range(5):
                sheet.write_blank(row, col, None, fmt(SEPARATOR if col == 3 else None, number='0.00'))
            if lay:
                sheet.write_string(row, 0, f"{contracts}-{lay['marker_id']}", fmt(align='left', wrap=True))
                breakdown = '; '.join(f'L{number}: {plies}' for number, plies in lay['lays'])
                sheet.set_row(row, max(24, 12 * ((len(breakdown) // 48) + 1)))
                sheet.write_number(row, lay_count_col, len(lay['lays']), fmt(bold=True))
                sheet.write_string(row, breakdown_col, breakdown, fmt(align='left', wrap=True))
                sheet.write_comment(row, plies_start + index,
                                    f'Total across {len(lay["lays"])} lays. Maximum per lay: {entry["max_plies"]}. See the ply breakdown.')
                dimensions = verified.get(tuple(lay['counts']), {})
                for col, key, factor in [(1, 'width_cm', 1), (2, 'length_m', 100), (4, 'efficiency_percent', 1)]:
                    if dimensions.get(key) is not None:
                        sheet.write_number(row, col, float(Decimal(dimensions[key]) * factor), fmt(number='0.00'))
                # Layer length = marker length + 2 cm; blank until a marker length exists.
                marker_length = dimensions.get('length_m')
                if marker_length:
                    length_cm = Decimal(marker_length) * 100
                    fabric_totals[index][0] += length_cm * lay['plies'] / 100
                    fabric_totals[index][1] += (length_cm + 2) * lay['plies'] / 100
                sheet.write_formula(row, 3,
                                    f'=IF(ISNUMBER({xl_rowcol_to_cell(row,2)}),{xl_rowcol_to_cell(row,2)}+2,"")',
                                    fmt(SEPARATOR, number='0.00'),
                                    float(Decimal(marker_length) * 100 + 2) if marker_length is not None else '')
            else:
                sheet.write_blank(row, lay_count_col, None, fmt())
                sheet.write_blank(row, breakdown_col, None, fmt())
            for offset in range(slots):
                if lay and offset < len(sizes):
                    sheet.write_number(row, ratio_start + offset, lay['counts'][offset], fmt(number='0;-0;;@'))
                else:
                    sheet.write_blank(row, ratio_start + offset, None, fmt())
            sheet.write_formula(row, pcs, f'=SUM({xl_rowcol_to_cell(row,ratio_start)}:{xl_rowcol_to_cell(row,pcs-1)})',
                                fmt(SEPARATOR, bold=True), sum(lay['counts']) if lay else 0)
            for material_index in range(len(materials)):
                ply_col = plies_start + material_index
                if lay and material_index == index:
                    sheet.write_number(row, ply_col, lay['plies'], fmt(PLIES_COLORS[material_index % 4], bold=True))
                else:
                    sheet.write_blank(row, ply_col, None, fmt(PLIES_COLORS[material_index % 4]))
                usage = usage_start + 3 * material_index
                sheet.write_formula(row, usage, f'={xl_rowcol_to_cell(row,pcs)}*{xl_rowcol_to_cell(row,ply_col)}',
                                    fmt(USAGE_COLORS[material_index % 4]), sum(lay['counts'])*lay['plies'] if lay and index == material_index else 0)
                for offset, length_col in [(1, 2), (2, 3)]:
                    length, plies = xl_rowcol_to_cell(row, length_col), xl_rowcol_to_cell(row, ply_col)
                    sheet.write_formula(row, usage + offset,
                                        f'=IF(AND(ISNUMBER({length}),ISNUMBER({plies})),{length}*{plies}/100,"")',
                                        fmt(USAGE_COLORS[material_index % 4], number='0.00'),
                                        float((Decimal(dimensions['length_m']) * 100 + (2 if offset == 2 else 0)) * lay['plies'] / 100)
                                        if lay and material_index == index and dimensions.get('length_m') else '')
            row += 1
    total_row = row
    for col in range(last_col + 1):
        sheet.write_blank(row, col, None, fmt('C0C0C0' if col <= pcs else None))
    sheet.merge_range(row, 0, row, 4, 'TOTAL CUT', fmt('C0C0C0', bold=True, align='left'))
    for index in range(len(materials)):
        for offset in range(3):
            col = usage_start + index * 3 + offset
            region = f'{xl_rowcol_to_cell(first_row,col)}:{xl_rowcol_to_cell(total_row-1,col)}'
            formula = f'=SUM({region})' if offset == 0 else f'=IF(COUNT({region})=0,"",SUM({region}))'
            cached = sum(quantities) if offset == 0 else (float(fabric_totals[index][offset - 1]) if fabric_totals[index][offset - 1] else '')
            sheet.write_formula(row, col, formula, fmt(USAGE_COLORS[index % 4], bold=True, number='0' if offset == 0 else '0.00'),
                                cached)
    sheet.write_formula(row, lay_count_col,
                        f'=SUM({xl_rowcol_to_cell(first_row,lay_count_col)}:{xl_rowcol_to_cell(total_row-1,lay_count_col)})',
                        fmt(bold=True), sum(len(entry['result']['lays']) for entry, _ in materials))
    row += 2
    sheet.merge_range(row, 0, row, last_col, 'REMAINING QTY / EXACT ORDER CHECK', fmt(bold=True, border=False, align='left'))
    row += 1
    for index in range(len(materials)):
        color = 'FCD5B4' if index % 4 == 2 else 'DCE6F1'
        sheet.write_string(row, 4, labels[index], fmt(color, bold=True))
        ply = xl_col_to_name(plies_start + index)
        for offset, quantity in enumerate(quantities):
            count_col = xl_col_to_name(ratio_start + offset)
            formula = f'={quantity}-SUMPRODUCT({count_col}{first_row+1}:{count_col}{total_row},${ply}${first_row+1}:${ply}${total_row})'
            sheet.write_formula(row, ratio_start + offset, formula, fmt(color, bold=True), 0)
        row += 1
    # Per-material summary (green band): totals from the TOTAL CUT row and the two consumptions.
    green = '00B050'
    summary_titles = ['CUT QTY', 'MARKER FABRIC (m)', 'USED FABRIC (m)', 'MARKER CONSUMPTION', 'USED CONSUMPTION']
    for col in range(last_col + 1):
        sheet.write_blank(row, col, None, fmt(green))
    sheet.merge_range(row, 0, row, 4, 'SUMMARY BY MATERIAL', fmt(green, bold=True, align='left'))
    for position, title in enumerate(summary_titles):
        start = ratio_start + 2 * position
        sheet.merge_range(row, start, row, start + 1, title, fmt(green, bold=True, wrap=True))
    sheet.set_row(row, 24)
    row += 1
    for index, (entry, source) in enumerate(materials):
        cut, marker_fabric, used_fabric = (xl_rowcol_to_cell(total_row, usage_start + 3 * index + k) for k in range(3))
        cached_cut = sum(quantities)
        cached = [cached_cut, float(fabric_totals[index][0]) or '', float(fabric_totals[index][1]) or '']
        cached += [float(fabric_totals[index][k] / cached_cut) if fabric_totals[index][k] and cached_cut else '' for k in (0, 1)]
        formulas = [f'={cut}', f'={marker_fabric}', f'={used_fabric}',
                    f'=IF(AND(ISNUMBER({marker_fabric}),N({cut})>0),{marker_fabric}/{cut},"")',
                    f'=IF(AND(ISNUMBER({used_fabric}),N({cut})>0),{used_fabric}/{cut},"")']
        for col in range(last_col + 1):
            sheet.write_blank(row, col, None, fmt(green))
        sheet.merge_range(row, 0, row, 1, labels[index], fmt('FFFF00', bold=True))
        sheet.merge_range(row, 2, row, 4, source.get('placement_type') or entry.get('placement') or '',
                          fmt(green, bold=True, align='left', wrap=True))
        for position, formula in enumerate(formulas):
            start = ratio_start + 2 * position
            number = '0' if position == 0 else '0.00' if position < 3 else '0.0000'
            sheet.merge_range(row, start, row, start + 1, '', fmt(green, bold=True, number=number))
            sheet.write_formula(row, start, formula, fmt(green, bold=True, number=number), cached[position])
        row += 1
    for col in range(last_col + 1):
        sheet.write_blank(row, col, None, fmt(green, border=False))
    for start, title in [(0, 'PREPARED BY'), (2, 'CHECKED BY'), (ratio_start, 'APPROVED BY')]:
        end = {0: 1, 2: 4, ratio_start: ratio_start + 5}[start]
        sheet.merge_range(row, start, row, end, f'........................  {title}', fmt(green, bold=True, border=False))
    sheet.print_area(0, 0, row, last_col)
    workbook.close()
    return buffer.getvalue()
