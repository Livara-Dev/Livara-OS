# SPDX-License-Identifier: GPL-3.0-or-later
# Livara Terminal's interactive Bash profile. Other terminal profiles are unchanged.
[[ $- == *i* ]] || return
[[ ${__LIVARA_PROMPT_LOADED:-0} == 1 ]] && return
__LIVARA_PROMPT_LOADED=1
[[ ! -r /etc/bash.bashrc ]] || source /etc/bash.bashrc
[[ ! -r "$HOME/.bashrc" ]] || source "$HOME/.bashrc"

# Directory and branch names are data. Disable prompt command substitution so
# a path such as '$(touch file)' cannot execute when it appears in the prompt.
shopt -u promptvars
shopt -s histappend checkwinsize
HISTCONTROL=ignoreboth:erasedups
HISTSIZE=5000
HISTFILESIZE=10000

alias ll='ls -alF --color=auto'
alias la='ls -A --color=auto'
alias l='ls -CF --color=auto'
alias c='clear'
alias work='cd "$HOME/Livara/Workspace"'
alias cases='cd "$HOME/Livara/Cases"'

__livara_prompt_safe() {
    local livara_text
    livara_text=$(printf '%s' "$1" | LC_ALL=C tr -d '\000-\037\177')
    livara_text=${livara_text//\\/\\\\}
    printf '%s' "$livara_text"
}

__livara_prompt() {
    local livara_status=$? livara_where livara_branch livara_identity livara_mark livara_state
    livara_where=$(__livara_prompt_safe "${PWD/#"$HOME"/\~}")
    livara_branch=$(command git --no-optional-locks symbolic-ref --quiet --short HEAD 2>/dev/null) || livara_branch=''
    livara_branch=$(__livara_prompt_safe "$livara_branch")
    [[ -z $livara_branch ]] || livara_branch="  ·  $livara_branch"
    if (( EUID == 0 )); then
        livara_identity='\[\e[38;2;255;151;173m\]root'
        livara_mark='#'
    else
        livara_identity='\[\e[38;2;198;160;255m\]\u'
        livara_mark='❯'
    fi
    if (( livara_status == 0 )); then
        livara_state='\[\e[38;2;166;227;183m\]●'
    else
        livara_state="\[\e[38;2;255;151;173m\]exit $livara_status"
    fi
    PS1="\[\e[38;2;111;119;150m\]╭─ ${livara_identity}\[\e[38;2;111;119;150m\]@\h  \[\e[38;2;237;242;255m\]${livara_where}\[\e[38;2;146;191;255m\]${livara_branch}\n\[\e[38;2;111;119;150m\]╰─ ${livara_state} \[\e[38;2;198;160;255m\]${livara_mark} \[\e[0m\]"
    return 0
}
PROMPT_COMMAND=__livara_prompt

livara-help() {
    printf '\n  LIVARA TERMINAL\n  work / cases    Open your workspace or case folders\n  ll / la / l     Directory views\n  livara status   Observe the current system\n  livara center   Open the Control Center\n  Ctrl+Shift+T    New tab    Ctrl+Shift+F    Find text\n  Ctrl+Shift+C/V  Copy/paste\n\n'
}

if [[ ${TERM:-dumb} != dumb ]]; then
    printf '\n\033[38;2;198;160;255m  L I V A R A\033[0m  \033[38;2;146;191;255m/  T E R M I N A L\033[0m\n'
    printf '\033[38;2;157;171;203m  A little curiosity. A clear command line.\n  Type livara-help for shortcuts.\033[0m\n\n'
fi
