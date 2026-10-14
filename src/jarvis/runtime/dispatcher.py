"""Local authority checks and durable intent before any registered capability."""
import time

from jarvis.runtime import workers
from jarvis.runtime.protocol import Rejected, result, validate_call, validate_result


class Dispatcher:
    def __init__(self, config, credentials, journal, runner=workers.execute):
        self.config, self.credentials, self.journal, self.runner = config, credentials, journal, runner

    def dispatch(self, call, cancelled=lambda: False):
        try:
            validate_call(call, self.credentials["signing_key"], self.config["allowed_tools"], check_deadline=False)
            previous, fresh = self.journal.begin(call)
            if not fresh:
                return previous or result(call, "unknown", error="unfinished_call_requires_reconciliation")
            if cancelled():
                output = result(call, "cancelled", error="cancelled_before_dispatch")
            elif time.time() >= call["deadline"] or call["deadline"] > time.time()+31:
                output = result(call, "denied", error="expired_or_excessive_deadline")
            else:
                output = self.runner(call, self.config, self.credentials, cancelled)
            validate_result(output, call)
            self.journal.finish(call, output)
            return output
        except Rejected as exc:
            return result(call if isinstance(call, dict) else {}, "denied", error=str(exc))
