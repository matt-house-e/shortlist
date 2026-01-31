# LangGraph Workflow

## State Schema

All workflow data lives in `AgentState` (app/models/state.py).

## Node Pattern

Pure functions returning `Command` objects:

```python
async def agent_node(state: AgentState) -> Command:
    return Command(update={...}, goto="next_node")
```

## Adding Nodes

1. Create node function in `app/agents/`
2. Register in `workflow.py`
3. Add edges to connect nodes
