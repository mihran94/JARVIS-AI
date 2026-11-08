from security.policy import Denied, Stopped


class Gateway:
    def __init__(self, policy, store):
        self.policy, self.store = policy, store

    def run(self, action, confirm, operation):
        ident = self.store.task(action.kind, action.target)
        try:
            token = self.policy.approve(action, confirm)
            self.store.finish(ident, 'running')
            result = self.policy.execute(action, token, operation)
            self.store.finish(ident, 'completed', result)
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
