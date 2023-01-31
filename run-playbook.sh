#!/usr/bin/env zsh

AP=$(which ansible-playbook)

$AP -i localhost, -c local $@
