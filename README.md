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

## Usage

TODO

## Example configuration file

TODO


[OverTheWire]: http://overthewire.org
