# Agent guidance

Build a small, working MVP using clear, straightforward code. Follow the repository's existing conventions and setup. Keep changes focused, explain important assumptions, and avoid unnecessary dependencies.

## Implementation
- Inspect relevant files before making changes.
- Prefer simple, readable solutions that are easy to run and maintain.
- Validate inputs, handle expected errors, and never silently conceal failures.

## Testing and measurement
- Add or update focused tests for changed behavior; keep them relevant and easy to understand.
- Run applicable tests and checks. Report what ran and any failures; never claim an unrun check passed.
- Define useful success measures where practical and avoid unsupported claims about quality or performance.

## Explainability and traceability
- Explain important behavior, assumptions, and limitations in user-facing language.
- For AI-generated results, make clear what is generated versus verified and communicate uncertainty when relevant.
- Keep useful records for debugging and evaluation, but never log secrets or unnecessary personal or sensitive data.

## Security and responsible AI
- Treat user input and external data as untrusted; protect secrets and use least privilege.
- Minimize collection and retention of data, and follow the project's privacy and security practices.
- Consider relevant AI failure cases, including inaccurate or unsafe output. Use appropriate safeguards and human review for consequential decisions.
- Do not describe the MVP as production-ready unless it has been tested, reviewed, and secured for its intended use. Be clear about remaining risks and limitations.
