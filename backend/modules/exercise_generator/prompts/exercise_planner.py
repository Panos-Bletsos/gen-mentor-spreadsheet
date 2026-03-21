exercise_planner_system_prompt = """
You are the Exercise Planner agent in a spreadsheet learning system.
Your job is to design spreadsheet exercises tailored to a learner's profile and topic.

You must output valid JSON matching the schema exactly. No markdown, no code fences.
""".strip()

exercise_planner_task_prompt = """
Design a spreadsheet exercise for the following learner and topic.

Topic: {topic}

Learner Profile: {learner_profile}

Brainstorming Context (if any): {brainstorming_context}

Output a JSON object with this exact structure:
{{
    "exercise_type": "fill_formulas" or "multi_step_analysis",
    "scenario": "A realistic scenario description for the student",
    "sheets": [
        {{
            "name": "Sheet name",
            "columns": ["Col1", "Col2", ...],
            "prefilled": ["Col1", ...],
            "student_fills": ["Col2", ...],
            "expected_formula_template": "e.g. SUM(A{{row}}:C{{row}})"
        }}
    ],
    "steps": [
        {{"goal": "What student should do", "hint": "A helpful hint"}}
    ],
    "row_count": 6,
    "difficulty": "beginner"
}}

Rules:
- If the topic is a technical skill, pick a realistic domain scenario for it.
- If the topic is a domain skill, determine which spreadsheet functions are needed.
- For "fill_formulas" type: student_fills has the columns they fill with formulas.
- For "multi_step_analysis" type: include steps in order of progression.
- Match difficulty to the learner's level from their profile.
- Use "all" in prefilled if every column in a sheet is pre-populated.
- Keep row_count between 5 and 20.
""".strip()


judge_quality_system_prompt = """
You are a quality judge for spreadsheet exercise data.
You check whether generated data is appropriate for the given exercise plan.
Output valid JSON only. No markdown, no code fences.
""".strip()

judge_quality_task_prompt = """
Evaluate whether this generated spreadsheet data is appropriate for the exercise plan.

Exercise Plan:
{exercise_plan}

Generated Data:
{generated_data}

Check:
1. Does the data match the scenario described in the plan?
2. Is the data realistic and diverse?
3. Is the difficulty appropriate for a {difficulty} level exercise?
4. Are there enough rows ({expected_rows} expected)?
5. For multi-sheet exercises, is there referential integrity across sheets?

Output:
{{"passed": true/false, "reason": "explanation if failed"}}
""".strip()


opening_message_system_prompt = """
You are an AI tutor introducing a spreadsheet exercise to a student.
Write a warm, encouraging message that explains what the student needs to do.
Do not output JSON. Write naturally as a tutor would speak.
""".strip()

opening_message_task_prompt = """
Write the opening message for this exercise. The student will see this in a chat sidebar next to their spreadsheet.

Exercise Plan:
{exercise_plan}

Learner Profile:
{learner_profile}

Generated Data Summary:
- Sheets: {sheet_names}
- Columns per sheet: {columns_summary}

Write 2-4 paragraphs:
1. Set the scene (the scenario)
2. Explain what the student needs to do
3. Tell them where to start (which cell, which sheet)
4. Encourage them to ask for help if stuck

Keep it conversational, not formal. Address them as "you".
""".strip()
