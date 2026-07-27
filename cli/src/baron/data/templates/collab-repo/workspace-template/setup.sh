#!/usr/bin/env bash
# {{PROJECT_NAME}} — workspace setup script
#
# Usage:
#   ./setup.sh <persona-slug>                          # Just workspace (default)
#   REGISTER_CRON=yes ./setup.sh <persona-slug>        # Workspace + cron stub
#
# Creates ~/Workspace/{{PROJECT_NAME}}/<persona-slug>/ with both repos cloned
# and per-repo git identity configured. Drops a CLAUDE.md (Claude Code) +
# AGENTS.md (code-puppy / others) at the workspace root pointing at the
# canonical agents/<persona>/AGENT.md.
#
# With REGISTER_CRON=yes (only set this if you are the persona's default_runner),
# also generates a per-runtime cron stub in the workspace based on the persona's
# AGENT.md frontmatter `runtime:` field:
#   launchd-cron    → ~/Workspace/.../com.<project>.<persona>.plist + wrapper
#   systemd-timer   → ~/Workspace/.../<project>-<persona>.{service,timer}
#   cloud-routine   → prints /schedule command to run in Claude Code
#   gh-actions-*    → skipped (cron lives in code repo, not on this machine)
#
# The stub is GENERATED but NOT LOADED. After review, you load it manually
# per the persona's FAILOVER.md. This keeps the script idempotent and avoids
# accidental double-registration.

set -euo pipefail

PERSONA_SLUG="${1:-}"
if [[ -z "$PERSONA_SLUG" ]]; then
  echo "Usage: $0 <persona-slug>" >&2
  echo "  e.g. $0 librarian" >&2
  exit 1
fi

# Configuration — skill fills these at scaffold time
PROJECT_NAME="{{PROJECT_NAME}}"
CODE_REPO="{{CODE_REPO}}"      # e.g. owner/code-repo
COLLAB_REPO="{{COLLAB_REPO}}"  # e.g. owner/collab-repo
CODE_REPO_DIR="$(basename "$CODE_REPO")"
COLLAB_REPO_DIR="$(basename "$COLLAB_REPO")"

WORKSPACE_ROOT="${WORKSPACE_ROOT:-$HOME/Workspace/$PROJECT_NAME/$PERSONA_SLUG}"

echo "→ Setting up $PERSONA_SLUG workspace at $WORKSPACE_ROOT"
mkdir -p "$WORKSPACE_ROOT"
cd "$WORKSPACE_ROOT"

# Clone both repos if missing (idempotent)
if [[ ! -d "$CODE_REPO_DIR/.git" ]]; then
  echo "→ Cloning $CODE_REPO"
  git clone "git@github.com:$CODE_REPO.git" "$CODE_REPO_DIR"
else
  echo "✓ $CODE_REPO_DIR already cloned"
fi

if [[ ! -d "$COLLAB_REPO_DIR/.git" ]]; then
  echo "→ Cloning $COLLAB_REPO"
  git clone "git@github.com:$COLLAB_REPO.git" "$COLLAB_REPO_DIR"
else
  echo "✓ $COLLAB_REPO_DIR already cloned"
fi

# Read persona identity from the canonical AGENT.md frontmatter
AGENT_MD="$WORKSPACE_ROOT/$COLLAB_REPO_DIR/agents/$PERSONA_SLUG/AGENT.md"
if [[ ! -f "$AGENT_MD" ]]; then
  echo "✗ $AGENT_MD does not exist — persona slug typo, or AGENT.md missing in collab repo" >&2
  exit 1
fi

# Extract persona name + email from frontmatter (simple grep — assumes well-formed YAML)
PERSONA_NAME=$(awk '/^persona:/{print $2; exit}' "$AGENT_MD")
PERSONA_EMAIL=$(awk -F'[`/]' '/^\| Git email/{print $4; exit}' "$AGENT_MD" 2>/dev/null || echo "")
if [[ -z "$PERSONA_NAME" ]]; then
  echo "✗ Could not extract persona name from $AGENT_MD frontmatter" >&2
  exit 1
fi
if [[ -z "$PERSONA_EMAIL" ]]; then
  echo "! Could not extract git email from AGENT.md. Set it manually after this script." >&2
fi

# Configure per-repo git identity
echo "→ Setting git identity in both clones: $PERSONA_NAME / $PERSONA_EMAIL"
for repo_dir in "$CODE_REPO_DIR" "$COLLAB_REPO_DIR"; do
  git -C "$WORKSPACE_ROOT/$repo_dir" config user.name "$PERSONA_NAME"
  if [[ -n "$PERSONA_EMAIL" ]]; then
    git -C "$WORKSPACE_ROOT/$repo_dir" config user.email "$PERSONA_EMAIL"
  fi
done

# Copy workspace bootstrap files (CLAUDE.md for Claude Code, AGENTS.md for code-puppy etc.)
TEMPLATE_DIR="$WORKSPACE_ROOT/$COLLAB_REPO_DIR/workspace-template"
if [[ -d "$TEMPLATE_DIR" ]]; then
  for f in CLAUDE.md AGENTS.md; do
    if [[ -f "$TEMPLATE_DIR/$f" && ! -f "$WORKSPACE_ROOT/$f" ]]; then
      # Simple placeholder substitution
      sed \
        -e "s|{{PERSONA_NAME}}|$PERSONA_NAME|g" \
        -e "s|{{PERSONA_SLUG}}|$PERSONA_SLUG|g" \
        -e "s|{{PERSONA_EMAIL}}|$PERSONA_EMAIL|g" \
        -e "s|{{PROJECT_NAME}}|$PROJECT_NAME|g" \
        -e "s|{{CODE_REPO}}|$CODE_REPO|g" \
        -e "s|{{COLLAB_REPO}}|$COLLAB_REPO|g" \
        -e "s|{{CODE_REPO_DIR}}|$CODE_REPO_DIR|g" \
        -e "s|{{COLLAB_REPO_DIR}}|$COLLAB_REPO_DIR|g" \
        "$TEMPLATE_DIR/$f" > "$WORKSPACE_ROOT/$f"
      echo "✓ Wrote $WORKSPACE_ROOT/$f"
    fi
  done
else
  echo "! No workspace-template/ in $COLLAB_REPO_DIR — skipping CLAUDE.md/AGENTS.md drop"
fi

# ---------------------------------------------------------------------------
# Cron stub generation (opt-in via REGISTER_CRON=yes)
# ---------------------------------------------------------------------------

generate_launchd_stub() {
  local label="com.${PROJECT_NAME_LOWER}.${PERSONA_SLUG}"
  local plist="$WORKSPACE_ROOT/${label}.plist"
  local wrapper="$WORKSPACE_ROOT/run-${PERSONA_SLUG}.sh"

  if [[ -f "$plist" ]]; then
    echo "✓ $plist already exists — leaving alone (idempotent)"
    return 0
  fi

  cat > "$wrapper" <<EOF
#!/bin/zsh
# Scheduled run of ${PROJECT_NAME}'s ${PERSONA_NAME} (${PERSONA_SLUG}).
# Invoked by ~/Library/LaunchAgents/${label}.plist
cd "$WORKSPACE_ROOT" || exit 1
exec /usr/local/bin/claude -p "Run your daily cycle." --dangerously-skip-permissions
EOF
  chmod +x "$wrapper"

  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${label}</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>${wrapper}</string>
    </array>

    <!-- TODO: review StartCalendarInterval against AGENT.md cadence (${CADENCE}).
         launchd uses LOCAL time, not UTC. Adjust Hour for your TZ offset.
         For "daily 22:00 UTC" on US Pacific: Hour=15 during PDT; Hour=14 during PST. -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>15</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>${WORKSPACE_ROOT}/run.log</string>
    <key>StandardErrorPath</key>
    <string>${WORKSPACE_ROOT}/run.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

  echo "✓ Wrote $plist + $wrapper"
  echo "  To load (after reviewing the time):"
  echo "    cp $plist ~/Library/LaunchAgents/${label}.plist"
  echo "    launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/${label}.plist"
  echo "    launchctl list | grep ${label}"
}

generate_systemd_stub() {
  local unit_base="${PROJECT_NAME_LOWER}-${PERSONA_SLUG}"
  local service="$WORKSPACE_ROOT/${unit_base}.service"
  local timer="$WORKSPACE_ROOT/${unit_base}.timer"
  local wrapper="$WORKSPACE_ROOT/run-${PERSONA_SLUG}.sh"

  if [[ -f "$service" ]]; then
    echo "✓ $service already exists — leaving alone (idempotent)"
    return 0
  fi

  cat > "$wrapper" <<EOF
#!/usr/bin/env bash
# Scheduled run of ${PROJECT_NAME}'s ${PERSONA_NAME} (${PERSONA_SLUG}).
# Invoked by ${unit_base}.service
cd "$WORKSPACE_ROOT" || exit 1
exec claude -p "Run your daily cycle." --dangerously-skip-permissions
EOF
  chmod +x "$wrapper"

  cat > "$service" <<EOF
[Unit]
Description=${PROJECT_NAME} ${PERSONA_NAME} (${PERSONA_SLUG}) — scheduled run

[Service]
Type=oneshot
ExecStart=${wrapper}
StandardOutput=append:${WORKSPACE_ROOT}/run.log
StandardError=append:${WORKSPACE_ROOT}/run.log
EOF

  # systemd OnCalendar accepts UTC explicitly — derive from CADENCE if possible
  cat > "$timer" <<EOF
[Unit]
Description=${PROJECT_NAME} ${PERSONA_NAME} (${PERSONA_SLUG}) timer

[Timer]
# TODO: review OnCalendar against AGENT.md cadence (${CADENCE}).
# For "daily HH:MM UTC", use: OnCalendar=*-*-* HH:MM:00 UTC
OnCalendar=*-*-* 22:00:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
EOF

  echo "✓ Wrote $service + $timer + $wrapper"
  echo "  To install (after reviewing OnCalendar):"
  echo "    mkdir -p ~/.config/systemd/user"
  echo "    cp ${unit_base}.{service,timer} ~/.config/systemd/user/"
  echo "    systemctl --user daemon-reload"
  echo "    systemctl --user enable --now ${unit_base}.timer"
  echo "    systemctl --user list-timers | grep ${unit_base}"
}

if [[ "${REGISTER_CRON:-no}" == "yes" ]]; then
  # Read runtime + cadence from the persona's AGENT.md
  RUNTIME=$(awk -F': *' '/^runtime:/{gsub(/"/,"",$2); print $2; exit}' "$AGENT_MD" 2>/dev/null || echo "")
  CADENCE=$(awk -F': *' '/^cadence:/{gsub(/"/,"",$2); print $2; exit}' "$AGENT_MD" 2>/dev/null || echo "")
  PROJECT_NAME_LOWER=$(echo "$PROJECT_NAME" | tr '[:upper:]' '[:lower:]')

  echo ""
  echo "→ REGISTER_CRON=yes — generating cron stub for runtime: ${RUNTIME:-<unset>}"

  case "$RUNTIME" in
    launchd-cron)
      generate_launchd_stub
      ;;
    systemd-timer)
      generate_systemd_stub
      ;;
    cloud-routine)
      echo "→ cloud-routine: nothing to generate locally. In Claude Code, run:"
      echo "    /schedule cron='${CADENCE}' \\"
      echo "      task='Run the ${PROJECT_NAME} ${PERSONA_NAME} per agents/${PERSONA_SLUG}/AGENT.md.'"
      ;;
    gh-actions-cron|gh-actions-event)
      echo "→ ${RUNTIME}: cron lives in ${CODE_REPO}/.github/workflows/${PERSONA_SLUG}.yml — nothing to do on this machine."
      ;;
    "")
      echo "! No runtime field in ${AGENT_MD} — skipping cron stub. Add 'runtime: <value>' to the AGENT.md frontmatter."
      ;;
    *)
      echo "! Unknown runtime '${RUNTIME}' — skipping cron stub. Supported: launchd-cron, systemd-timer, cloud-routine, gh-actions-cron, gh-actions-event."
      ;;
  esac
else
  RUNTIME=$(awk -F': *' '/^runtime:/{gsub(/"/,"",$2); print $2; exit}' "$AGENT_MD" 2>/dev/null || echo "")
  if [[ -n "$RUNTIME" ]]; then
    echo ""
    echo "→ runtime: $RUNTIME — cron stub generation skipped."
    echo "  If this machine is the persona's default_runner, re-run with REGISTER_CRON=yes."
  fi
fi

echo ""
echo "✓ Workspace ready at $WORKSPACE_ROOT"
echo ""
echo "Next steps:"
echo "  1. cd $WORKSPACE_ROOT"
echo "  2. Open Claude Code (or your AI agent) in this folder"
echo "  3. Read $WORKSPACE_ROOT/$COLLAB_REPO_DIR/agents/$PERSONA_SLUG/AGENT.md"
echo "  4. Follow the persona's session-start ritual"
