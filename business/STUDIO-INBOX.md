# AI Creative Studio client inbox

Open **Business → Client inbox & replies** in JARVIS. Paste a client message
and optional reply instructions, then select **Draft with Gemini**. This uses
the saved Gemini key from **API Providers**. Review and edit the draft before
copying it. Use **Open Fiverr Inbox** to open your signed-in Fiverr inbox and
paste the reply in the conversation you select.

## Enable website inbox and reply sending

The current AI Studio export has simulated account login and in-memory
messages. A production website must enforce account authentication and
per-order authorization on its existing routes, then expose the authenticated
contract below. Configure these environment variables in the process that
launches JARVIS:

- `MY_WEBSITE_ADMIN_URL` is the deployed website origin, such as
  `https://studio.example.com`. HTTP origins are accepted for loopback
  development.
- `JARVIS_STUDIO_INBOX_TOKEN` is a separate credential issued by the website
  backend. Store the server copy as a server-side secret.

With the inbox open, select **Refresh website inbox**. **Check every 15 seconds**
enables polling for this dialog. The first successful read sets the baseline.
Enable **Voice alerts** to hear the count of newly observed customer messages.
Select the exact order and review the text in the confirmation dialog to send
a website reply. If the server does not confirm the reply, check the website
chat before sending it again.

### Website API contract

Both endpoints require `Authorization: Bearer <integration-token>`. The
server must authorize access to each order, use the server-side admin identity,
store messages durably, and enforce the `Idempotency-Key` header on writes.

- `GET /api/admin/all-messages?limit=100` returns a newest-first JSON array
  of at most 100 records. Customer records contain the strings `id`,
  `orderId`, `senderRole: "customer"`, `senderName`, and `message`.
- `POST /api/admin/reply` accepts JSON strings `orderId` and `message`.
  On a committed write, return the created message with a nonempty `id`,
  the exact `orderId` and `message`, and `senderRole: "admin"`.

The JARVIS inbox does not store client messages in general chat history.
