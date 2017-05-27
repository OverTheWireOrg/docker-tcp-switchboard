#!/bin/bash -ex

# start docker, and wait until it's likely up
(sudo /etc/init.d/docker start  && sleep 3 ) || true

# build echoserv and upperserv
docker build -t echoserv -f testimages/Dockerfile.echoserv testimages
docker build -t upperserv -f testimages/Dockerfile.upperserv testimages
sleep 2

sudo apt-get install python3-pip
sudo pip3 install ../requirements.txt

# start the switchboard
../docker-tcp-switchboard.py config.ini &
DAEMONPID=$!
function cleanup {
  echo "Cleaning up..."
  kill -9 $DAEMONPID
}
trap cleanup EXIT

sleep 2 # give time to startup

./client.py 4 10 7 10

# Show logfile
cat /tmp/logfile
