# Agent guidance

Build a small, working hackathon MVP that demonstrates an end-to-end AI engineering capability relevant to an early-career AI Engineer role. Focus on one real user problem and a reliable, measurable workflow. Follow repository conventions, keep code straightforward, and avoid unnecessary dependencies.

The code should be explainable and traceable.

## Product and engineering
- Inspect relevant files and existing setup before changing the implementation.
- Deliver a runnable vertical slice: validated input or data, a clearly scoped AI capability, a usable result, and an interface or API appropriate to the project.
- Use modular, maintainable code and clean service boundaries. Keep model/provider configuration outside source code; handle missing credentials and service errors visibly.
- Include SQL, ETL, cloud, or streaming components only when they serve the chosen use case. Validate schemas and data quality, and handle PII deliberately.
- Validate inputs, handle expected errors, and never silently conceal failures.

## AI quality and responsible use
- State the task, model or service choice, and important assumptions. Use prompts and structured outputs that can be inspected and validated.
- Add proportionate guardrails, grounding or evidence where applicable, and a safe response for uncertain or invalid outputs. Keep human review for consequential decisions.
- Evaluate the core workflow with representative examples and relevant measures such as accuracy, relevance, groundedness, latency, or robustness. Record failure cases and limitations; avoid unsupported quality claims.
- Treat user input and external data as untrusted. Protect secrets, minimize sensitive data collection and retention, and do not log secrets or unnecessary personal data.

## Testing and delivery
- Add focused tests for changed behavior and run applicable checks. Report what ran and any failures; never claim an unrun check passed.
- Document the problem, setup, architecture, sample usage, evaluation approach and results, assumptions, and known limitations in the project's existing documentation.
- Keep changes focused and explain important decisions in user-facing language.
