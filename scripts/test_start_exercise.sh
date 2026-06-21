#!/usr/bin/env bash
# Test the /start-exercise endpoint with the last known topic from traces_2026-04-22.jsonl

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:5000}"

payload=$(cat <<'EOF'
{
  "topic": "Skill: XLOOKUP/INDEX-MATCH, data cleaning + joins (via Power Query or formulas), and summary metrics (COUNTIFS/SUMIFS or PivotTables); Domain: sales Customer 360 (Accounts/Companies view); Goal: Build an Accounts/Companies 360 sheet that pulls company profile fields and aggregates related contacts and deal outcomes into one unified view.; Suggested difficulty: beginner",
  "learner_profile": "",
  "brainstorming_history": [
    {"role": "assistant", "content": "Hi! What would you like to practice today? You can tell me a specific skill or your goal you'd like to achieve."},
    {"role": "user", "content": "i would like to learn how to build a customer360"},
    {"role": "assistant", "content": "Great goal - building a Customer 360 is a really practical spreadsheet project. What's the main domain/context (e.g., sales, customer support, marketing)?"},
    {"role": "user", "content": "sales"},
    {"role": "assistant", "content": "Awesome - Customer 360 for sales is a great choice. What difficulty level? beginner, intermediate, or advanced?"},
    {"role": "user", "content": "beginner"},
    {"role": "assistant", "content": "Great - sales + beginner is set. Which view do you want to build first? 1) Accounts/Companies 2) Contacts/Leads 3) Both"},
    {"role": "user", "content": "1"}
  ],
  "model_provider": "openai",
  "model_name": "gpt-5.4"
}
EOF
)

response=$(curl -s -4 -w "\n%{http_code}" -X POST "$BACKEND_URL/start-exercise" \
  -H "Content-Type: application/json" \
  -d "$payload")

http_code=$(echo "$response" | tail -1)
body=$(echo "$response" | head -n -1)

echo "HTTP $http_code"
echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
