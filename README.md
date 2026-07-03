
# Coding Agent — Harness Engineering

A goal-oriented terminal coding agent built on top of Task 1. The agent understands natural-language requests and performs file operations inside a selected workspace. The key upgrade in this version is **automated code execution with self-healing**: when you ask the agent to run a file and it fails, the agent diagnoses the error, fixes the code, and runs it again — all on its own, without you asking.

---

## What This Agent Does

The agent supports five actions, chosen automatically based on what you type:

**Create** — generates a new code file with a suitable name and extension
**Explain** — reads an existing file and explains what it does
**Modify** — edits an existing file based on your request (always backs up first)
**Run** — executes a file; if it fails, auto-fixes and runs again
**Fix** — explicitly reads, runs, diagnoses, fixes, and reruns a file

---

## Execution Flow

Every request follows this flow:

```
User types request
        ↓
Agent lists workspace files for context
        ↓
Model classifies intent → action + filename
        ↓
Agent selects the matching tool
        ↓
Tool executes → result printed to terminal
```

For **Run** specifically, the flow extends automatically if there is an error:

```
Run file
   ↓ error detected
Agent decides: goal is to run successfully → must fix first
   ↓
Read current code
   ↓
Send code + error to model → get fixed version
   ↓
Backup original file
   ↓
Write fixed version
   ↓
Run again
   ↓ success
Print output
```

---

## Live Test Results

The following commands were tested and produced the results below.

**Create a GUI app**
```
> create a python tkinter GUI app called manager_student.py for managing
  student names and grades
[DONE] File saved: workspace\manager_student.py
```

**Run a GUI app**
```
> run manager_student.py
[INFO] GUI application detected — launching in background
[RUN RESULT] GUI launched successfully
[FINAL STATUS] Run successful
```

<img width="1917" height="1012" alt="image" src="https://github.com/user-attachments/assets/8adb8a87-d6d9-4825-b4f7-2cf8a1c20511" />


The student manager window opened on screen immediately.

**Create a file with intentional bugs**
```
> create a python file called broken.py
```
The file `app.py` (inventory management system, ~200 lines) was placed in the workspace with 7 logic bugs including type mismatches between str and int.

**Run the broken file — auto-fix in action**
```
> run broken.py
[RUN ERROR] TypeError: can only concatenate str (not "int") to str
[DECISION] Goal is to run successfully → auto-fixing to achieve goal
[FIX ATTEMPT] 1/2 — fixing to achieve run goal
[DONE] Backup created: broken.py.bak.20260703_042928
[DONE] File saved: broken.py
[STEP] Re-running after fix attempt 1
[FINAL STATUS] Goal achieved — code runs successfully after auto-fix

[Output]
========================================
   Inventory Management System
========================================
Added: Laptop
Added: Mouse
...
Total products : 9
Total units    : 191
Total value    : $36949.19
```
The agent fixed the bug in one attempt and ran the file successfully.

**Combined request (evaluator-style command)**
```
> open broken.py, run it, find the error, fix it and run it again
[INTENT] action=fix | file=broken.py
[FINAL STATUS] No errors found — code runs fine
```
The agent understood the full multi-step instruction as a single goal and handled it correctly.


<img width="1917" height="1017" alt="image" src="https://github.com/user-attachments/assets/5093bae6-506d-442f-ab1f-5933bdf1c412" />


---

## Terminal Logs

Every step is printed with a timestamp:

| Label | Meaning |
|---|---|
| `[USER REQUEST]` | What you typed |
| `[STEP]` | Current stage in the flow |
| `[INTENT]` | What the agent understood — action and filename |
| `[SELECTED TOOL]` | Which tool was chosen |
| `[TARGET FILE]` | File being operated on |
| `[RUN RESULT]` | Output of a successful execution |
| `[RUN ERROR]` | Error output from a failed execution |
| `[DECISION]` | Agent's reasoning when choosing to auto-fix |
| `[FIX ATTEMPT]` | Which fix attempt out of the maximum |
| `[FINAL STATUS]` | End result of the full operation |
| `[ERROR]` | Any blocking error — file missing, model issue, etc. |

---

## Memory

After every session the agent saves `memory.json` automatically:

```json
{
  "workspace": "E:\\Important Folder\\Task Agents\\workspace",
  "recent_files": ["broken.py", "manager_student.py", "todo_app.py"],
  "previous_operations": [
    { "time": "04:29:28", "op": "auto-fixed and ran broken.py" },
    { "time": "04:27:00", "op": "created broken.py" },
    { "time": "04:22:03", "op": "ran manager_student.py" },
    { "time": "04:21:53", "op": "modified manager_student.py" },
    { "time": "04:16:11", "op": "ran manager_student.py" }
  ],
  "last_error": "",
  "last_fix_attempt": "attempt 1 on broken.py"
}
```


<img width="1391" height="837" alt="image" src="https://github.com/user-attachments/assets/f8cb80c5-44c8-449a-a658-46404aec8128" />


On the next run, the agent loads this file and pre-fills the workspace path so you do not have to type it again.

---

## Safety

- The agent never accesses files outside the workspace folder.
- Any filename pointing outside the workspace (e.g. `../../etc/passwd`) is blocked before the operation runs.
- Absolute paths in filenames are rejected immediately.
- Files containing dangerous shell patterns (`subprocess.call("rm -rf ...")`, `os.system("format ...")`, etc.) are refused before execution.
- A backup is always created before any file is modified or overwritten.

---

## Error Messages

| Message | Meaning |
|---|---|
| `[Error] Folder not found` | Workspace path does not exist |
| `[Error] File not found in workspace` | File you mentioned does not exist |
| `[Warning] File already exists` | Use modify instead of create |
| `[Error] Access outside workspace blocked` | Path escapes the workspace |
| `[Error] Dangerous pattern detected` | File contains a dangerous command |
| `[Error] Failed to connect to Ollama` | Ollama is not running |
| `[Error] Model returned empty response` | Try again or rephrase your request |
| `[Unclear]` | Agent could not determine intent — add more detail |

---

## Project Files

```
coding-agent/
├── agent.py       ← the agent, run this
└── memory.json    ← auto-generated, not uploaded to git
