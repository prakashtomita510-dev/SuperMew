path = r"d:\agent_demo\SuperMew\backend\rag_pipeline.py"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if "GRADE_PROMPT = (" in line:
        new_lines.append("GRADE_PROMPT = (\n")
        new_lines.append('    "You are a grader assessing whether the retrieved context is SUFFICIENT to answer the user question. \\n"\n')
        new_lines.append('    "Retrieved Context: \\n\\n {context} \\n\\n"\n')
        new_lines.append('    "User Question: {question} \\n"\n')
        new_lines.append('    "Criteria: \\n"\n')
        new_lines.append('    "1. Does the context contain the specific answer? \\n"\n')
        new_lines.append('    "2. If the question is complex or ambiguous, does the context resolve all parts? \\n"\n')
        new_lines.append('    "Grade \'yes\' if the context is sufficient, \'no\' if it is missing information or if the question needs clarification/expansion."\n')
        new_lines.append(")\n")
        skip = True
    elif "ANSWER_PROMPT = (" in line:
        new_lines.append("ANSWER_PROMPT = (\n")
        new_lines.append('    "You are a helpful assistant. Use the provided context to answer the question concisely. \\n\\n"\n')
        new_lines.append('    "Context: \\n {context} \\n\\n"\n')
        new_lines.append('    "Question: {question} \\n"\n')
        new_lines.append('    "Instructions: \\n"\n')
        new_lines.append('    "1. If the context is in Chinese, respond in Chinese. If in English, respond in English. \\n"\n')
        new_lines.append('    "2. Provide a direct answer. Avoid long introductions or meta-talk about the context. \\n"\n')
        new_lines.append('    "3. Use citations like [1], [2] for each factual point. \\n"\n')
        new_lines.append('    "4. If the context does not contain the answer, state that clearly and briefly. \\n"\n')
        new_lines.append('    "Answer:"\n')
        new_lines.append(")\n")
        skip = True
    elif skip and line.strip() == ")":
        skip = False
        continue
    
    if not skip:
        new_lines.append(line)

with open(path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)
print("Cleaned up rag_pipeline.py prompts.")
