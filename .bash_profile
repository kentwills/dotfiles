# all environment munging should go here.
# this file only runs once, on login


# set PATH so it includes user's private bin if it exists
if [ -d ~/bin ] ; then
    export PATH=~/bin:"${PATH}"
fi
if [ -d /usr/local/bin ] ; then
    export PATH=/usr/local/sbin:/usr/local/bin:"${PATH}"
fi
if [ -d ~/.local/bin ] ; then
    export PATH=~/.local/bin:"${PATH}"
fi


# include .bashrc if it exists
if [ -f ~/.bashrc ]; then
    . ~/.bashrc
fi
