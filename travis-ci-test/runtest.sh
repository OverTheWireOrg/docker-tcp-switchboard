#!/bin/bash -ex

../docker-tcp-switchboard.py config.ini &
DAEMONPID=$!
function cleanup {
  echo "Cleaning up..."
  kill -9 $DAEMONPID
}
trap cleanup EXIT

./client.py


