#!/usr/bin/env zsh

BREW=$(which brew)
SETUPDIR="${HOME}/.setup"
SETUPREPO="https://github.com/StreamOfRon/setup.git"

if [[ ! -x $BREW || $? -eq 1 ]] ; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  BREW="$(which brew)"
fi

NONINTERACTIVE=1
$BREW install ansible flock

mkdir -p $SETUPDIR

curl -fsSL https://raw.githubusercontent.com/StreamOfRon/setup/main/run-ansible-pull.sh | zsh
