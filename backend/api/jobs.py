from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Event, Lock, Thread
from uuid import uuid4

from .graph import SearchBudgetExceeded, SearchCancelled, find_path

JOBS = {}
JOB_LOCK = Lock()
JOB_TTL = timedelta(minutes=30)


def start_connection_job(actor_a_id, actor_b_id, max_degrees=6):
    _cleanup_jobs()
    job_id = str(uuid4())
    stop_event = Event()
    now = _utc_now()

    with JOB_LOCK:
        JOBS[job_id] = {
            'id': job_id,
            'status': 'pending',
            'actor_a_id': actor_a_id,
            'actor_b_id': actor_b_id,
            'max_degrees': max_degrees,
            'created_at': now,
            'updated_at': now,
            'path': None,
            'degrees': None,
            'error': None,
            'progress': {
                'stage': 'queued',
                'depth': 0,
                'explored_actors': 0,
                'frontier_size': 0,
                'frontier_sample': [],
                'message': 'Busca enfileirada.',
                'history': [],
            },
            'stop_event': stop_event,
        }

    worker = Thread(
        target=_run_connection_job,
        args=(job_id,),
        daemon=True,
    )
    worker.start()
    return get_job(job_id)


def get_job(job_id):
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        return _serialize_job(job)


def cancel_job(job_id):
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        job['stop_event'].set()
        job['updated_at'] = _utc_now()
        if job['status'] in {'pending', 'running'}:
            job['status'] = 'cancel_requested'
            job['progress']['message'] = 'Cancelamento solicitado.'
        return _serialize_job(job)


def _run_connection_job(job_id):
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job['status'] = 'running'
        job['updated_at'] = _utc_now()
        job['progress']['stage'] = 'starting'
        job['progress']['message'] = 'Preparando busca profunda.'
        actor_a_id = job['actor_a_id']
        actor_b_id = job['actor_b_id']
        max_degrees = job['max_degrees']
        stop_event = job['stop_event']

    try:
        path = find_path(
            actor_a_id,
            actor_b_id,
            max_degrees=max_degrees,
            search_profile='deep',
            progress_callback=lambda payload: _update_progress(job_id, payload),
            cancel_check=stop_event.is_set,
        )
        with JOB_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return
            job['updated_at'] = _utc_now()
            if path is None:
                job['status'] = 'not_found'
                job['progress']['stage'] = 'not_found'
                job['progress']['message'] = f'Nenhuma conexao encontrada em ate {max_degrees} graus.'
            else:
                job['status'] = 'completed'
                job['path'] = path
                job['degrees'] = len(path) - 1
                job['progress']['stage'] = 'found'
                job['progress']['message'] = 'Conexao encontrada.'
    except SearchCancelled:
        with JOB_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return
            job['status'] = 'cancelled'
            job['updated_at'] = _utc_now()
            job['progress']['stage'] = 'cancelled'
            job['progress']['message'] = 'Busca cancelada.'
    except SearchBudgetExceeded:
        with JOB_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return
            job['status'] = 'timeout'
            job['updated_at'] = _utc_now()
            job['error'] = 'A busca profunda excedeu o tempo permitido.'
            job['progress']['stage'] = 'timeout'
            job['progress']['message'] = 'Busca profunda excedeu o tempo permitido.'
    except Exception as exc:
        with JOB_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return
            job['status'] = 'error'
            job['updated_at'] = _utc_now()
            job['error'] = str(exc)
            job['progress']['stage'] = 'error'
            job['progress']['message'] = 'Ocorreu um erro durante a busca.'


def _update_progress(job_id, payload):
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return

        progress = job['progress']
        history_entry = payload.pop('history_entry', None)
        progress.update(payload)
        if history_entry:
            history = progress.setdefault('history', [])
            if not history or history[-1].get('depth') != history_entry.get('depth'):
                history.append(history_entry)
        job['updated_at'] = _utc_now()


def _serialize_job(job):
    serialized = {
        'id': job['id'],
        'status': job['status'],
        'actor_a_id': job['actor_a_id'],
        'actor_b_id': job['actor_b_id'],
        'max_degrees': job['max_degrees'],
        'created_at': job['created_at'].isoformat(),
        'updated_at': job['updated_at'].isoformat(),
        'path': deepcopy(job['path']),
        'degrees': job['degrees'],
        'error': job['error'],
        'progress': deepcopy(job['progress']),
    }
    return serialized


def _cleanup_jobs():
    cutoff = _utc_now() - JOB_TTL
    with JOB_LOCK:
        stale_ids = [
            job_id
            for job_id, job in JOBS.items()
            if job['updated_at'] < cutoff
        ]
        for job_id in stale_ids:
            JOBS.pop(job_id, None)


def _utc_now():
    return datetime.now(timezone.utc)
