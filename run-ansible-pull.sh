#!/usr/bin/env zsh

AP=$(which ansible-pull)
SETUPDIR="${HOME}/.setup"

$AP --clean -U https://github.com/StreamOfRon/setup.git -i localhost, -l localhost -c local -d $SETUPDIR $@ main.yml
