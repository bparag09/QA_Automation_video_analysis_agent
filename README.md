# QA Automation Video Analysis Agent

LLM-based analysis agent that verifies whether claimed execution steps are **actually visible in run video evidence**.

It compares:

- planner/internal thought logs (`agent_inner_logs.json`)
- test run video(s) (`.webm` / `.mp4`)
- final Hercules output (`test_result.xml`)

Then generates a step-level deviation report (`OBSERVED`, `DEVIATION`, `NOT_VERIFIABLE`).

## Project structure

```text
QA_Automation_video_analysis_agent/
├── agent_logs/                         # Input artifacts (sample logs, xml, video)
├── reports/                            # Generated reports and debug logs
├── src/
│   └── video_analysis_agent/
│       ├── cli/
│       │   └── main.py                 # Argument parsing and CLI entry
│       ├── config/
│       │   └── settings.py             # App settings dataclass
│       ├── core/
│       │   └── models.py               # Domain entities and report models
│       ├── pipeline/
│       │   └── analyzer.py             # End-to-end orchestration flow
│       └── services/
│           ├── parser_service.py       # Planner log + Hercules XML parsing
│           ├── video_service.py        # Frame sampling and video debug payload
│           ├── llm_service.py          # OpenAI vision + step evaluation
│           └── report_service.py       # Report + artifact writer
├── run_agent.py                        # Thin bootstrap entrypoint
├── requirements.txt
└── README.md
```

## Setup

### 1) Create a virtual environment (recommended)

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) `.env` setup (required)

Create a `.env` file in the project root (same folder as `run_agent.py`) and add:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

Notes:

- Do not quote the key.
- Keep `.env` private (already ignored via `.gitignore`).
- You can also set `OPENAI_API_KEY` as a system environment variable instead.

## How to run

From project root:

```bash
python run_agent.py
```

Default inputs:

- `agent_logs/agent_inner_logs.json`
- `agent_logs/test_result.xml`
- videos auto-discovered under `agent_logs/`

If your videos are elsewhere:

```bash
python run_agent.py --videos "path/to/run.webm"
```

Multiple videos:

```bash
python run_agent.py --videos "path/to/part1.webm" "path/to/part2.webm"
```

Useful options:

- `--model gpt-4.1-mini` (default)
- `--frame-interval 5`
- `--max-frames 24`
- `--output-dir reports`

## Output

Generated files in `reports/`:

- `deviation_report.json`
- `deviation_report.md`
- `logs/video_sampling_log.json` (from `services/video_service.py`)
- `logs/llm_analysis_log.json` (from `services/llm_service.py`)

Report timestamping:

- `deviation_report.json` includes `generated_at_utc`
- `deviation_report.md` includes a `Generated At (UTC)` header

Markdown report format:


| Step    | Description              | Result    | Notes                                        |
| ------- | ------------------------ | --------- | -------------------------------------------- |
| Claim 1 | Click search icon        | OBSERVED  | Search UI appears at 00:12                   |
| Claim 2 | Enter "Rainbow sweater"  | OBSERVED  | Search result title visible                  |
| Claim 3 | Apply Turtle Neck filter | DEVIATION | Only Crew Neck visible; Turtle Neck not seen |


If every claim is supported:

- `➡️ No deviations detected.`

## Approach (transparent)

1. **Input ingestion**
  - Parse planner logs into planned and claimed execution steps.
  - Parse final XML to capture fail/pass and assertion text.
2. **Video evidence extraction**
  - Sample frames on a fixed timeline.
  - Send timestamped frames to OpenAI vision model.
  - Collect structured visual events.
3. **Step comparison**
  - Compare each claimed step against visual events.
  - Cross-check against final XML assertion/failure text.
4. **Report generation**
  - Emit per-step status with notes and assumptions.

## Notes

- Accuracy is prioritized over speed.
- If no relevant visual evidence exists, step is marked `NOT_VERIFIABLE`.

