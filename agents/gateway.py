from security.policy import Denied, Stopped


class Gateway:
    def __init__(self, policy, store):
        self.policy, self.store = policy, store

    def run(self, action, confirm, operation, *, task_id=None, completion_status='completed',
            auto_approve=True, history_detail=None):
        # Keep the exact action for approval and execution. A caller that
        # supplies safe history metadata must not persist the raw output.
        detail = action.target if history_detail is None else history_detail
        ident = task_id if task_id is not None else self.store.task(action.kind, detail)
        try:
            token = self.policy.approve(action, confirm, auto_approve=auto_approve)
            self.store.finish(ident, 'running')
            result = self.policy.execute(action, token, operation)
            self.store.finish(ident, completion_status, result if history_detail is None else None)
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
