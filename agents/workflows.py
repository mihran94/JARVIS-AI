"""Bounded, user-authored Windows launch workflows with fresh per-step approval.

No model output is parsed as workflow commands, no step runs in the background,
and an interrupted workflow is terminal (never resumed/replayed automatically).
"""
import uuid

from automation.windows import APPS, launch_app
from security.policy import Action, Denied, Stopped

MAX_STEPS = 10


class WorkflowQueue:
    def __init__(self, store, gateway):
        self.store = store
        self.gateway = gateway

    def add(self, apps):
        self.gateway.policy.ticket()
        if isinstance(apps, (str, bytes)) or not isinstance(apps, (list, tuple)):
            raise ValueError('Provide a sequence of allowlisted applications.')
        if not 1 <= len(apps) <= MAX_STEPS or any(app not in APPS for app in apps):
            raise ValueError('Choose 1 to 10 steps using Notepad or Calculator only.')
        ident = uuid.uuid4().hex
        with self.store.connect() as db:
            db.execute("INSERT INTO workflows(id,status,summary) VALUES (?,'queued',?)",
                       (ident, ' → '.join(apps)))
            db.executemany("INSERT INTO workflow_steps(workflow_id,position,app,status) "
                           "VALUES (?,?,?,'pending')",
                           ((ident, position, app) for position, app in enumerate(apps, 1)))
        return ident

    def rows(self):
        with self.store.connect() as db:
            return [dict(row) for row in db.execute(
                'SELECT * FROM workflows ORDER BY rowid DESC LIMIT 200')]

    def steps(self, ident):
        with self.store.connect() as db:
            return [dict(row) for row in db.execute(
                'SELECT position,app,status,detail FROM workflow_steps '
                'WHERE workflow_id=? ORDER BY position', (ident,))]

    def cancel(self, ident):
        with self.store.connect() as db:
            result = db.execute("UPDATE workflows SET status='cancelled',detail='Cancelled by owner' "
                                "WHERE id=? AND status IN ('queued','reviewing')", (ident,))
            if result.rowcount:
                db.execute("UPDATE workflow_steps SET status='cancelled' WHERE workflow_id=? "
                           "AND status IN ('pending','reviewing')", (ident,))
            return result.rowcount == 1

    def cancel_pending(self):
        with self.store.connect() as db:
            db.execute("UPDATE workflows SET status='cancelled',detail='Emergency stop' "
                       "WHERE status IN ('queued','reviewing')")
            db.execute("UPDATE workflow_steps SET status='cancelled' WHERE status IN "
                       "('pending','reviewing') AND workflow_id IN "
                       "(SELECT id FROM workflows WHERE status='cancelled')")

    def _terminal(self, ident, state, detail):
        with self.store.connect() as db:
            db.execute("UPDATE workflows SET status=?,detail=? WHERE id=? "
                       "AND status IN ('reviewing','running')", (state, detail, ident))
            db.execute("UPDATE workflow_steps SET status=?,detail=? WHERE workflow_id=? "
                       "AND status IN ('reviewing','running')", (state, detail, ident))
            db.execute("UPDATE workflow_steps SET status='cancelled' WHERE workflow_id=? "
                       "AND status='pending'", (ident,))

    def run(self, ident, confirm, launcher=launch_app):
        ticket = self.gateway.policy.ticket()
        with self.store.connect() as db:
            result = db.execute("UPDATE workflows SET status='reviewing' "
                                "WHERE id=? AND status='queued'", (ident,))
            if result.rowcount != 1:
                raise Denied('Workflow is not queued; terminal or interrupted runs cannot be replayed.')
        try:
            steps = self.steps(ident)
            if not 1 <= len(steps) <= MAX_STEPS or any(
                    step['position'] != i or step['app'] not in APPS or
                    step['status'] != 'pending' for i, step in enumerate(steps, 1)):
                raise Denied('Workflow content is invalid or has changed.')

            for i, step in enumerate(steps, 1):
                self.gateway.policy.check(ticket)
                with self.store.connect() as db:
                    updated = db.execute("UPDATE workflow_steps SET status='reviewing' "
                                         "WHERE workflow_id=? AND position=? AND status='pending' "
                                         "AND EXISTS (SELECT 1 FROM workflows WHERE id=? "
                                         "AND status='reviewing')", (ident, i, ident))
                    if updated.rowcount != 1:
                        raise Stopped('Workflow was cancelled before this step.')

                app = step['app']

                def launch_once():
                    with self.store.connect() as db:
                        running = db.execute("UPDATE workflows SET status='running' WHERE id=? "
                                             "AND status='reviewing'", (ident,))
                        if running.rowcount != 1:
                            raise Stopped('Workflow was cancelled during approval.')
                        started = db.execute("UPDATE workflow_steps SET status='running' "
                                             "WHERE workflow_id=? AND position=? "
                                             "AND status='reviewing'", (ident, i))
                        if started.rowcount != 1:
                            raise Stopped('Step changed during approval.')
                    return launcher(app)

                action = Action('workflow_launch', f'{app} · step {i}/{len(steps)} · workflow {ident}')
                result = self.gateway.run(action, confirm, launch_once)
                with self.store.connect() as db:
                    db.execute("UPDATE workflow_steps SET status='completed',detail=? "
                               "WHERE workflow_id=? AND position=? AND status='running'",
                               (str(result)[:500], ident, i))
                    if i == len(steps):
                        db.execute("UPDATE workflows SET status='completed',detail=? "
                                   "WHERE id=? AND status='running'",
                                   (f'Completed {len(steps)} individually approved steps', ident))
                    else:
                        db.execute("UPDATE workflows SET status='reviewing' WHERE id=? "
                                   "AND status='running'", (ident,))
            return f'Completed {len(steps)} individually approved steps.'
        except Denied:
            self._terminal(ident, 'denied', 'A step was declined or the workflow was invalid')
            raise
        except Stopped:
            self._terminal(ident, 'cancelled', 'Emergency stop or cancellation')
            raise
        except Exception:
            self._terminal(ident, 'failed', 'Step failed; workflow was not resumed')
            raise
