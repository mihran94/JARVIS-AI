from security.policy import Denied, Stopped


class Gateway:
    def __init__(self, policy, store):
        self.policy, self.store = policy, store

    def run(self, action, confirm, operation, *, task_id=None, completion_status='completed'):
        ident = task_id if task_id is not None else self.store.task(action.kind, action.target)
        try:
            token = self.policy.approve(action, confirm)
            self.store.finish(ident, 'running')
            result = self.policy.execute(action, token, operation)
            self.store.finish(ident, completion_status, result)
            return result
        except Denied:
            self.store.finish(ident, 'denied')
            raise
        except Stopped:
            self.store.finish(ident, 'cancelled')
            raise
        except Exception:
            self.store.finish(ident, 'failed')
            raise
