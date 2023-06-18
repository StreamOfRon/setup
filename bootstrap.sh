#!/usr/bin/env zsh

SETUPREPO="https://github.com/StreamOfRon/setup.git"
SETUPDIR="${HOME}/.setup"

BREW=$(which brew)
if [[ ! -x $BREW || $? -eq 1 ]] ; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [ -x /usr/local/bin/brew ] ; then
    BREW="/usr/local/bin/brew"
  else if [ -x /opt/homebrew/bin/brew ] ; then
    BREW="/opt/homebrew/bin/brew"
  else
    echo "Still can't find homebrew, aborting..."
    exit 1
  fi
  echo "eval \"$(${BREW} shellenv)\"" >> ~/.zprofile
  eval "$(${BREW} shellenv)"
fi

NONINTERACTIVE=1
$BREW install ansible flock

mkdir -p $SETUPDIR
curl -fsSL https://raw.githubusercontent.com/StreamOfRon/setup/main/run-ansible-pull.sh | zsh
