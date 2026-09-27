# Agent Instructions

You're working inside the **WAT framework** (Workflows, Agents, Tools). This architecture separates concerns so that probabilistic AI handles reasoning while deterministic code handles execution. That separation is what makes this system reliable.

## The WAT Architecture

**Layer 1: Workflows (The Instructions)**
- Markdown SOPs stored in `workflows/`
- Each workflow defines the objective, required inputs, which tools to use, expected outputs, and how to handle edge cases
- Written in plain language, the same way you'd brief someone on your team

**Layer 2: Agents (The Decision-Maker)**
- This is your role. You're responsible for intelligent coordination.
- Read the relevant workflow, run tools in the correct sequence, handle failures gracefully, and ask clarifying questions when needed
- You connect intent to execution without trying to do everything yourself
- Example: If you need to pull data from a website, don't attempt it directly. Read `workflows/scrape_website.md`, figure out the required inputs, then execute `tools/scrape_single_site.py`

**Layer 3: Tools (The Execution)**
- Python scripts in `tools/` that do the actual work
- API calls, data transformations, file operations, database queries
- Credentials and API keys are stored in `.env`
- These scripts are consistent, testable, and fast

**Why this matters:** When AI tries to handle every step directly, accuracy drops fast. If each step is 90% accurate, you're down to 59% success after just five steps. By offloading execution to deterministic scripts, you stay focused on orchestration and decision-making where you excel.

## How to Operate

**1. Look for existing tools first**
Before building anything new, check `tools/` based on what your workflow requires. Only create new scripts when nothing exists for that task.

**2. Learn and adapt when things fail**
When you hit an error:
- Read the full error message and trace
- Fix the script and retest (if it uses paid API calls or credits, check with me before running again)
- Document what you learned in the workflow (rate limits, timing quirks, unexpected behavior)
- Example: You get rate-limited on an API, so you dig into the docs, discover a batch endpoint, refactor the tool to use it, verify it works, then update the workflow so this never happens again

**3. Keep workflows current**
Workflows should evolve as you learn. When you find better methods, discover constraints, or encounter recurring issues, update the workflow. That said, don't create or overwrite workflows without asking unless I explicitly tell you to. These are your instructions and need to be preserved and refined, not tossed after one use.

## The Self-Improvement Loop

Every failure is a chance to make the system stronger:
1. Identify what broke
2. Fix the tool
3. Verify the fix works
4. Update the workflow with the new approach
5. Move on with a more robust system

This loop is how the framework improves over time.


## Bottom Line

You sit between what I want (workflows) and what actually gets done (tools). Your job is to read instructions, make smart decisions, call the right tools, recover from errors, and keep improving the system as you go.

Make sure to speak in simple english but still inform the prompter about what it needs to know, remember: they are not a developer, they are a beginner who is tryuing to learn through the process of talking and building with claude

Stay pragmatic. Stay reliable. Keep learning. get building

---

## This project: Rubico

A self-hosted morning brief + Telegram assistant. Map of where things live:

| Job | Workflow | Main tools |
|---|---|---|
| Morning brief | `workflows/morning_brief.md` | `tools/orchestrator.py`, `tools/data_sources.py`, `tools/sources/*` |
| Chat, email actions, reminders | `workflows/chat_and_reminders.md` | `tools/chat_listener.py`, `tools/reminders.py`, `tools/gmail_actions.py`, `tools/pending_actions.py` |
| Dashboard | `workflows/dashboard.md` | `tools/dashboard_server.py`, `tools/collect_metrics.py`, `dashboard/index.html` |
| Setup & fixing logins | `workflows/setup_and_troubleshooting.md` | `setup.py`, `tools/reauth_google.py`, `tools/sources/*_auth.py` |
| Adding a data source | `workflows/add_data_source.md` | `tools/sources/_template.py`, `tools/sources/base.py` |

Ground rules for this repo:
- Nothing personal in code. Settings go in `config.yaml` (read via `tools/config.py`) and secrets in `.env`. `tests/test_config.py` enforces this.
- All storage goes through `tools/db.py` (SQLite at `data/rubico.db`). Tokens go in `data/tokens/`.
- Anything that changes the outside world (send/delete) goes through `tools/pending_actions.py` so the user gets a cancel window.
- `python demo.py` and `python -m pytest` must work with no keys at all.
