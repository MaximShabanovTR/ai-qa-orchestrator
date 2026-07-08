from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from models.planning import RemediationAction
from workflow.state import QAState
from workflow.nodes import analyze, clarify, generate, collect_answers, plan, review

# MemorySaver keeps state in memory — enough for development.
# Swap for SqliteSaver or RedisSaver later without changing any node code.
_checkpointer = MemorySaver()


def route_after_clarification(state: QAState) -> str:
    if state["clarification_complete"]:
        return "generate"
    else:
        return "collect_answers"
    
def route_after_plan(state: QAState) -> str:
    if state["planner_decision"].action == RemediationAction.REGENERATE_ALL:
        return "generate"
    else:
        return END

def build_graph():
    graph = StateGraph(QAState)

    graph.add_node("analyze", analyze)
    graph.add_node("collect_answers", collect_answers)
    graph.add_node("clarify", clarify)
    graph.add_node("generate", generate)
    graph.add_node("review", review)
    graph.add_node("plan", plan)

    graph.add_edge(START, "analyze")
    graph.add_edge("analyze", "clarify")
    graph.add_conditional_edges("clarify", route_after_clarification)
    graph.add_edge("collect_answers", "clarify")
    graph.add_edge("generate", "review")
    graph.add_edge("review", "plan")
    graph.add_conditional_edges("plan", route_after_plan)

    return graph.compile(checkpointer=_checkpointer)

qa_graph = build_graph()
