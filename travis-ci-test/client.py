#!/usr/bin/env python3

from twisted.internet.protocol import Protocol, ClientFactory
from twisted.internet import reactor
import twisted.internet.error
import sys, pprint, time, threading

# for client: a translate function to be passed to the protocol class, to indicate what the expect in return

errorcode = 0
lock = threading.Lock()
connectCount = 0

class Echo(Protocol):
    def __init__(self, repeats = 10, data = "xxx", translationFunction = lambda x: x, delay = 0):
        self.lines = []
        self.repeats = repeats
        self.sendData = data
        self.translationFunction = translationFunction
        self.delay = delay
        self.counter = 0

    def dataReceived(self, data):
        self.lines += ["S: {}".format(data.decode("utf-8"))]
        reply = ""
        if self.counter >= self.repeats:
            reply = "quit\n"
        else:
            reply = self.sendData + "\n"
        self.lines += ["C: {}".format(reply)]
        self.transport.write(reply.encode("utf-8"))
        self.counter += 1
        time.sleep(self.delay)

    def connectionLost(self, reason):
        #self.lines += ["?: {}".format(reason)]
        self.lines += ["?: Done"]
        if "weird" == self.verifyOutcome():
            global errorcode
            errorcode = 1

    def verifyOutcome(self):
        successexpected = ['S: Hello, this is an echo service!\n']
        successexpected += ['C: '+self.sendData+'\n', 'S: '+self.translationFunction(self.sendData+'\n')] * self.repeats
        successexpected += ['C: quit\n', 'S: Goodbye.\n'+self.translationFunction('quit\n'), 'C: quit\n', '?: Done']

        fullexpected = ['S: dockerports says no :(\r\n', 'C: xxx\n', '?: Done']

        if successexpected == self.lines:
            return "success"
        if fullexpected == self.lines:
            return "full"
        else:
            print("Got weird lines ::::")
            pprint.pprint(self.lines)
            print("--> Expected ::::")
            pprint.pprint(successexpected)
            return "weird"
        
class UpperEcho(Echo):
    def __init__(self, repeats = 10, data = "xxx", delay = 0):
        super().__init__(repeats, data, lambda x: x.upper(), delay)
            

class EchoClientFactory(ClientFactory):
    def __init__(self, protocol = None):
        self.protocol = protocol

    def startedConnecting(self, connector):
        global connectCount, lock
        with lock:
            connectCount += 1
        print('Started to connect.%d' % connectCount)

    def buildProtocol(self, addr):
        global connectCount
        print('Connected.%d' % connectCount)
        return self.protocol()

    def clientConnectionLost(self, connector, reason):
        global connectCount, lock
        with lock:
            connectCount -= 1
            print('Lost connection.%d' % connectCount)
            #print('Lost connection.%d Reason:' % connectCount, reason)
            if connectCount == 0:
                reactor.stop()

    def clientConnectionFailed(self, connector, reason):
        global connectCount, lock
        with lock:
            connectCount -= 1
            print('Failed connection.%d' % connectCount)
            #print('Failed connection.%d Reason:' % connectCount, reason)
            global errorcode
            errorcode = 1
            if connectCount == 0:
                reactor.stop()

ecf = EchoClientFactory(Echo)
uecf = EchoClientFactory(UpperEcho)

for x in range(10):
    reactor.connectTCP("localhost", 2222, ecf)
    reactor.connectTCP("localhost", 2223, uecf)
reactor.run()

sys.exit(errorcode)
