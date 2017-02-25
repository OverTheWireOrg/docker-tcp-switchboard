#!/usr/bin/env python

# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor
import sys

### Protocol Implementation

makeUpper = False

# This is just about the simplest possible protocol
class Echo(Protocol):
    def connectionMade(self):
        self.transport.write("Hello, this is an echo service!\n")

    def dataReceived(self, data):
        if data.lower().startswith("quit"):
            self.transport.write("Goodbye.\n".encode("utf-8"))
            self.transport.loseConnection()
        global makeUpper
        if makeUpper:
            data = data.upper()
        self.transport.write(data)


def main():
    f = Factory()
    f.protocol = Echo
    reactor.listenTCP(8000, f)
    reactor.run()

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == "upper":
        makeUpper = True
    main()
