# Simple Coding Agent

A terminal-based coding agent that understands natural-language requests and performs file operations inside a workspace folder. Powered by Ollama and gpt-oss:120b-cloud.

---

## Project Files

```
coding-agent/
├── agent.py       # The agent — only file you need to run
└── .gitignore     # Keeps backup files and cache out of git
```

---

## Requirements

- Python 3.9+
- [Ollama](https://ollama.com/download) installed on your machine

---

## Setup

**1. Install Ollama**
Download from https://ollama.com/download and install it.

**2. Pull the model**
```
ollama pull gpt-oss:120b-cloud
```

**3. Log in to Ollama**
```
ollama login
```
A browser window will open — sign in to your Ollama account.

**4. Install the Python library**
```
pip install openai
```

---

## Run

```
python agent.py
```

You will be asked for a workspace folder. This is where all files will be created and modified.

```
Enter workspace folder path: E:\Important Folder\Task Agents\workspace
Ready. Working inside: E:\Important Folder\Task Agents\workspace
>
```

> **Note:** If the folder doesn't exist yet, the agent will show `[Error] Folder not found` and ask again — create the folder first, then re-enter the same path.

---

## Example Session (actual run log)

```
> create a python file that prints Hello World
[Done] File created: workspace\hello_world.py

> explain hello_world.py
--- Explanation of hello_world.py ---
Prints "Hello World" to the console using the built-in print() function,
then terminates. Single statement, no functions/classes/imports.

> modify hello_world.py to print my name is Nina after Hello World
[Done] Backup created: workspace\hello_world.py.bak.20260701_031334
[Done] File modified: hello_world.py

> create a C++ file that implements a simple calculator
[Done] File created: workspace\simple_calculator.cpp

> create an HTML calculator with buttons and display
[Done] File created: workspace\calculator.html
```

---

## What You Can Do

**Create a file**
```
> create <language> file that <description>
[Done] File created: workspace\<filename>
```

**Explain a file**
```
> explain <filename>
--- Explanation of <filename> ---
...
```

**Modify a file**
A backup is created automatically before any change.
```
> modify <filename> to <change>
[Done] Backup created: workspace\<filename>.bak.<timestamp>
[Done] File modified: <filename>
```

**Exit**
```
> exit
```

---

## Error Messages

| Message | Meaning |
|---|---|
| `[Error] Folder not found` | The workspace path you entered does not exist |
| `[Error] File not found in workspace` | The file you mentioned does not exist |
| `[Warning] File already exists` | Use modify instead of create |
| `[Error] Access outside workspace is not allowed` | Cannot touch files outside the workspace |
| `[Error] Failed to connect to Ollama` | Ollama is not running — start it first |
| `[Error] Model returned invalid response` | Try again or rephrase your request |
| `[Unclear]` | The agent did not understand — be more specific |
