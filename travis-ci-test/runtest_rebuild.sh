#!/bin/bash -ex

# this test does a rebuild of one of the images while
# a connection is active

# start the switchboard
../docker-tcp-switchboard.py config.ini &
DAEMONPID=$!
function cleanup {
  echo "Cleaning up..."
  kill -9 $DAEMONPID || true # daemon could already be dead
  kill -9 $NCPID || true # netcat is hopefully disconnected already
  cat /tmp/logfile
  rm -f /tmp/logfile
}
trap cleanup EXIT

sleep 2 # give time to startup

# open a connection
((while true; do echo hi; sleep 1; done; sleep 1000) | nc 0 2222 ) &
NCPID=$!
sleep 10

# show running containers, for debugging the test
docker ps -a

# now rebuild the image
docker build -t echoserv -f testimages/Dockerfile.echoserv-mangled testimages
sleep 2

# kill the client
kill -s SIGTERM $NCPID
sleep 2

# show running containers, for debugging the test
docker ps -a
sleep 2

# and now stop the server
kill -s SIGTERM $DAEMONPID
sleep 2

if [ $(docker ps -aq|wc -l) -eq 0 ]; 
then 
	echo "Success: All containers are gone"; 
else 
	echo "Fail: Some containers remain"; 
	docker ps -a; 
	false; 
fi

# restore the old image
docker build -t echoserv -f testimages/Dockerfile.echoserv testimages
