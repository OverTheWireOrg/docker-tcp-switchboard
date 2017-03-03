#!/bin/bash -ex

../docker-tcp-switchboard.py config.ini &
DAEMONPID=$!
function cleanup {
  echo "Cleaning up..."
  kill -9 $DAEMONPID
}
trap cleanup EXIT

sleep 2 # give time to startup

./client.py 4 10 7 10


