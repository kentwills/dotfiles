#!/bin/bash

# shootie for Mac
#
# Don't share this script with anyone. It contains a key that identifies
# rkwills.

# For help, visit https://trac.yelpcorp.com/wiki/Shootie

# loonix users should go to http://yelp-shootie.appspot.com/loonix

echo -n | pbcopy
rm -f /tmp/x.png
screencapture -i -s /tmp/x.png
curl -T /tmp/x.png http://yelp-shootie.appspot.com/put/a8e5c9d4dd854c71b6f14b5bccae6474 | pbcopy
