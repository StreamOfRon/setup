#!/usr/bin/env zsh

AP=$(which ansible-pull)
SETUPDIR="${HOME}/.setup"

$AP -U https://github.com/StreamOfRon/setup.git -i $SETUPDIR/hosts -d $SETUPDIR $@ >/dev/null 2>&1