#!/bin/bash -ex

# installing some packages before docker install maybe messes things up
sudo apt-get update
sudo apt-get install -y python3-pip
sudo pip3 install -r ../requirements.txt

# install latest docker if it doesn't already exist
if [ ! -e /etc/init.d/docker ]; then
    curl -sSL https://get.docker.com/ | sudo sh
fi
# start docker, and wait until it's likely up
(sudo /etc/init.d/docker start  && sleep 3 ) || true

# give 'everyone' access...
sudo chmod o+rw /var/run/docker.sock

# build echoserv and upperserv
docker build -t echoserv -f testimages/Dockerfile.echoserv testimages
docker build -t upperserv -f testimages/Dockerfile.upperserv testimages
sleep 2


