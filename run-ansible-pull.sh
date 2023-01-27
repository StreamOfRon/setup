#!/usr/bin/env zsh

AP=$(which ansible-pull)

$AP -U https://github.com/StreamOfRon/setup.git -i $SETUPDIR/hosts -d $SETUPDIR $@