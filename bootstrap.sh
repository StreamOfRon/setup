#!/usr/bin/env zsh

SETUPREPO="https://github.com/StreamOfRon/setup.git"
SETUPDIR="${HOME}/.setup"
OS=$(uname)

case "${OS}" in
"Darwin")
  BREW=$(which brew)
  if [[ ! -x $BREW || $? -eq 1 ]] ; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [ -x /usr/local/bin/brew ] ; then
      BREW="/usr/local/bin/brew"
    elif [ -x /opt/homebrew/bin/brew ] ; then
      BREW="/opt/homebrew/bin/brew"
    else
      echo "Still can't find homebrew, aborting..."
      exit 1
    fi
    echo "eval \"$(${BREW} shellenv)\"" >> ~/.zprofile
    eval "$(${BREW} shellenv)"
  fi

  NONINTERACTIVE=1
  $BREW install ansible git flock </dev/null
  ;;

"Linux")
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ansible git </dev/null
  elif command -v apt >/dev/null 2>&1; then
    sudo apt update
    sudo DEBIAN_FRONTEND=noninteractive apt install -y ansible git </dev/null
  elif command -v pamac >/dev/null 2>&1; then
    pamac update --no-confirm </dev/null
    pamac install --no-confirm ansible git flock </dev/null
  else
    echo "No supported package manager for Linux detected"
    exit 1
  fi
  ;;

*)
  echo "Unknown OS environment: ${OS}"
  exit 1
  ;;
esac

mkdir -p $SETUPDIR
RUN_ANSIBLE_PULL="$(mktemp)"
curl -fsSL https://raw.githubusercontent.com/StreamOfRon/setup/main/run-ansible-pull.sh -o "$RUN_ANSIBLE_PULL"
zsh "$RUN_ANSIBLE_PULL"
rm -f "$RUN_ANSIBLE_PULL"
