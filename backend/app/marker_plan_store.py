"""Database boundary for saved marker plans. Returned snapshots are detached copies."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select
from .database import SessionLocal
from .models import MarkerPlanRecord


def create_record(job, payload, audit=None):
    """Save a new plan. `audit(session, job)`, when given, writes the activity-log entry in the same transaction."""
    with SessionLocal() as session:
        session.add(MarkerPlanRecord(id=UUID(job['id']), status=job['status'],
                                    created_at=datetime.fromisoformat(job['created_at']),
                                    request_json=deepcopy(payload), snapshot_json=deepcopy(job)))
        if audit:
            audit(session, job)
        session.commit()


def update_snapshot(job):
    with SessionLocal() as session:
        row = session.get(MarkerPlanRecord, UUID(job['id']))
        if row is None:
            raise LookupError('Saved marker plan not found')
        row.status, row.snapshot_json = job['status'], deepcopy(job)
        session.commit()


def load_snapshot(job_id):
    with SessionLocal() as session:
        row = session.get(MarkerPlanRecord, UUID(str(job_id)))
        return deepcopy(row.snapshot_json) if row else None


def delete_record(job_id, audit=None):
    """Delete a finished plan. `audit(session, snapshot)`, when given, records what was deleted in the same transaction."""
    with SessionLocal() as session:
        row = session.get(MarkerPlanRecord, UUID(str(job_id)))
        if row is None:
            return False
        if row.status in ('queued', 'running'):
            raise ValueError('Wait for this plan to finish before deleting it.')
        if audit:
            audit(session, deepcopy(row.snapshot_json))
        session.delete(row)
        session.commit()
        return True


def log_event(audit, job):
    """Write an activity-log entry for something that changes no plan (a download): `audit(session, job)` then commit."""
    with SessionLocal() as session:
        audit(session, job)
        session.commit()


def current_ply_info(materials):
    from .ply_lookup import ply_info_for
    with SessionLocal() as session:
        return ply_info_for(session, {'materials': materials}, strict=True)


def best_incumbents(payload, demand):
    """Find the best validated result for identical cutting inputs, irrespective of search time."""
    from .marker_plan import PlanMaterial, planner_input
    from .marker_planner import Lay, validate_plan
    wanted = payload.materials
    best = {}
    with SessionLocal() as session:
        statement = select(MarkerPlanRecord).where(MarkerPlanRecord.status == 'complete').execution_options(yield_per=100)
        for record in session.scalars(statement):
            job = record.snapshot_json
            if job.get('sizes') != list(demand.sizes) or job.get('quantities') != list(demand.quantities):
                continue
            request = job.get('request') or {}
            if Decimal(str(request.get('table_length_m', 0))) != payload.table_length_m or request.get('min_plies') != payload.min_plies:
                continue
            for source, entry in zip(request.get('materials', []), job.get('materials', [])):
                result = entry.get('result') or {}
                if not result.get('validated') or result.get('status') not in ('FEASIBLE', 'OPTIMAL'):
                    continue
                try:
                    normalized = PlanMaterial.model_validate(source)
                    lays = tuple(Lay(tuple(lay['counts']), lay['plies']) for lay in result['lays'])
                    for index, material in enumerate(wanted):
                        if normalized != material:
                            continue
                        validate_plan(planner_input(demand, payload.materials[index], payload), list(lays))
                        quality = (len({lay.marker for lay in lays}), len(lays))
                        if index not in best or quality < best[index][0]:
                            best[index] = (quality, lays)
                except (ValueError, KeyError, TypeError):
                    continue
    return {index + 1: lays for index, (_, lays) in best.items()}


def list_snapshots(limit=100, offset=0, unfinished=False):
    statement = select(MarkerPlanRecord).order_by(MarkerPlanRecord.created_at.desc(), MarkerPlanRecord.id.desc())
    if unfinished:
        statement = statement.where(MarkerPlanRecord.status.in_(['queued', 'running']))
    else:
        statement = statement.limit(limit).offset(offset)
    with SessionLocal() as session:
        return [deepcopy(row.snapshot_json) for row in session.scalars(statement).all()]
