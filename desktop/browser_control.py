"""The main composer's browser actions. Page contents remain transient and local."""
import asyncio
from dataclasses import replace
from pathlib import Path
from queue import Empty, Queue
import threading

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QInputDialog

from automation.browser import BrowserSession, BrowserTaskError, HELP, origin, parse_browser
from security.policy import Action, Denied, Stopped


class BrowserThread(QThread):
    result = Signal(str, str, object)

    def __init__(self, profile, policy, parent):
        super().__init__(parent)
        self.session = BrowserSession(profile)
        self.policy = policy
        self.inbox = Queue(maxsize=1)
        self.halt = threading.Event()

    def run(self):
        asyncio.run(self.serve())

    async def serve(self):
        try:
            while not self.halt.is_set():
                try:
                    action, ticket, document = self.inbox.get_nowait()
                except Empty:
                    await asyncio.sleep(0.05)
                    continue

                def check():
                    self.policy.check(ticket)
                    if self.halt.is_set():
                        raise Stopped('Browser action cancelled.')

                task = asyncio.create_task(self.session.perform(action, document, check))
                try:
                    while not task.done():
                        await asyncio.wait([task], timeout=0.05)
                        check()
                    status, message, new_document = task.result()
                    check()
                    self.result.emit(status, message, new_document)
                except Stopped:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    self.result.emit('cancelled', 'Browser stopped. Check any previously dispatched action on the site.', None)
                except BrowserTaskError as error:
                    self.result.emit('unverified', str(error), None)
                except Exception:
                    # Playwright error strings may include URL tokens and field values.
                    self.result.emit('unverified', 'The browser could not verify the result. Check the browser before repeating the action.', None)
        finally:
            try:
                await self.session.close()
            except Exception:
                pass


class BrowserControl(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.worker = self.task = self.document = None
        self.ticket = None

    def stop(self):
        self.document = None
        if self.worker:
            self.worker.halt.set()

    def command(self, request):
        w = self.window
        try:
            action = parse_browser(request)
            if action.verb == 'close':
                self.stop()
                w.browser_output.setPlainText('Closing browser session.')
                return
            if self.task or (self.worker and self.worker.halt.is_set()):
                raise BrowserTaskError('Wait for the current browser action to finish.')
            ticket = w.policy.ticket()
            if action.verb == 'open':
                destination = origin(action.target)
                preview = 'Open this address in the dedicated browser profile?\n' + action.target
            else:
                if not self.worker or (not self.document and action.verb != 'inspect'):
                    raise BrowserTaskError('Open the site and inspect the page first.')
                destination = self.document[0] if self.document else 'the current authorized site'
                preview = f'{action.verb.title()} on {destination}\n{action.target}'
            if action.verb == 'fill':
                value, ok = QInputDialog.getMultiLineText(w, 'Browser draft', 'Text for ' + action.target)
                if not ok:
                    return
                if len(value) > 16000:
                    raise BrowserTaskError('Use at most 16,000 characters in one draft.')
                action = replace(action, value=value)
                preview += '\n\n' + value
            if action.verb == 'upload':
                chosen, _ = QFileDialog.getOpenFileName(w, 'Choose the asset to send')
                if not chosen:
                    return
                path = Path(chosen)
                from desktop.attachments import is_sensitive
                if not path.is_file() or path.is_symlink() or is_sensitive(path) or path.stat().st_size > 100_000_000:
                    raise BrowserTaskError('Choose a regular non-sensitive asset under 100 MB.')
                action = replace(action, value=str(path))
                preview += '\nSend file to this site: ' + str(path)
            document = self.document
            digest = action.digest(document)
            audit = Action('browser_' + action.verb, destination, digest)
            token = w.policy.approve(audit, lambda _: w.confirm(Action(audit.kind, preview, digest)))
            def enqueue():
                w.policy.check(ticket)
                if self.worker is None:
                    self.worker = BrowserThread(w.root / 'browser-profile', w.policy, self)
                    self.worker.result.connect(self.finished_action)
                    self.worker.finished.connect(self.closed)
                    self.worker.start()
                self.ticket = ticket
                self.task = w.store.task(audit.kind, destination)
                w.store.finish(self.task, 'running')
                self.worker.inbox.put_nowait((action, ticket, document))
                w.browser_output.setPlainText(f'{action.verb.title()} in progress on {destination}…')
                w.refresh_prime_state()
            w.policy.execute(audit, token, enqueue)
        except (BrowserTaskError, Denied, Stopped, OSError) as error:
            w.browser_output.setPlainText(str(error))

    @Slot(str, str, object)
    def finished_action(self, status, message, document):
        if self.task is None:
            return
        try:
            self.window.policy.check(self.ticket)
            if self.worker.halt.is_set():
                raise Stopped()
        except Stopped:
            status, message, document = 'cancelled', 'Browser action stopped. Review the site before retrying.', None
        self.document = document
        self.window.browser_output.setPlainText(message)
        # Do not persist page contents, URLs with queries, user-entered values or filenames.
        self.window.store.finish(self.task, status, 'Browser action ' + status + '.')
        self.task = None
        self.window.refresh_prime_state()

    @Slot()
    def closed(self):
        if self.task:
            self.finished_action('cancelled', 'Browser session closed.', None)
        self.worker.deleteLater()
        self.worker = self.document = None
        if self.window.close_when_done:
            self.window.close()
