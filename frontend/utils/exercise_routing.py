"""exercise_routing.py

Helpers for building ExerciseTopic dicts and extra_context strings from
learning-path session data, for the treatment cohort (interactive_exercises=True).
"""

from __future__ import annotations

_PROFICIENCY_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}


def session_to_exercise_topic(
    session: dict,
    learner_profile: dict,
    knowledge_points: list[dict],
) -> tuple[dict, str]:
    """Convert a SessionItem + derived knowledge points into an ExerciseTopic and extra_context.

    Args:
        session: A single SessionItem dict from the learning path.
        learner_profile: The learner profile dict.
        knowledge_points: List of KnowledgePoint dicts from /derive-knowledge-points.

    Returns:
        A tuple of (topic_dict, extra_context_str).
        topic_dict has keys: skill, domain, goal, difficulty_hint.
        extra_context_str is a grounding string for the ExercisePlanner.
    """
    # --- skill ---
    # Prefer knowledge-point names; fall back to outcomes then associated_skills
    if knowledge_points:
        skill = ", ".join(kp["name"] for kp in knowledge_points)
    else:
        outcomes = session.get("desired_outcome_when_completed", [])
        if outcomes:
            skill = ", ".join(o["name"] for o in outcomes)
        else:
            associated = session.get("associated_skills", [])
            skill = ", ".join(associated)

    # --- domain ---
    domain = ""
    if isinstance(learner_profile, dict):
        domain = learner_profile.get("occupation", "")

    # --- goal ---
    goal = session.get("abstract", "")

    # --- difficulty_hint ---
    # Max proficiency among desired outcomes
    outcomes = session.get("desired_outcome_when_completed", [])
    difficulty_hint = "beginner"
    if outcomes:
        max_level = max(
            (o.get("level", "beginner") for o in outcomes),
            key=lambda lvl: _PROFICIENCY_ORDER.get(str(lvl).lower(), 0),
        )
        difficulty_hint = str(max_level).lower()

    topic_dict = {
        "skill": skill,
        "domain": domain,
        "goal": goal,
        "difficulty_hint": difficulty_hint,
    }

    # --- extra_context ---
    lines = ["## Session Context"]
    lines.append(f"Session title: {session.get('title', '')}")
    lines.append(f"Session goal: {goal}")
    lines.append("")

    if knowledge_points:
        lines.append("### Knowledge Points to practice")
        for kp in knowledge_points:
            kp_line = f"- **{kp['name']}** ({kp.get('type', '')})"
            lines.append(kp_line)
        lines.append("")

    if outcomes:
        lines.append("### Desired outcomes when session is completed")
        for o in outcomes:
            lines.append(f"- {o['name']} at `{o.get('level', '')}` level")
        lines.append("")

    associated = session.get("associated_skills", [])
    if associated:
        lines.append("### Associated skills")
        lines.append(", ".join(associated))

    extra_context = "\n".join(lines).strip()
    return topic_dict, extra_context
