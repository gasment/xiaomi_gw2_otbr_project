#!/bin/sh
BASE=/data/otbr
SUPERVISOR=/tmp/mi-otbr-supervisor.pid
CHILD_PID=/tmp/mi-otbr.pid
STOP=/tmp/mi-otbr.stop
pid_matches() {
    case "$1" in ''|*[!0-9]*) return 1;; esac
    [ -r "/proc/$1/cmdline" ] || return 1
    CMD=$(tr '\000' ' ' < "/proc/$1/cmdline") || return 1
    case "$2:$CMD" in
        "host:$BASE/mi-otbr-host $BASE/config.yaml --run ") return 0;;
        "supervisor:sh $BASE/supervisor.sh "|"supervisor:/bin/sh $BASE/supervisor.sh ") return 0;;
    esac
    return 1
}
