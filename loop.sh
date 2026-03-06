#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./loop.sh                               # Build mode, unlimited
#   ./loop.sh 20                            # Build mode, max 20
#   ./loop.sh build 15                      # Build mode, max 15 (explicit)
#   ./loop.sh test                          # Test mode (prompt_test.md), unlimited
#   ./loop.sh test 5                        # Test mode, max 5
#   ./loop.sh architecture                  # Architecture mode (prompt_architecture.md), unlimited
#   ./loop.sh architecture 5                # Architecture mode, max 5
#   ./loop.sh plan                          # Full planning, unlimited
#   ./loop.sh plan 5                        # Full planning, max 5
#   ./loop.sh plan-work "user auth"         # Scoped planning, default max 5
#   ./loop.sh plan-work "user auth" 8       # Scoped planning, max 8

MODE="build"
PROMPT_FILE="PROMPT_build.md"
MAX_ITERATIONS=0
WORK_SCOPE="${WORK_SCOPE:-}"

if [ "${1:-}" = "plan" ]; then
  MODE="plan"
  PROMPT_FILE="PROMPT_plan.md"
  MAX_ITERATIONS="${2:-0}"
elif [ "${1:-}" = "test" ]; then
  MODE="test"
  PROMPT_FILE="prompt_test.md"
  MAX_ITERATIONS="${2:-0}"
elif [ "${1:-}" = "architecture" ]; then
  MODE="architecture"
  PROMPT_FILE="prompt_architecture.md"
  MAX_ITERATIONS="${2:-0}"
elif [ "${1:-}" = "plan-work" ]; then
  MODE="plan-work"
  PROMPT_FILE="PROMPT_plan_work.md"
  WORK_SCOPE="${WORK_SCOPE:-${2:-}}"
  if [ -z "$WORK_SCOPE" ]; then
    echo "Error: plan-work requires a work description."
    echo "Usage: ./loop.sh plan-work \"description of work\" [max_iterations]"
    exit 1
  fi
  MAX_ITERATIONS="${3:-5}"
elif [ "${1:-}" = "build" ]; then
  MODE="build"
  PROMPT_FILE="PROMPT_build.md"
  MAX_ITERATIONS="${2:-0}"
elif [[ "${1:-}" =~ ^[0-9]+$ ]]; then
  MAX_ITERATIONS="$1"
fi

if ! [[ "$MAX_ITERATIONS" =~ ^[0-9]+$ ]]; then
  echo "Error: max iterations must be a non-negative integer."
  exit 1
fi

CURRENT_BRANCH="$(git branch --show-current)"
if [ "$MODE" = "plan-work" ] && { [ "$CURRENT_BRANCH" = "main" ] || [ "$CURRENT_BRANCH" = "master" ]; }; then
  echo "Error: plan-work should run on a work branch, not $CURRENT_BRANCH."
  echo "Create one first, e.g. git checkout -b trace/your-scope"
  exit 1
fi

# Resolve agent command once per run.
if [ -z "${AGENT_CMD:-}" ]; then
  while :; do
    read -r -p "Which agent are you using? (claude/codex): " AGENT_CHOICE
    AGENT_CHOICE="$(echo "$AGENT_CHOICE" | tr '[:upper:]' '[:lower:]')"
    case "$AGENT_CHOICE" in
      claude)
        AGENT_CMD="claude -p"
        break
        ;;
      codex)
        # danger-full-access required so agent can reach Docker daemon (e.g. docker compose)
        AGENT_CMD="codex exec --sandbox danger-full-access -"
        break
        ;;
      cursor)
        echo "Cursor is not supported in this script yet. Choose claude or codex."
        ;;
      *)
        echo "Invalid option. Choose claude or codex."
        ;;
    esac
  done
fi

if [ ! -f "$PROMPT_FILE" ]; then
  echo "Error: prompt file not found: $PROMPT_FILE"
  exit 1
fi

ITERATION=0
while :; do
  ITERATION=$((ITERATION + 1))
  echo "=================================================="
  echo "Mode: $MODE | Iteration: $ITERATION | Prompt: $PROMPT_FILE"
  [ "$MAX_ITERATIONS" -gt 0 ] && echo "Max iterations: $MAX_ITERATIONS"
  [ "$MODE" = "plan-work" ] && echo "Work scope: $WORK_SCOPE"
  echo "=================================================="

  if [ "$MODE" = "plan-work" ]; then
    {
      awk -v scope="$WORK_SCOPE" '{gsub(/\$\{WORK_SCOPE\}/, scope); print}' "$PROMPT_FILE"
      printf "\n"
      cat AGENTS.md
    } | eval "$AGENT_CMD"
  else
    cat "$PROMPT_FILE" AGENTS.md | eval "$AGENT_CMD"
  fi

  if [ -n "$(git status --porcelain 2>/dev/null || true)" ]; then
    REPO_ROOT="$(git rev-parse --show-toplevel)"
    LOOP_MSG="$REPO_ROOT/.loop-commit-msg"
    LOOP_FULL="$REPO_ROOT/.loop-commit-msg.full"
    if [ -f "$LOOP_MSG" ]; then
      SUMMARY=$(head -1 "$LOOP_MSG" | tr -d '\n\r')
    else
      SUMMARY="(no summary)"
    fi
    printf 'agent-trace loop %s (%s): %s\n' "$ITERATION" "$MODE" "$SUMMARY" > "$LOOP_FULL"
    git add -A || true
    git commit -F "$LOOP_FULL" || true
    rm -f "$LOOP_MSG" "$LOOP_FULL"
    git push -u origin "$(git branch --show-current)" || true
  fi

  # Stop after n iterations when MAX_ITERATIONS is set (e.g. ./loop.sh build 15 or ./loop.sh 15)
  if [ "$MAX_ITERATIONS" -gt 0 ] && [ "$ITERATION" -ge "$MAX_ITERATIONS" ]; then
    echo "Reached max iterations ($MAX_ITERATIONS). Stopping."
    break
  fi
done
echo "Loop finished."
exit 0
