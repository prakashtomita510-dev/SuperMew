import re

path = r"d:\agent_demo\SuperMew\backend\rag_pipeline.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

new_grade = """GRADE_PROMPT = (
    "You are a grader assessing whether the retrieved context is SUFFICIENT to answer the user question. \\n"
    "Retrieved Context: \\n\\n {context} \\n\\n"
    "User Question: {question} \\n"
    "Criteria: \\n"
    "1. Does the context contain the specific answer? \\n"
    "2. If the question is complex or ambiguous, does the context resolve all parts? \\n"
    "Grade 'yes' if the context is sufficient, 'no' if it is missing information or if the question needs clarification/expansion."
)"""

new_answer = """ANSWER_PROMPT = (
    "You are a helpful assistant. Use the provided context to answer the question concisely. \\n\\n"
    "Context: \\n {context} \\n\\n"
    "Question: {question} \\n"
    "Instructions: \\n"
    "1. If the context is in Chinese, respond in Chinese. If in English, respond in English. \\n"
    "2. Provide a direct answer. Avoid long introductions or meta-talk about the context. \\n"
    "3. Use citations like [1], [2] for each factual point. \\n"
    "4. If the context does not contain the answer, state that clearly and briefly. \\n"
    "Answer:"
)"""

# Use regex to find the blocks regardless of trailing spaces
content = re.sub(r'GRADE_PROMPT = \([\s\S]*?\)', new_grade, content, count=1)
content = re.sub(r'ANSWER_PROMPT = \([\s\S]*?\)', new_answer, content, count=1)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated rag_pipeline.py prompts successfully.")
