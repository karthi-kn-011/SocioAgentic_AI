import logging
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from .state import ContentWorkflowState
from .nodes import (
    generate_node,
    review_node,
    self_correction_node,
    should_self_correct
)
from ..database.models import PostStatus

logger = logging.getLogger("WorkflowEngine")


def approval_entry_node(state: ContentWorkflowState) -> Dict[str, Any]:
    """Prepares post for human review in the approval queue."""
    return {
        "workflow_status": PostStatus.AWAITING_HUMAN_APPROVAL.value
    }


def create_content_graph() -> StateGraph:
    """Constructs the LangGraph state graph for AI content generation, quality audit, and self-correction."""
    workflow = StateGraph(ContentWorkflowState)

    # 1. Register Graph Nodes
    workflow.add_node("generate", generate_node)
    workflow.add_node("review", review_node)
    workflow.add_node("self_correct", self_correction_node)
    workflow.add_node("await_approval", approval_entry_node)

    # 2. Establish Workflow Edges
    workflow.set_entry_point("generate")
    workflow.add_edge("generate", "review")

    # 3. Conditional Routing from Quality Review
    workflow.add_conditional_edges(
        "review",
        should_self_correct,
        {
            "self_correct": "self_correct",
            "send_to_approval": "await_approval"
        }
    )

    workflow.add_edge("self_correct", "review")
    workflow.add_edge("await_approval", END)

    return workflow


# Compile the graph
content_graph = create_content_graph().compile()
