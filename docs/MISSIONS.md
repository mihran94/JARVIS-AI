# JARVIS missions — supervised model-directed work

## What a mission is

A **mission** is one goal the owner gave, worked towards in a short,
visible sequence of real actions.

```
owner goal  →  JARVIS proposes one action  →  JARVIS checks it  →  the tool runs it
            →  the real result goes back to the model  →  next action  →  final answer
```

The owner watches every step in **Mission Control** (the desktop page),
and the whole loop is bounded: at most six steps and three minutes.

## The rules

| Rule | Where it is enforced | Where it is tested |
|---|---|---|
| The model may only choose a tool that is in the catalogue | `core/mission.py` — an unknown tool ends the mission | `test_a_tool_that_is_not_in_the_catalogue_does_not_exist` |
| Arguments must match the tool's schema | `core/mission_tools.py` — `check_arguments` | `test_an_argument_the_tool_does_not_take_is_refused` |
| A tool that changes something needs the owner's approval | `agents/gateway.py` through the existing one-use policy | `test_a_tool_that_changes_something_asks_the_owner_first` |
| A refused tool never runs | the gateway refuses before the operation | `test_a_refused_tool_is_never_run` |
| An emergency stop cancels the mission at the next step | `security/policy.py` through the runtime check | `test_an_emergency_stop_cancels_the_mission` |
| The mission cannot run for ever | `MAX_STEPS` and `BUDGET_SECONDS` | `test_a_mission_cannot_run_for_ever` |
| Only a real tool result is evidence | `mission.tools_used` is written only after the tool returned | `test_a_tool_that_fails_is_not_counted_as_evidence` |

## The tool catalogue

`core/mission_tools.py` is the whole surface the model can reach. There
is no shell tool, no "write this file" tool and no arbitrary network
tool.

| Tool | Reads or changes | Bound to |
|---|---|---|
| `current_time` | reads | the clock of this computer |
| `system_status` | reads | `desktop/system_metrics.py` — the real CPU, RAM, disk, GPU and temperature readings |
| `evaluate_expression` | reads | an AST walk that allows arithmetic and nothing else |
| `research_fetch` | reads one public HTTPS page | `research/research.py` — private and loopback addresses are refused before any request |
| `list_directory` | reads | the mission folder only; a link is refused |
| `read_text_file` | reads | the mission folder only; 20 000 characters at most |
| `memory_search` | reads | the real `MemoryService`, BM25 ranked |
| `memory_remember` | **changes** | the real `MemoryService` |
| `launch_app` | **changes** | `automation/windows.py` — Notepad and Calculator only |

The two tools that change something are the two that ask the owner.
Everything else reports what is already there.

## The answer envelope

The model answers with one JSON object and nothing else:

```json
{"action": "tool", "tool": "memory_search", "arguments": {"query": "launch"}, "thought": "I need the saved note."}
{"action": "answer", "answer": "The launch is on Friday.", "thought": "That is enough."}
```

Anything else is refused, and the refusal says what was expected, so the
model can correct itself on the next turn. Prose is never parsed into a
command.

## What the owner sees

The Mission Control page paints the mission as it runs:

- one rail, one marker per step, coloured by kind — a thought, a call,
  an approval, a result, a failure;
- the newest step glows;
- the counter says **Step 2 of 6** — the number of calls that ran. There
  is no percentage and no estimate, because neither is known;
- the result card carries the answer;
- the evidence line names the tools that really ran, and says *no tool
  ran* when none did.

A tool that failed is not on the evidence line, and the mission never
says that something happened that did not happen.

## Where it runs

The mission runs in a worker thread, so the console keeps painting while
the model thinks. The owner's approval dialog belongs to the interface
thread, so the worker hands the question over and waits for the answer.

The **Emergency Stop** cancels a running mission, and closing the window
waits for the mission to stop before the window goes.

## What it is not

- It is not a chat. The model is asked for one decision at a time.
- It is not autonomy. The mission runs what the owner asked for, stops
  at the first refusal, and stops at the step limit.
- It is not a general agent framework. There is no plugin loader, no
  dynamic tool registration from the model, and no self-modifying
  catalogue.
- It has not run on a physical Windows machine. The suite covers the
  loop, the refusals and the interface; a real provider key and a real
  owner have not yet been used against it.
