# Coding drafts — first coding-agent increment

Configure your API key, then open Developer Studio. Describe a single Python program and click Generate Python draft. The approval shows the selected chat provider and model; the request may incur API charges. Only your task description and a fixed coding instruction are transmitted. Existing source files and chat history are not attached. Backup routing is not enabled for this workflow.

A complete response appears in a separate preview. Python syntax is checked without execution. Syntax passing is not a correctness or security guarantee. Failed syntax remains visible for review. Cancelled or failed requests do not populate the preview. Generation has persistent task status and provider usage records.

Review and copy draft to editor requires approval and marks the editor modified. Review and save is a separate existing approval and retains revisions of overwritten files. Generating a new draft replaces the previous preview only after approval; previews are not persisted across restart.

Not yet implemented: isolated code execution, automatic debugging, test execution, multi-file project generation, offline model inference or internet research. This increment provides real provider-backed drafting, not a completed autonomous coding agent.

Validation: 130 local tests passed, including refusal, cancellation, no implicit execution or file writes, and explicit editor replacement. Compilation passed. Live API and native Windows checks remain pending.

தமிழ்: Developer Studio → செய்ய வேண்டிய Python வேலையை எழுதுங்கள் → Generate Python draft → அனுமதி கொடுங்கள் → preview பாருங்கள் → Review and copy draft to editor → Review and save. Code தானாக run ஆகாது.

## Repair an existing Python draft

Paste the failing source into the editor and paste the error into the error box. Review and request code repair asks permission to share the current editor contents and error with the selected chat provider. Remove credentials and private data before approving. No files, conversation history or logs are discovered or attached automatically. The captured payload is bounded and its digest is shown in the approval.

The complete corrected source appears in the same draft preview with a syntax check. The editor remains unchanged until Review and copy draft to editor is approved; saving still requires a separate approval. Emergency stop invalidates pending approval and discards late responses. A failed repair does not populate the preview. Repairs use one provider and do not use backup routing.

This is AI-assisted repair from an error supplied by the user, not automatic execution or verified debugging. Code execution and behavioral tests remain pending. Current validation: 139 local tests pass, including repair payload limits, rejection, stop during approval, late cancellation, and failed responses. Live API testing remains pending.

தமிழ்: Editor-ல் code வையுங்கள் → error box-ல் பிழையை paste செய்யுங்கள் → Review and request code repair → அனுமதி → திருத்தப்பட்ட preview → review செய்து editor-க்கு மாற்றுங்கள். Code தானாக run அல்லது save ஆகாது.
