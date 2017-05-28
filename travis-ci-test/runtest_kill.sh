#!/bin/bash -ex

# start the switchboard
../docker-tcp-switchboard.py config.ini &
DAEMONPID=$!
function cleanup {
  echo "Cleaning up..."
  kill -9 $DAEMONPID || true # daemon could already be dead
  kill -9 $NCPID || true # netcat is hopefully disconnected already
  rm -f /tmp/logfile
}
trap cleanup EXIT

sleep 2 # give time to startup

# open a connection
((echo hi; sleep 1000) | nc 0 2222 ) &
NCPID=$!
sleep 3

# show running containers, for debugging the test
docker ps -a

# now kill the server, which should clean up everything
kill -s SIGTERM $DAEMONPID
sleep 2

# Show logfile
cat /tmp/logfile

if [ $(docker ps -aq|wc -l) -eq 0 ]; 
then 
	echo "Success: All containers are gone"; 
else 
	echo "Fail: Some containers remain"; 
	docker ps -a; 
	false; 
fi
