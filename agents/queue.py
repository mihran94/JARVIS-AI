"""Durable manual queue. No approval survives restart; no automatic retries."""
import uuid
from automation.windows import APPS, launch_app
from security.policy import Action, Denied, Stopped


class TaskQueue:
    def __init__(self, store, gateway):
        self.store, self.gateway = store, gateway

    def add(self, app):
        self.gateway.policy.ticket()
        if app not in APPS:
            raise ValueError('Application is not allowlisted.')
        ident = uuid.uuid4().hex
        with self.store.connect() as db:
            db.execute("INSERT INTO jobs(id,app,status) VALUES (?,?,'queued')", (ident, app))
        return ident

    def rows(self):
        with self.store.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM jobs ORDER BY rowid DESC LIMIT 200')]

    def cancel(self, ident):
        with self.store.connect() as db:
            result = db.execute("UPDATE jobs SET status='cancelled',detail='Cancelled by owner' "
                                "WHERE id=? AND status IN ('queued','reviewing')", (ident,))
            return result.rowcount == 1

    def cancel_pending(self):
        with self.store.connect() as db:
            db.execute("UPDATE jobs SET status='cancelled',detail='Emergency stop' "
                       "WHERE status IN ('queued','reviewing')")

    def _finish(self, ident, status, detail):
        with self.store.connect() as db:
            db.execute("UPDATE jobs SET status=?,detail=? WHERE id=? "
                       "AND status IN ('reviewing','running')", (status, detail, ident))

    def run(self, ident, confirm, launcher=launch_app):
        self.gateway.policy.ticket()
        with self.store.connect() as db:
            claimed = db.execute("UPDATE jobs SET status='reviewing' WHERE id=? AND status='queued'", (ident,))
            if claimed.rowcount != 1:
                raise Denied('Job is not queued. Completed, cancelled or interrupted jobs cannot be replayed.')
            row = db.execute('SELECT app FROM jobs WHERE id=?', (ident,)).fetchone()
            app = row['app']
        try:
            if app not in APPS:
                raise Denied('Stored application is not allowlisted.')
            def launch_once():
                with self.store.connect() as db:
                    result = db.execute("UPDATE jobs SET status='running' WHERE id=? AND status='reviewing'", (ident,))
                    if result.rowcount != 1:
                        raise Stopped('Job was cancelled while awaiting approval.')
                return launcher(app)
            result = self.gateway.run(Action('queued_launch', f'{app} (job {ident})'), confirm, launch_once)
            self._finish(ident, 'completed', result)
            return result
        except Denied:
            self._finish(ident, 'denied', 'Approval declined or invalid action')
            raise
        except Stopped:
            self._finish(ident, 'cancelled', 'Cancelled before execution')
            raise
        except Exception:
            self._finish(ident, 'failed', 'Launch failed; see the desktop error')
            raise
