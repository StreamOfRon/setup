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
  $BREW install ansible flock
  ;;

"Linux")
  SUPPORTED=('apt' 'pamac')
  PKGMGR=""
  for name in $SUPPORTED ; do
    PKGMGR=$(which ${name})
    if $? == 0 ; then
      case "${name}" in
      "apt")
        sudo $PKGMGR update
        sudo $PKGMGR install ansible
        ;;

      "pamac")
        $PKGMGR update
        $PKGMGR install ansible flock
        ;;

      *)
        echo "No supported package manager for Linux detected"
        exit 1
        ;;
      esac
    fi
  done

  ;;

*)
  echo "Unknown OS environment: ${OS}"
  exit 1
  ;;
esac

mkdir -p $SETUPDIR
curl -fsSL https://raw.githubusercontent.com/StreamOfRon/setup/main/run-ansible-pull.sh | zsh
