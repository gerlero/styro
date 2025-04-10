#!/bin/sh
set -e -u -o pipefail

if [[ -z "$FOAM_USER_APPBIN" ]]; then
    echo "Error: No OpenFOAM environment found. Please activate (source) the OpenFOAM environment first." >&2
    exit 1
fi

if [[ -n "$(command -v styro 2>/dev/null)" && "$(command -v styro)" != "$FOAM_USER_APPBIN/styro" ]]; then
    echo "Error: Managed installation of 'styro' found at $(command -v styro)."
    exit 1
elif [[ -e "$FOAM_USER_APPBIN/styro" ]]; then
    echo "Will replace/upgrade existing 'styro' in \$FOAM_USER_APPBIN ($FOAM_USER_APPBIN)."
else
    echo "Will install 'styro' to \$FOAM_USER_APPBIN ($FOAM_USER_APPBIN)."
fi

echo "Press Enter to continue or Ctrl-C to abort."
read

echo "Downloading and installing styro..."
mkdir -p "$FOAM_USER_APPBIN"
curl -L https://github.com/gerlero/styro/releases/latest/download/styro-$(uname)-$(uname -m).tar.gz | tar -xz -C "$FOAM_USER_APPBIN"

echo "Done."
echo "styro is now installed in \$FOAM_USER_APPBIN."
echo "You can run it by typing 'styro' in the terminal."
