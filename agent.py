import os
import shutil
import json
import re
from datetime import datetime
from openai import OpenAI

MODEL_NAME = "gpt-oss:120b-cloud"
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")


def ask_llm(system_prompt, user_prompt, max_tokens=3000):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Error] Failed to connect to Ollama: {e}")
        print("Make sure Ollama is running on your machine.")
        return None


def extract_json(text):
    cleaned = re.sub(r"```(json)?|```", "", text.strip()).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def safe_path(workspace, filename):
    full_path = os.path.abspath(os.path.join(workspace, filename))
    if os.path.commonpath([workspace, full_path]) != workspace:
        print(f"[Error] Access outside workspace is not allowed: {filename}")
        return None
    return full_path


def classify_intent(user_request, existing_files):
    system_prompt = (
        "You are part of a coding agent. Your only job is to identify the user's intent "
        "and return JSON only, no extra text, in this exact format:\n"
        '{"action": "create" | "read" | "modify" | "unclear", '
        '"filename": "filename if mentioned or empty", '
        '"reason": "short reason if unclear"}\n\n'
        "action should be:\n"
        "- create: user wants a new code file\n"
        "- read: user wants to understand/explain an existing file\n"
        "- modify: user wants to edit/add something to an existing file\n"
        "- unclear: request is not clear enough\n\n"
        f"Files currently in workspace: {existing_files}"
    )
    raw = ask_llm(system_prompt, user_request, max_tokens=300)
    if not raw:
        return None
    return extract_json(raw)


def create_file(workspace, user_request):
    system_prompt = (
        "You are a coding agent. The user wants a new code file. "
        "Return JSON only, no extra text, in this format:\n"
        '{"filename": "suitable_name.extension", "content": "full file content"}\n\n'
        "Choose a suitable filename and correct extension based on the request. "
        "The code must be complete and working."
    )
    raw = ask_llm(system_prompt, user_request)
    if not raw:
        return

    data = extract_json(raw)
    if not data or "filename" not in data or "content" not in data:
        print("[Error] Model returned invalid response.")
        return

    filepath = safe_path(workspace, data["filename"])
    if not filepath:
        return

    if os.path.exists(filepath):
        print(f"[Warning] File '{data['filename']}' already exists. Use modify instead.")
        return

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(data["content"])

    print(f"[Done] File created: {filepath}")


def read_file(workspace, filename):
    if not filename:
        print("[Error] Please specify a filename. Example: explain main.py")
        return

    filepath = safe_path(workspace, filename)
    if not filepath:
        return

    if not os.path.isfile(filepath):
        print(f"[Error] File '{filename}' not found in workspace.")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    system_prompt = (
        "You are a coding agent. Read the code file and explain it clearly: "
        "what it does and what its main parts do. Write as plain text, not JSON."
    )
    explanation = ask_llm(system_prompt, f"Filename: {filename}\n\nContent:\n{content}", max_tokens=1500)
    if explanation:
        print(f"\n--- Explanation of {filename} ---\n{explanation}\n")


def modify_file(workspace, filename, user_request):
    if not filename:
        print("[Error] Please specify a filename. Example: modify app.py and add input validation")
        return

    filepath = safe_path(workspace, filename)
    if not filepath:
        return

    if not os.path.isfile(filepath):
        print(f"[Error] File '{filename}' not found in workspace.")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        current_content = f.read()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.bak.{timestamp}"
    shutil.copy2(filepath, backup_path)
    print(f"[Done] Backup created: {backup_path}")

    system_prompt = (
        "You are a coding agent. Modify the existing code file based on the user's request. "
        "Return the full file content after modification only, no explanation, no ``` markers."
    )
    user_prompt = (
        f"Filename: {filename}\n\n"
        f"Current content:\n{current_content}\n\n"
        f"Modification request: {user_request}"
    )
    new_content = ask_llm(system_prompt, user_prompt)
    if not new_content:
        return

    new_content = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", new_content.strip())

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"[Done] File modified: {filename}")


def list_files(workspace):
    files = []
    for root, _, filenames in os.walk(workspace):
        for fn in filenames:
            if ".bak." not in fn:
                rel = os.path.relpath(os.path.join(root, fn), workspace)
                files.append(rel)
    return files


def main():
    print("=" * 55)
    print("Simple Coding Agent — type 'exit' to quit")
    print("=" * 55)

    while True:
        workspace = input("\nEnter workspace folder path: ").strip()
        if not workspace:
            continue
        workspace = os.path.abspath(workspace)
        if not os.path.isdir(workspace):
            print(f"[Error] Folder not found: {workspace}")
            continue
        break

    print(f"\nReady. Working inside: {workspace}")

    while True:
        user_request = input("\n> ").strip()

        if not user_request:
            continue

        if user_request.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        existing_files = list_files(workspace)
        intent = classify_intent(user_request, existing_files)

        if not intent:
            print("[Error] Could not understand the request. Please try again.")
            continue

        action = intent.get("action")
        filename = intent.get("filename", "").strip()

        if action == "create":
            create_file(workspace, user_request)
        elif action == "read":
            read_file(workspace, filename)
        elif action == "modify":
            modify_file(workspace, filename, user_request)
        else:
            reason = intent.get("reason", "Request is unclear.")
            print(f"[Unclear] {reason}")
            print("Try specifying: create a file / explain a file / modify a file")


if __name__ == "__main__":
    main()