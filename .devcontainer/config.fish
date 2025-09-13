# Fish shell configuration for devcontainer

# Add local npm bin to PATH (already set in ENV, this ensures it persists)
set -gx PATH /home/python/.local/bin $PATH

if status is-interactive
    # Configure persistent history locations
    set -gx XDG_DATA_HOME /commandhistory/.local/share
    set -gx FZF_DEFAULT_OPTS "--history=/commandhistory/.fzf_history"

    # Disable virtual environment prompt (devcontainer is always in venv)
    set -gx VIRTUAL_ENV_DISABLE_PROMPT 1
    set -gx SPACEFISH_VENV_SHOW false
end
