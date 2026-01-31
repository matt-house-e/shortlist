# Architecture Decisions

## ADR-001: Fat State Pattern

Use single state object for all workflow data.

**Rationale**: Simplifies debugging and state inspection.

## ADR-002: Node Functions over Classes

Use pure functions as LangGraph nodes.

**Rationale**: More testable, explicit state transitions.
