import os
import sys
import json
import shutil
import subprocess
import re
from datetime import datetime
from openai import OpenAI
 
# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
MODEL_NAME      = "gpt-oss:120b-cloud"
OLLAMA_BASE_URL = "http://localhost:11434/v1"
MEMORY_FILE     = "memory.json"
MAX_FIX_TRIES   = 2
 
client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
 
# ─────────────────────────────────────────
#  SYSTEM PROMPT
# ─────────────────────────────────────────
SYSTEM_PROMPT = """
You are a goal-oriented coding agent running inside a terminal.
 
ROLE:
- Help the user create, read, explain, modify, and run code files.
- Your job is to achieve the user's GOAL, not just execute the literal command.
- If the user says "run", your goal is that the code RUNS SUCCESSFULLY.
  This means: if it fails, fix it automatically and run again — without being asked.
- If code has errors, analyze the error and return a complete fixed version.
 
AUTOMATION PRINCIPLE:
- Think about what the user ultimately wants to achieve.
- Take all necessary steps to reach that goal, even if not explicitly requested.
- Example: "run app.py" → run → error detected → fix automatically → run again → success.
 
SAFETY RULES:
- Never access or modify files outside the workspace folder.
- Never run dangerous system commands (rm -rf, format, shutdown, etc.).
- Always work only inside the workspace.
- Always create a backup before modifying any file.
 
WORKSPACE LIMITS:
- All file operations must stay inside the selected workspace folder.
- Do not use absolute paths that go outside the workspace.
 
HANDLING UNCLEAR REQUESTS:
- If the request is unclear, return action "unclear" with a short reason.
- Do not guess — ask the user to clarify.
 
HANDLING CODE ERRORS:
- When given an error message and the code, return only the fixed code.
- Do not add explanations outside the code itself.
- Return complete file content, never partial snippets.
"""
 
# ─────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────
def log(label, message=""):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{label}] {message}")
 
# ─────────────────────────────────────────
#  MEMORY
# ─────────────────────────────────────────
def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "workspace":            "",
        "recent_files":         [],
        "previous_operations":  [],
        "last_error":           "",
        "last_fix_attempt":     ""
    }
 
def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)
 
def update_memory(memory, **kwargs):
    for key, value in kwargs.items():
        if key == "recent_files":
            files = memory.get("recent_files", [])
            if value not in files:
                files.insert(0, value)
            memory["recent_files"] = files[:10]
        elif key == "previous_operations":
            ops = memory.get("previous_operations", [])
            ops.insert(0, {
                "time": datetime.now().strftime("%H:%M:%S"),
                "op":   value
            })
            memory["previous_operations"] = ops[:20]
        else:
            memory[key] = value
    save_memory(memory)
 
# ─────────────────────────────────────────
#  TOOL: SAFE PATH
# ─────────────────────────────────────────
def safe_path(workspace, filename, create_dirs=False):
    if os.path.isabs(filename):
        log("ERROR", f"Absolute paths not allowed: {filename}")
        return None
    full_path = os.path.abspath(os.path.join(workspace, filename))
    if os.path.commonpath([workspace, full_path]) != workspace:
        log("ERROR", f"Access outside workspace blocked: {filename}")
        return None
    if create_dirs:
        parent = os.path.dirname(full_path)
        if not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
            log("INFO", f"Created directory: {parent}")
    return full_path
 
# ─────────────────────────────────────────
#  TOOL: LIST FILES
# ─────────────────────────────────────────
def tool_list_files(workspace):
    log("TOOL", "List Files")
    files = []
    for root, _, filenames in os.walk(workspace):
        for fn in filenames:
            if ".bak." not in fn and fn != "memory.json":
                rel = os.path.relpath(os.path.join(root, fn), workspace)
                files.append(rel)
    return files
 
# ─────────────────────────────────────────
#  TOOL: READ FILE
# ─────────────────────────────────────────
def tool_read_file(workspace, filename):
    log("TOOL", f"Read File → {filename}")
    filepath = safe_path(workspace, filename)
    if not filepath:
        return None
    if not os.path.isfile(filepath):
        log("ERROR", f"File not found: {filename}")
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()
 
# ─────────────────────────────────────────
#  TOOL: WRITE FILE
# ─────────────────────────────────────────
def tool_write_file(workspace, filename, content):
    log("TOOL", f"Write File → {filename}")
    filepath = safe_path(workspace, filename, create_dirs=True)
    if not filepath:
        return False
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    log("DONE", f"File saved: {filepath}")
    return True
 
# ─────────────────────────────────────────
#  TOOL: BACKUP FILE
# ─────────────────────────────────────────
def tool_backup_file(workspace, filename):
    log("TOOL", f"Backup File → {filename}")
    filepath = safe_path(workspace, filename)
    if not filepath or not os.path.isfile(filepath):
        log("ERROR", f"Cannot backup: {filename} not found")
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.bak.{timestamp}"
    shutil.copy2(filepath, backup_path)
    log("DONE", f"Backup created: {backup_path}")
    return backup_path
 
# ─────────────────────────────────────────
#  TOOL: RUN FILE
# ─────────────────────────────────────────
DANGEROUS_COMMANDS = [
    "rm ", "del ", "format", "shutdown", "rmdir",
    "os.remove", "shutil.rmtree", "subprocess"
]
 
def tool_run_file(workspace, filename):
    log("TOOL", f"Run File → {filename}")
    filepath = safe_path(workspace, filename)
    if not filepath:
        return None, "Access outside workspace blocked."
    if not os.path.isfile(filepath):
        log("ERROR", f"File not found: {filename}")
        return None, f"File not found: {filename}"
 
    ext = os.path.splitext(filename)[1].lower()
 
    # check for dangerous content
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    for danger in DANGEROUS_COMMANDS:
        if danger in content:
            log("ERROR", f"Dangerous command detected: {danger}")
            return None, f"Refused to run: dangerous command found ({danger})"
 
    # build run command based on extension
    if ext == ".py":
        cmd = [sys.executable, filepath]
    elif ext == ".js":
        cmd = ["node", filepath]
    elif ext in (".cpp", ".cc"):
        exe_path = filepath.replace(ext, ".exe" if os.name == "nt" else ".out")
        compile_result = subprocess.run(
            ["g++", filepath, "-o", exe_path],
            capture_output=True, text=True, cwd=workspace
        )
        if compile_result.returncode != 0:
            log("ERROR", "Compilation failed")
            return None, compile_result.stderr
        cmd = [exe_path]
    elif ext == ".html":
        log("INFO", f"HTML file — open in browser: {filepath}")
        return f"HTML file: open {filepath} in your browser.", None
    else:
        return None, f"Unsupported file type: {ext}"
 
    # اكتشاف هل الكود GUI ولا script عادي
    with open(filepath, "r", encoding="utf-8") as f:
        code_content = f.read()
    is_gui = any(kw in code_content for kw in [
        "tkinter", "tk.Tk", "PyQt", "wx.", "mainloop()", "QApplication"
    ])
 
    if is_gui:
        # GUI apps بنشغلها في الخلفية ومش بننتظر تنتهي
        log("INFO", "GUI application detected — launching in background")
        try:
            subprocess.Popen(cmd, cwd=workspace)
            log("RUN RESULT", "GUI launched successfully")
            return "GUI application launched. The window should open shortly.", None
        except FileNotFoundError as e:
            log("ERROR", str(e))
            return None, str(e)
 
    # ملفات عادية (CLI / scripts) بنشغلها ونستنى النتيجة
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=workspace
        )
        output = result.stdout.strip()
        error  = result.stderr.strip()
 
        if result.returncode == 0:
            log("RUN RESULT", output or "(no output)")
            return output, None
        else:
            log("RUN ERROR", error)
            return output, error
 
    except subprocess.TimeoutExpired:
        log("ERROR", "Execution timed out (15s)")
        return None, "Execution timed out after 15 seconds."
    except FileNotFoundError as e:
        log("ERROR", str(e))
        return None, str(e)
 
# ─────────────────────────────────────────
#  LLM HELPERS
# ─────────────────────────────────────────
def ask_llm(user_prompt, max_tokens=3000):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log("ERROR", f"Failed to connect to Ollama: {e}")
        return None
 
def extract_json(text):
    cleaned = re.sub(r"```(json)?|```", "", text.strip()).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None
 
def strip_code_fences(text):
    return re.sub(r"^```[a-zA-Z]*\n|\n```$", "", text.strip()).strip()
 
# ─────────────────────────────────────────
#  INTENT CLASSIFICATION
# ─────────────────────────────────────────
def classify_intent(user_request, existing_files):
    log("STEP", "Understand Request")
    prompt = (
        "Identify the user's intent and return JSON only, no extra text:\n"
        '{"action": "create"|"read"|"modify"|"run"|"fix"|"unclear", '
        '"filename": "filename if mentioned or empty", '
        '"reason": "short reason if unclear"}\n\n'
        "action meanings:\n"
        "- create: user wants a new code file\n"
        "- read: user wants to understand/explain an existing file\n"
        "- modify: user wants to edit an existing file\n"
        "- run: user wants to run/execute a file\n"
        "- fix: user wants to fix errors in a file then run it\n"
        "- unclear: request is not clear enough\n\n"
        f"Existing files in workspace: {existing_files}\n\n"
        f"User request: {user_request}"
    )
    raw = ask_llm(prompt, max_tokens=300)
    if not raw:
        return None
    data = extract_json(raw)
    if data:
        log("INTENT", f"action={data.get('action')} | file={data.get('filename','')}")
    return data
 
# ─────────────────────────────────────────
#  ACTIONS
# ─────────────────────────────────────────
def action_create(workspace, user_request, memory):
    log("STEP", "Select Tool → Create File")
    prompt = (
        "The user wants a new code file. Return JSON only:\n"
        '{"filename": "suitable_name.ext", "content": "full file content"}\n\n'
        "Choose a suitable filename and correct extension. Code must be complete and working.\n\n"
        f"Request: {user_request}"
    )
    raw = ask_llm(prompt)
    if not raw:
        log("ERROR", "Model returned empty response")
        return
    data = extract_json(raw)
    if not data:
        log("ERROR", "Model response is not valid JSON")
        return
    if "filename" not in data or "content" not in data:
        log("ERROR", f"Model response missing fields — got: {list(data.keys())}")
        return
    filename = data["filename"].strip()
    if not filename:
        log("ERROR", "Model returned empty filename")
        return
    content_text = data["content"].strip()
    if not content_text:
        log("ERROR", "Model returned empty file content")
        return
    filepath = safe_path(workspace, filename)
    if not filepath:
        return
    if os.path.exists(filepath):
        log("WARNING", f"File '{filename}' already exists — use modify instead")
        return
    if tool_write_file(workspace, filename, content_text):
        update_memory(memory, previous_operations=f"created {filename}", recent_files=filename)
 
def action_read(workspace, filename, memory):
    log("STEP", "Select Tool → Read File")
    content = tool_read_file(workspace, filename)
    if content is None:
        return
    log("STEP", "Ask Model → Explain")
    prompt = f"Explain this code file clearly.\n\nFilename: {filename}\n\nContent:\n{content}"
    explanation = ask_llm(prompt, max_tokens=1500)
    if explanation:
        print(f"\n--- Explanation of {filename} ---\n{explanation}\n")
        update_memory(memory, previous_operations=f"explained {filename}", recent_files=filename)
 
def action_modify(workspace, filename, user_request, memory):
    log("STEP", "Select Tool → Edit File")
    content = tool_read_file(workspace, filename)
    if content is None:
        return
    backup = tool_backup_file(workspace, filename)
    if not backup:
        return
    log("STEP", "Ask Model → Generate Edit")
    prompt = (
        "Modify the code file based on the request. "
        "Return the full file content only, no explanations, no ``` markers.\n\n"
        f"Filename: {filename}\n\nCurrent content:\n{content}\n\nRequest: {user_request}"
    )
    new_content = ask_llm(prompt)
    if not new_content:
        log("ERROR", "Model returned empty response for modify")
        return
    new_content = strip_code_fences(new_content)
    if not new_content.strip():
        log("ERROR", "Model returned empty content after stripping fences")
        return
    if tool_write_file(workspace, filename, new_content):
        update_memory(memory, previous_operations=f"modified {filename}", recent_files=filename)
 
def action_run(workspace, filename, memory):
    """
    Goal-oriented run:
    هدفه مش بس تشغيل الكود، هدفه إن الكود يشتغل بنجاح.
    لو فيه error يصلحه تلقائي ويشغله تاني من غير ما المستخدم يقول حاجة.
    """
    log("STEP", "Select Tool → Run File")
    log("TARGET FILE", filename)
 
    output, error = tool_run_file(workspace, filename)
 
    if not error:
        # اشتغل من أول مرة
        log("FINAL STATUS", "Run successful")
        update_memory(memory, previous_operations=f"ran {filename}", last_error="")
        print(f"\n[Output]\n{output}\n")
        return
 
    # فيه error — الأجنت بيقرر لوحده إنه يصلح عشان يحقق الهدف
    log("ERROR MESSAGE", error)
    log("DECISION", "Goal is to run successfully → auto-fixing to achieve goal")
    update_memory(memory, last_error=error)
 
    content = tool_read_file(workspace, filename)
    if content is None:
        return
 
    for attempt in range(1, MAX_FIX_TRIES + 1):
        log("FIX ATTEMPT", f"{attempt}/{MAX_FIX_TRIES} — fixing to achieve run goal")
 
        prompt = (
            "The code below has an error. Fix it and return the complete fixed file content only, "
            "no explanations, no ``` markers.\n\n"
            f"Filename: {filename}\n\n"
            f"Code:\n{content}\n\n"
            f"Error:\n{error}"
        )
        fixed_content = ask_llm(prompt)
        if not fixed_content:
            log("ERROR", "Model returned empty fix")
            break
 
        fixed_content = strip_code_fences(fixed_content)
        if not fixed_content.strip():
            log("ERROR", "Model returned empty content after fix")
            break
 
        update_memory(memory, last_fix_attempt=f"attempt {attempt} on {filename}")
 
        tool_backup_file(workspace, filename)
        tool_write_file(workspace, filename, fixed_content)
 
        log("STEP", f"Re-running after fix attempt {attempt}")
        output, error = tool_run_file(workspace, filename)
 
        if not error:
            log("FINAL STATUS", "Goal achieved — code runs successfully after auto-fix")
            update_memory(memory, previous_operations=f"auto-fixed and ran {filename}", last_error="")
            print(f"\n[Output]\n{output}\n")
            return
 
        log("RUN ERROR", f"Still failing after attempt {attempt}")
        log("ERROR MESSAGE", error)
        content = fixed_content
 
    log("FINAL STATUS", f"Could not achieve run goal after {MAX_FIX_TRIES} fix attempts")
    print(f"\n[Failed] Could not run {filename} successfully after {MAX_FIX_TRIES} fix attempts.")
    print(f"Last error:\n{error}\n")
 
def action_fix(workspace, filename, memory):
    log("STEP", "Select Tool → Fix File")
 
    # 1. read code
    content = tool_read_file(workspace, filename)
    if content is None:
        return
 
    # 2. run to get the error
    log("STEP", "Run Code → Detect Error")
    output, error = tool_run_file(workspace, filename)
 
    if not error:
        log("FINAL STATUS", "No errors found — code runs fine")
        print(f"\n[Output]\n{output}\n")
        return
 
    log("ERROR MESSAGE", error)
    update_memory(memory, last_error=error)
 
    # 3. try to fix (up to MAX_FIX_TRIES)
    for attempt in range(1, MAX_FIX_TRIES + 1):
        log("FIX ATTEMPT", f"{attempt}/{MAX_FIX_TRIES}")
 
        prompt = (
            "The code below has an error. Fix it and return the complete fixed file content only, "
            "no explanations, no ``` markers.\n\n"
            f"Filename: {filename}\n\n"
            f"Code:\n{content}\n\n"
            f"Error:\n{error}"
        )
        fixed_content = ask_llm(prompt)
        if not fixed_content:
            log("ERROR", "Model returned empty fix")
            break
 
        fixed_content = strip_code_fences(fixed_content)
        update_memory(memory, last_fix_attempt=f"attempt {attempt} on {filename}")
 
        # 4. backup then apply fix
        tool_backup_file(workspace, filename)
        tool_write_file(workspace, filename, fixed_content)
 
        # 5. run again
        log("STEP", "Run Again After Fix")
        output, error = tool_run_file(workspace, filename)
 
        if not error:
            log("FINAL STATUS", "Fix successful — code runs fine")
            update_memory(memory, previous_operations=f"fixed and ran {filename}", last_error="")
            print(f"\n[Output after fix]\n{output}\n")
            return
        else:
            log("RUN ERROR", f"Still failing after attempt {attempt}")
            log("ERROR MESSAGE", error)
            content = fixed_content  # try fixing the updated version next round
 
    log("FINAL STATUS", f"Could not fix after {MAX_FIX_TRIES} attempts")
    print(f"\n[Failed] Could not fix {filename} automatically.")
    print(f"Last error:\n{error}\n")
 
# ─────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────
def main():
    print("=" * 55)
    print("Coding Agent v2 — type 'exit' to quit")
    print("=" * 55)
 
    memory = load_memory()
 
    # workspace setup
    while True:
        default = memory.get("workspace", "")
        prompt_text = f"\nEnter workspace folder path [{default}]: " if default else "\nEnter workspace folder path: "
        workspace = input(prompt_text).strip()
        if not workspace and default:
            workspace = default
        if not workspace:
            continue
        workspace = os.path.abspath(workspace)
        if not os.path.isdir(workspace):
            print(f"[Error] Folder not found: {workspace}")
            continue
        break
 
    update_memory(memory, workspace=workspace)
    log("READY", f"Working inside: {workspace}")
 
    while True:
        user_request = input("\n> ").strip()
        if not user_request:
            continue
        if user_request.lower() in ("exit", "quit"):
            print("Goodbye!")
            break
 
        log("USER REQUEST", user_request)
 
        existing_files = tool_list_files(workspace)
        intent = classify_intent(user_request, existing_files)
 
        if not intent:
            print("[Error] Could not process request. Please try again.")
            continue
 
        action   = intent.get("action")
        filename = intent.get("filename", "").strip()
 
        log("SELECTED TOOL", action.upper() if action else "UNKNOWN")
        if filename:
            log("TARGET FILE", filename)
 
        if action == "create":
            action_create(workspace, user_request, memory)
 
        elif action == "read":
            if not filename:
                print("[Error] Please mention the filename. Example: explain main.py")
            else:
                action_read(workspace, filename, memory)
 
        elif action == "modify":
            if not filename:
                print("[Error] Please mention the filename. Example: modify app.py and add validation")
            else:
                action_modify(workspace, filename, user_request, memory)
 
        elif action == "run":
            if not filename:
                print("[Error] Please mention the filename. Example: run hello_world.py")
            else:
                action_run(workspace, filename, memory)
 
        elif action == "fix":
            if not filename:
                print("[Error] Please mention the filename. Example: fix app.py")
            else:
                action_fix(workspace, filename, memory)
 
        elif action == "unclear":
            reason = intent.get("reason", "Request is unclear.")
            log("UNCLEAR", reason)
            print(f"\n[Unclear] {reason}")
            print("Try: create / explain / modify / run / fix + filename\n")
 
        else:
            print("[Error] Unknown action. Please rephrase your request.")
 
 
if __name__ == "__main__":
    main()
