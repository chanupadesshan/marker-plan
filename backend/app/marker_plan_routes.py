"""Cutting-plan API: start a plan for the chosen POs and materials, then poll it for progress.

Each selected material is solved separately in a background thread. Inputs and result snapshots
are saved in PostgreSQL; only high-frequency live progress is held in memory.
"""
import threading
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from dataclasses import replace
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from . import marker_plan_store as store
from .audit import record
from .auth import require_user
from .marker_plan import (PLAN_STATUSES, PlanInputError, PlanRequest, consumption_in_metres, failure,
                          material_capacity, order_demand, planner_input, progress_dict, run_material)
from .marker_plan import PlanMaterial, nesting_details

router = APIRouter(prefix='/api/marker-plans', tags=['Marker plans'])

MAX_JOBS = 50
# One solve at a time: CP-SAT already uses several workers, and parallel jobs would share the CPU
# and make every time budget less effective.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='marker-plan')
_jobs = {}
_inputs = {}
_lock = threading.Lock()
logger = logging.getLogger(__name__)


def submit(function, *args):
    """
    Purpose: Start background work. Tests replace this to run jobs immediately.
    Input: function and its arguments.
    Output: nothing.
    """
    _executor.submit(function, *args)


def now():
    """Purpose: Current UTC time as ISO text. Input: none. Output: the timestamp string."""
    return datetime.now(timezone.utc).isoformat()


def summary(job):
    """
    Purpose: Totals across materials once every material is finished. The order is complete only when
    every material has a validated plan; marker and lay totals are then summed (they are not garment totals).
    Input: job - the stored job dict.
    Output: {'complete', 'marker_count', 'lay_count', 'failed'}, or None while materials are still running.
    """
    results = [entry['result'] for entry in job['materials']]
    if any(result is None for result in results):
        return None
    planned = [result for result in results if result['status'] in PLAN_STATUSES and result['validated']]
    complete = len(planned) == len(results)
    return {'complete': complete,
            'marker_count': sum(result['marker_count'] for result in results) if complete else None,
            'lay_count': sum(result['lay_count'] for result in results) if complete else None,
            'failed': len(results) - len(planned)}


def snapshot(job):
    """
    Purpose: A copy of a job that is safe to send while its thread keeps updating it.
    Input: job - the stored job dict (the caller holds the lock).
    Output: the job dict with its summary.
    """
    value = deepcopy(job)
    value['summary'] = summary(job)
    return value


def persist(job):
    """Never label a failed database write as saved, and retain the live result for review."""
    value = snapshot(job)
    value['saved'], value['persistence_error'] = True, None
    try:
        store.update_snapshot(value)
    except Exception:
        logger.exception('Unable to save marker plan %s', job['id'])
        job['saved'] = False
        job['persistence_error'] = 'This result could not be saved. Check the database connection.'
        return False
    job['saved'], job['persistence_error'] = True, None
    return True


def plan_audit(user, action):
    """
    Purpose: Build the function that writes a plan's activity-log entry, so the store can do it in the same
    database transaction as the action itself.
    Input: user - who is acting; action - 'marker_plan.create', 'marker_plan.delete' or 'marker_plan.download'.
    Output: a function (session, job) that adds the entry. It records the inputs the plan was built from (Tech Pack,
    purchase orders, quantity, table length, minimum plies, time limit and each material's consumption and ply
    limit) and the plan's status and result totals.
    """
    def write(session, job):
        request = job.get('request') or {}
        name = request.get('tech_pack_filename') or ', '.join(job.get('order_labels') or []) or 'Marker plan'
        details = {'status': job.get('status'), 'summary': job.get('summary'),
                   'tech_pack_filename': request.get('tech_pack_filename'), 'style_number': request.get('style_number'),
                   'tech_pack_number': request.get('tech_pack_number'), 'orders': job.get('order_labels') or [],
                   'total_quantity': job.get('total_quantity'), 'table_length_m': request.get('table_length_m'),
                   'min_plies': request.get('min_plies'), 'time_limit_seconds': request.get('time_limit_seconds'),
                   'materials': [{key: material.get(key) for key in ('material_code', 'consumption', 'unit', 'max_plies')}
                                 for material in request.get('materials', [])]}
        record(session, user, action, 'marker_plan', job['id'], name[:255], details)
    return write


def recover_interrupted_plans():
    """A restarted process cannot continue its old solver threads; retain finished materials."""
    for job in store.list_snapshots(unfinished=True):
        for entry in job['materials']:
            if entry['result'] is None:
                entry['state'] = 'done'
                entry['result'] = failure('ERROR', 'Planning was interrupted by a server restart. Generate a new plan.')
        job['status'], job['finished_at'] = 'complete', now()
        job['saved'], job['persistence_error'] = True, None
        store.update_snapshot(snapshot(job))


def run_job(job_id):
    """
    Purpose: Solve each queued material of a job in turn, publishing live progress and final results.
    Any unexpected failure is recorded on the remaining materials so a job never stays 'running'.
    Input: job_id - the job to run.
    Output: nothing (the stored job is updated).
    """
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job['status'], job['started_at'] = 'running', now()
        persist(job)
        inputs = _inputs.get(job_id, {})
    try:
        for entry in job['materials']:
            with _lock:
                if entry['state'] != 'queued':
                    continue
                entry['state'] = 'running'

            def on_progress(event, entry=entry):
                with _lock:
                    entry['live'] = progress_dict(event)

            result = run_material(inputs[entry['number']], on_progress, entry['marker_prefix'])
            source = PlanMaterial.model_validate(job['request']['materials'][entry['number'] - 1])
            details = nesting_details(source, job['sizes'])
            for marker in result['markers']:
                marker.update(details.get(tuple(marker['counts']), {}))
            with _lock:
                entry['result'], entry['state'] = result, 'done'
                persist(job)
    except Exception as exc:  # noqa: BLE001 - report instead of leaving the job running forever
        with _lock:
            for entry in job['materials']:
                if entry['result'] is None:
                    entry['result'], entry['state'] = failure('ERROR', f'Planning stopped: {exc}'), 'done'
    finally:
        with _lock:
            job['status'], job['finished_at'] = 'complete', now()
            persist(job)
            _inputs.pop(job_id, None)


def forget_old_jobs():
    """
    Purpose: Keep memory bounded by dropping the oldest finished jobs beyond MAX_JOBS.
    Input: none (the caller holds the lock).
    Output: nothing.
    """
    finished = [key for key, job in _jobs.items() if job['status'] == 'complete' and job.get('saved')]
    for key in finished[:max(0, len(_jobs) - MAX_JOBS)]:
        del _jobs[key]


@router.post('', status_code=202)
def create_plan(payload: PlanRequest, user=Depends(require_user)):
    """
    Purpose: Check the chosen POs and materials, then queue a cutting plan for each material. Who generated it
    (including a re-run, which is a new plan) is recorded in the activity log.
    Input: payload - a PlanRequest (PO size rows, materials with consumption and maximum plies, table length,
    minimum plies and time budget per material).
    Output: the new job (HTTP 202) with the combined size demand and each material's capacity. A material
    with impossible settings (capacity below 1, minimum above its maximum plies) is answered at once with
    status 'INVALID_INPUT'; the others are still planned. Raises 400 when PO rows cannot be read as whole
    numbers; schema problems give 422.
    """
    try:
        demand = order_demand(payload.orders)
    except PlanInputError as exc:
        raise HTTPException(400, str(exc)) from exc
    job_id = str(uuid.uuid4())
    try:
        incumbents = store.best_incumbents(payload, demand)
    except Exception as exc:
        raise HTTPException(503, 'Unable to check previous saved results. Please try again.') from exc
    materials, inputs = [], {}
    for number, material in enumerate(payload.materials, 1):
        entry = {'number': number, 'marker_prefix': f'B{number:02d}-',
                 'material_code': material.material_code, 'description': material.description,
                 'placement': material.placement, 'page_number': material.page_number,
                 'consumption': f'{material.consumption.normalize():f}', 'unit': material.unit,
                 'consumption_m': f'{consumption_in_metres(material).normalize():f}',
                 'max_plies': material.max_plies,
                 'capacity': material_capacity(payload.table_length_m, material),
                 'capacity_basis': 'verified_nesting' if material.nesting_markers else 'estimated_consumption',
                 'state': 'queued', 'live': None, 'result': None}
        try:
            inputs[number] = planner_input(demand, material, payload)
            if number in incumbents:
                inputs[number] = replace(inputs[number], incumbent_lays=incumbents[number])
        except ValueError as exc:
            entry['state'], entry['result'] = 'done', failure('INVALID_INPUT', str(exc))
        materials.append(entry)
    request_json = payload.model_dump(mode='json')
    job = {'id': job_id, 'status': 'queued', 'created_at': now(), 'started_at': None, 'finished_at': None,
           'saved': True, 'persistence_error': None, 'request': request_json,
           'sizes': list(demand.sizes), 'quantities': list(demand.quantities),
           'total_quantity': sum(demand.quantities), 'warnings': demand.warnings,
           'order_labels': [order.label for order in payload.orders],
           'settings': {'table_length_m': f'{payload.table_length_m.normalize():f}', 'min_plies': payload.min_plies,
                        'time_limit_seconds': payload.time_limit_seconds},
           'materials': materials}
    try:
        store.create_record(snapshot(job), request_json, plan_audit(user, 'marker_plan.create'))
    except Exception as exc:
        raise HTTPException(503, 'Unable to save the cutting plan. Check the database connection and try again.') from exc
    with _lock:
        _jobs[job_id], _inputs[job_id] = job, inputs
        forget_old_jobs()
        result = snapshot(job)
    submit(run_job, job_id)
    return result


@router.get('')
def list_plans(limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    """Newest saved generations, including failed/interrupted runs, with bounded pagination."""
    try:
        jobs = store.list_snapshots(limit, offset)
    except Exception as exc:
        raise HTTPException(503, 'Unable to load saved marker plans.') from exc
    return [{key: job.get(key) for key in ('id', 'status', 'created_at', 'finished_at', 'order_labels',
                                          'total_quantity', 'summary', 'saved')}
            | {'tech_pack_filename': job.get('request', {}).get('tech_pack_filename'),
               'material_count': len(job['materials'])} for job in jobs]


@router.get('/{job_id}')
def get_plan(job_id: uuid.UUID):
    """
    Purpose: Report a cutting-plan job: its status, live solver progress per material and finished results.
    Input: job_id - the job's id.
    Output: the job (see create_plan) with 'summary' once every material is done. Raises 404 for an unknown
    job. Saved results are loaded from PostgreSQL after a restart or cache eviction.
    """
    with _lock:
        job = _jobs.get(str(job_id))
        if job is not None:
            return snapshot(job)
    try:
        saved = store.load_snapshot(job_id)
    except Exception as exc:
        raise HTTPException(503, 'Unable to load the saved cutting plan.') from exc
    if saved is None:
        raise HTTPException(404, 'Cutting plan not found.')
    return saved


@router.get('/{job_id}/excel')
def download_excel(job_id: uuid.UUID, user=Depends(require_user)):
    """
    Download the durable snapshot, never a recomputed plan or an unfinished cached result. Each download is
    recorded in the activity log first; if it cannot be recorded the file is not sent.
    """
    current = get_plan(job_id)
    if not current.get('saved') or current['status'] != 'complete':
        raise HTTPException(409, 'Wait for a complete, saved plan before downloading Excel.')
    try:
        job = store.load_snapshot(job_id)
    except Exception as exc:
        raise HTTPException(503, 'Unable to load the saved cutting plan.') from exc
    if job is None:
        raise HTTPException(404, 'Cutting plan not found.')
    from .marker_plan_excel import build_marker_plan_excel
    try:
        payload = build_marker_plan_excel(job)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    try:
        store.log_event(plan_audit(user, 'marker_plan.download'), job)
    except Exception as exc:
        logger.exception('Unable to record the download of marker plan %s', job_id)
        raise HTTPException(503, 'Unable to record this download in the activity log. Please try again.') from exc
    return Response(payload, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename="marker-plan-{job_id}.xlsx"'})


@router.delete('/{job_id}')
def delete_plan(job_id: uuid.UUID, user=Depends(require_user)):
    """Delete only a finished saved generation, preserving source documents and other plans. What was deleted and by whom is recorded."""
    key = str(job_id)
    with _lock:
        cached = _jobs.get(key)
        if cached and cached['status'] in ('queued', 'running'):
            raise HTTPException(409, 'Wait for this plan to finish before deleting it.')
        try:
            deleted = store.delete_record(job_id, plan_audit(user, 'marker_plan.delete'))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(503, 'Unable to delete the saved plan. Please try again.') from exc
        if not deleted:
            raise HTTPException(404, 'Cutting plan not found.')
        _jobs.pop(key, None)
        _inputs.pop(key, None)
    return {'ok': True}


@router.get('/{job_id}/rerun-settings')
def rerun_settings(job_id: uuid.UUID):
    """Review the original order/material snapshots using current material ply limits."""
    original = get_plan(job_id)
    if original['status'] in ('queued', 'running'):
        raise HTTPException(409, 'Wait for this plan to finish before running it again.')
    payload = deepcopy(original.get('request'))
    if not payload:
        raise HTTPException(409, 'This saved plan has no source settings. Generate a new plan from the Tech Pack.')
    try:
        info = store.current_ply_info(payload['materials'])
    except Exception as exc:
        raise HTTPException(503, 'Unable to load current ply limits. Please try again.') from exc
    notes = []
    for material in payload['materials']:
        code = material.get('material_code')
        maximum = info.get(code, {}).get('max_ply')
        if isinstance(maximum, (int, float)) and maximum >= 1 and maximum == int(maximum):
            material['max_plies'] = int(maximum)
        else:
            notes.append(f'{code or "Material"}: no current ply limit found; keeping the saved limit of {material["max_plies"]}.')
    return {'request': payload, 'notes': notes}
