# Docker TCP Switchboard

[![Build Status](https://api.travis-ci.org/OverTheWireOrg/docker-tcp-switchboard.svg?branch=master)](https://travis-ci.org/OverTheWireOrg/docker-tcp-switchboard)

This project is part of [OverTheWire]'s infrastructure and used to provide
players of OverTheWire wargames with a fresh Docker container each time they
log into SSH.

At this point in time, docker-tcp-switchboard only really supports SSH instead
of arbitrary TCP connections, since it makes a connection to the backend and
expects to receive a banner in order to determine that the Docker containers
has started up successfully.

Some features, current and future:

* Allocate a new Docker instance per connection
* Ability to reuse Docker instances for multiple connections.
* Ability to limit the amount of running containers to avoid resource exhaustion.
* [future] Ability to set quota (time-limit, network traffic limit) per container.
* [future] Ability to delay network communication for incoming connections, to
  prevent that a flood of incoming connections spawns of a flood of containers
  that overwhelm the Docker host.

## Quickstart
Attention: This is just a quick-start and not suitable for production.

Prerequisites:
- A docker image of your choice is needed
  - The image requires a running ssh-server and a known user/password (See `\example\Dockerfile` for a simple example)
- root or root-privileges are needed for setup

````bash
# start in your home directory
cd ~
# clone this repository
git clone https://github.com/OverTheWireOrg/docker-tcp-switchboard.git
# install and start docker. You'll be able to control docker without root
sudo apt-get -y install docker-ce
sudo service docker start
sudo usermod -a -G docker **yourusername**
# install requirements
cd /docker-tcp-switchboard
sudo apt install python3-pip
pip3 install -r requirements.txt
# setup logfile
touch /var/log/docker-tcp-switchboard.log
chmod a+w /var/log/docker-tcp-switchboard.log
# create the configuration file
vi /etc/docker-tcp-switchboard.conf #paste your configuration file here (see below)
# start docker-tcp-switchboard. It'll run in the foreground.
python3 docker-tcp-switchboard.py
````
Done! Now connect to your `outerport` to start a fresh container.


## Example configuration file
````ini
[global]
logfile = /var/log/docker-tcp-switchboard.log
loglevel = DEBUG

[profile:firstcontainer]
innerport = 22
outerport = 32768
container = imagename
limit = 10
reuse = false

[profile:differentcontainer]
innerport = 22
outerport = 32769
container = differentimagename
limit = 5
reuse = false

[dockeroptions:differentcontainer]
ports={"8808/tcp":null}
volumes={"/home/ubuntu/mountthisfolder/": {"bind": "/mnd/folderincointainer/", "mode": "rw"}}

````

### misc
- See logfile for debugging (`tail -f /var/log/docker-tcp-switchboard.log`)
- To auto-disconnect when idle, use SSHD config options "ClientAliveInterval" and "ServerAliveCountMax"
- Remember to unblock "outerport" in your firewall
- See [Docker SDK for Python](https://docker-py.readthedocs.io/en/stable/containers.html) for troubleshooting and available dockeroptions




[OverTheWire]: http://overthewire.org
