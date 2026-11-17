// Cutting-plan helpers: map the chosen POs and materials into the solver request and describe results.
// The solver plans size combinations and plies only; Lectra nests the pattern pieces afterwards.

export const DEFAULT_PLAN_SETTINGS = { table_length_m: '', min_plies: '10', time_limit_seconds: '60', materials: {} };
export const LENGTH_UNITS = ['m', 'cm', 'mm', 'yd'];
// Exact metres per unit as [numerator, denominator], matching the server.
const UNIT_FACTORS = { m: [1n, 1n], cm: [1n, 100n], mm: [1n, 1000n], yd: [9144n, 10000n] };
const BOM_UNITS = { m: 'm', mt: 'm', mtr: 'm', mtrs: 'm', meter: 'm', meters: 'm', metre: 'm', metres: 'm',
  cm: 'cm', mm: 'mm', yd: 'yd', yds: 'yd', yard: 'yd', yards: 'yd' };
const PLAN_STATUSES = ['OPTIMAL', 'FEASIBLE'];

/** Purpose: Normalize a typed decimal ('0,95' → '0.95'). Input: text. Output: the text, or null when not a plain decimal. */
export function decimalText(text) {
  const value = String(text ?? '').trim().replace(',', '.');
  return /^\d+(\.\d+)?$/.test(value) ? value : null;
}

/** Purpose: Exact fraction of a decimal string. Input: text. Output: { numerator, denominator } BigInts, or null. */
function fraction(text) {
  const value = decimalText(text);
  if (value === null) return null;
  const [whole, part = ''] = value.split('.');
  return { numerator: BigInt(whole + part), denominator: 10n ** BigInt(part.length) };
}

/**
 * Purpose: Garment sets that fit on one marker: floor(table length / consumption), computed exactly so it
 * matches the server (no floating-point rounding).
 * Input: lengthText - table length in metres; consumptionText - length per garment; unit - 'm', 'cm', 'mm' or 'yd'.
 * Output: the capacity as a number, or null when an input is missing or not positive.
 */
export function capacityPreview(lengthText, consumptionText, unit) {
  const length = fraction(lengthText), consumption = fraction(consumptionText), factor = UNIT_FACTORS[unit];
  if (!length || !consumption || !factor || !length.numerator || !consumption.numerator) return null;
  return Number((length.numerator * consumption.denominator * factor[1]) / (length.denominator * consumption.numerator * factor[0]));
}

/** Purpose: Read a whole number of at least 1. Input: text. Output: the number, or null. */
function positiveWhole(text) {
  const value = String(text ?? '').trim();
  return /^\d+$/.test(value) && Number(value) >= 1 ? Number(value) : null;
}

// A range wider than this is not listed value by value; its two ends are offered instead.
const MAX_LISTED_RANGE = 500;

/**
 * Purpose: Every whole-number maximum ply the plies table allows for a material. A range such as '70-75'
 * gives each value from 70 to 75; several related rows ('50-60', '80') give all their values together.
 * Input: info - the material's plies information ({ matches: [{ col_d }] }), or nothing.
 * Output: the allowed values, ascending and without repeats (empty when the table has no number).
 */
export function plyChoices(info) {
  const values = new Set();
  for (const match of info?.matches || []) {
    const text = String(match.col_d ?? '');
    const range = text.match(/^\s*(\d+)\s*[-–]\s*(\d+)\s*$/);
    if (range) {
      const [low, high] = [Number(range[1]), Number(range[2])].sort((a, b) => a - b);
      if (high - low <= MAX_LISTED_RANGE) for (let value = low; value <= high; value++) values.add(value);
      else values.add(low).add(high);
    } else {
      for (const found of text.match(/\d+(?:[.,]\d+)?/g) || []) values.add(Number(found.replace(',', '.')));
    }
  }
  return [...values].filter(value => Number.isInteger(value) && value >= 1).sort((a, b) => a - b);
}

/** Purpose: The plies-table entries behind a material, for display. Input: info. Output: text such as '50-60, 80'. */
export function plySourceText(info) {
  return (info?.matches || []).map(match => match.col_d).filter(Boolean).join(', ');
}

/**
 * Purpose: Starting settings for a material: its BOM quantity as consumption when the BOM unit is a length,
 * and its maximum plies when the plies table gives exactly one value. A range or several different values
 * are left blank so the user must choose one.
 * Input: row - the BOM material; plyInfo - plies information by material code.
 * Output: { consumption, unit, max_plies } as form text.
 */
export function defaultMaterialSettings(row, plyInfo) {
  const unit = BOM_UNITS[String(row?.unit ?? '').trim().toLowerCase()];
  const quantity = decimalText(row?.quantity);
  const choices = plyChoices(plyInfo?.[row?.material_code]);
  return { consumption: unit && quantity && Number(quantity) > 0 ? quantity : '', unit: unit || 'm',
    max_plies: choices.length === 1 ? String(choices[0]) : '' };
}

/**
 * Purpose: Check the cutting settings before a plan can be generated.
 * Input: settings - { table_length_m, min_plies, time_limit_seconds }; materials - [{ key, settings, plyChoices }]
 * (plyChoices: the values the plies table allows, so a missing choice gets the right message).
 * Output: { form: {field: message}, materials: {key: {field: message}}, pendingChoices: [key of a material whose
 * plies range still needs a choice], count } (count is 0 when a plan can be generated).
 */
export function planFormErrors(settings, materials, sizes) {
  const form = {}, byMaterial = {}, pending = [];
  const length = decimalText(settings.table_length_m);
  if (!length || !(Number(length) > 0)) form.table_length_m = 'Enter the usable table length in metres.';
  const minimum = positiveWhole(settings.min_plies);
  if (minimum === null) form.min_plies = 'Enter a whole number of plies, 1 or more.';
  const time = Number(String(settings.time_limit_seconds ?? '').trim());
  if (!String(settings.time_limit_seconds ?? '').trim() || !Number.isFinite(time) || time < 60 || time > 300) form.time_limit_seconds = 'Enter 60 to 300 seconds.';
  for (const { key, settings: material, plyChoices: choices = [] } of materials) {
    const problems = {};
    const consumption = decimalText(material.consumption);
    if (!consumption || !(Number(consumption) > 0)) problems.consumption = 'Enter the length per garment.';
    else if (!LENGTH_UNITS.includes(material.unit)) problems.consumption = 'Choose a length unit.';
    else if (!material.nesting_markers?.length && length && capacityPreview(length, consumption, material.unit) < 1) problems.consumption = 'One garment is longer than the table, so capacity is below 1.';
    if (material.nesting_markers?.length && nestingErrors(material.nesting_markers, length, sizes || material.nesting_markers.flatMap(marker => marker.size_rows.map(row => row.size))).length) problems.nesting = 'Check the verified nesting ratios, lengths and confirmations below.';
    const maximum = positiveWhole(material.max_plies);
    // A plies range waiting for the user's choice is not a mistake: it blocks the plan without an error message.
    if (maximum === null && choices.length > 1 && !material.custom_max_plies && !String(material.max_plies ?? '').trim()) pending.push(key);
    else if (maximum === null) problems.max_plies = 'Enter a whole number of plies, 1 or more.';
    else if (minimum !== null && maximum < minimum) problems.max_plies = `Must be at least the minimum of ${minimum} plies.`;
    if (Object.keys(problems).length) byMaterial[key] = problems;
  }
  return { form, materials: byMaterial, pendingChoices: pending,
    count: Object.keys(form).length + Object.keys(byMaterial).length + pending.length };
}

/**
 * Purpose: The individual purchase orders the user confirmed. Selections saved before orders were kept with
 * them are read back from their ids, which contain the order.
 * Input: poSelection - { ids, orders? }.
 * Output: a list of PO objects.
 */
export function selectedPlanOrders(poSelection) {
  if (Array.isArray(poSelection?.orders)) return poSelection.orders;
  return (poSelection?.ids || []).map(id => { try { return JSON.parse(id)[2]; } catch { return null; } }).filter(Boolean);
}

/**
 * Purpose: Build the server request: printed PO size rows (the server combines them by size and checks the
 * quantities), each material's consumption and maximum plies, and the order-level cutting settings.
 * Input: orders - PO objects; materials - [{ row, pageNumber, settings }]; settings - order-level settings.
 * Output: the request body for POST /api/marker-plans.
 */
export function buildPlanRequest(orders, materials, settings, source = {}) {
  const text = (value, limit) => (value == null || value === '' ? null : String(value).slice(0, limit));
  return {
    ...(source.id ? { tech_pack_id: source.id } : {}),
    ...(source.filename ? { tech_pack_filename: text(source.filename, 255) } : {}),
    ...(source.style_number ? { style_number: text(source.style_number, 200) } : {}),
    ...(source.tech_pack_number ? { tech_pack_number: text(source.tech_pack_number, 200) } : {}),
    orders: orders.map(order => ({ label: text(order.contract_number, 200),
      ...Object.fromEntries(['tech_pack_reference', 'model_id', 'quality_id', 'color_id']
        .filter(key => order[key] != null).map(key => [key, text(order[key], 200)])),
      ...(order.filename ? { source_filename: text(order.filename, 255) } : {}),
      size_rows: (order.size_rows || []).map(row => ({ size: text(row.size, 100), quantity: row.quantity == null ? null : String(row.quantity) })) })),
    materials: materials.map(({ row, pageNumber, settings: material }) => ({
      material_code: text(row.material_code, 200), description: text(row.description, 500), placement: text(row.placement, 500),
      ...(row.composition ? { composition: text(row.composition, 1000) } : {}),
      ...(row.placement_type ? { placement_type: text(row.placement_type, 500) } : {}),
      ...(row.colorways?.length ? { colorways: row.colorways.map(color => Object.fromEntries(
        ['code', 'name', 'material_color_code', 'material_color_name', 'fabric_reference']
          .filter(key => color[key] != null).map(key => [key, text(color[key], 500)]))) } : {}),
      page_number: Number.isInteger(pageNumber) ? pageNumber : null,
      ...(material.nesting_markers?.length ? { nesting_markers: nestingPayload(material.nesting_markers) } : {}),
      consumption: decimalText(material.consumption), unit: material.unit, max_plies: Number(String(material.max_plies).trim()) })),
    table_length_m: decimalText(settings.table_length_m),
    min_plies: Number(String(settings.min_plies).trim()),
    time_limit_seconds: Number(String(settings.time_limit_seconds).trim()),
  };
}

/** Purpose: Whether a plan job still needs polling. Input: job. Output: true while queued or running. */
export function isPlanRunning(job) {
  return Boolean(job) && job.status !== 'complete';
}

const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;

/**
 * Purpose: Plain-language outcome of one material's plan. Marker-count proof and lay-count proof are reported
 * separately, and a time-limited or restricted result is never described as proven.
 * Input: result - the material result from the server; timeLimit - its search time in seconds.
 * Output: { tone ('approved' | 'needs_review' | 'failed'), label, lines: [text] }.
 */
export function planOutcome(result, timeLimit) {
  const markers = plural(result.marker_count, 'unique marker'), lays = plural(result.lay_count, 'lay');
  switch (result.status) {
    case 'OPTIMAL': return { tone: 'approved', label: 'Minimum markers proven', lines: [
      `${markers} is the proven minimum for these cutting rules.`,
      result.lay_minimum_proven ? `${lays} is also the proven minimum for that marker count.`
        : `The lay count (${lays}) is not proven to be the minimum.`] };
    case 'FEASIBLE': return { tone: 'needs_review', label: 'Valid plan · not proven minimal', lines: [
      `This plan meets every cutting rule with ${markers} and ${lays}, but the search was time-limited or restricted, so fewer markers may be possible.`,
      Number.isInteger(result.marker_lower_bound) && result.marker_lower_bound < result.marker_count
        ? `At least ${plural(result.marker_lower_bound, 'marker')} are needed.` : null,
      'The lay count is not proven to be the minimum.'].filter(Boolean) };
    case 'INFEASIBLE': return { tone: 'failed', label: 'No plan possible', lines: [
      'No plan can meet these cutting rules for the order quantities. Try a lower minimum plies, a higher maximum plies, or check the consumption and table length.'] };
    case 'UNKNOWN': return { tone: 'failed', label: 'Search time ran out', lines: [
      `No plan was found within ${plural(timeLimit, 'second')}. This does not prove that no plan exists; try a longer search time.`] };
    case 'MODEL_TOO_LARGE': return { tone: 'failed', label: 'Too large to solve', lines: [
      'This order exceeds the solver\'s resource limits, so no plan was searched for. Check the quantities, capacity and maximum plies.'] };
    case 'INVALID_INPUT': return { tone: 'failed', label: 'Check settings', lines: [result.message] };
    default: return { tone: 'failed', label: 'Solver error', lines: [result.message || 'The plan could not be completed.'] };
  }
}

/** Purpose: Readable solve time. Input: seconds. Output: 'under 0.1 s' for very fast solves, otherwise e.g. '2.1 s'. */
export function solveTimeText(seconds) {
  const value = Number(seconds) || 0;
  return value < 0.1 ? 'under 0.1 s' : `${value.toFixed(1)} s`;
}

/** Purpose: Readable name of a solver progress phase. Input: phase. Output: text. */
export function phaseText(phase) {
  return { building: 'Preparing the search', markers: 'Searching for fewer markers', marker_proof: 'Marker minimum proven',
    lays: 'Reducing the number of lays', complete: 'Checking the plan' }[phase] || 'Searching';
}

/** Purpose: Whether a material result has a usable, validated plan. Input: result. Output: true or false. */
export function hasPlan(result) {
  return Boolean(result) && PLAN_STATUSES.includes(result.status) && result.validated;
}
import { nestingErrors, nestingPayload } from './nesting.js';
