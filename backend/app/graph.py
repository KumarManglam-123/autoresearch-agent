from langgraph.graph import StateGraph, START, END
from backend.app.state import ResearchState
from backend.app.nodes.planner import planner_node
from backend.app.nodes.researcher import researcher_node
from backend.app.nodes.critic import critic_node
from backend.app.nodes.writer import writer_node

def route_after_critic(state: ResearchState) -> str:
    """
    Conditional routing edge after critic review.
    Routes to 'writer' if research is sufficient or if max retries (2) reached.
    Otherwise routes back to 'researcher'.
    """
    is_sufficient = state.get("is_sufficient", False)
    retry_count = state.get("retry_count", 0)

    if is_sufficient or retry_count >= 2:
        return "writer"
    return "researcher"

def create_research_graph():
    """
    Build and compile the AutoResearch LangGraph state machine.
    """
    builder = StateGraph(ResearchState)

    # Add nodes
    builder.add_node("planner", planner_node)
    builder.add_node("researcher", researcher_node)
    builder.add_node("critic", critic_node)
    builder.add_node("writer", writer_node)

    # Add edges
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "researcher")
    builder.add_edge("researcher", "critic")

    # Conditional edge after critic
    builder.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "writer": "writer",
            "researcher": "researcher"
        }
    )

    builder.add_edge("writer", END)

    return builder.compile()

research_graph = create_research_graph()
