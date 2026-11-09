# Desktop backup provider

Chat now offers an unchecked, per-message backup checkbox and named provider selector. Select a different configured provider, then check the box before Send. This permits sharing the entire submitted conversation with that provider and may incur charges at both providers. Consent resets after Send; provider health checks stay primary-only.

One backup attempt is allowed for timeouts, connection errors, or HTTP 502/503/504 before any text is emitted. Authentication, quota, filtering, malformed responses, partial text, and emergency stop do not trigger backup. The backup never recursively retries.

Usage records identify the last attempted provider and model. Token counts are only those reported by that attempt; earlier failed attempts may still be billable and are not included in these token totals. Duration covers the whole request. This is not a billing reconciliation report. Worker-held primary and backup credentials are released on completion.

Validation: 97 local tests passed using Qt offscreen and fake HTTP transports. No real provider credentials were used. Native Windows and live API checks remain pending.
