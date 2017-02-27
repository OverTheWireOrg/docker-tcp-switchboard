#!/usr/bin/env python3

from twisted.protocols.portforward import *
from twisted.internet import reactor

import time, socket, subprocess

# this is a global object that keeps track of the free ports
# when requested, it allocated a new docker instance and returns it
class DockerPorts():
    def __init__(self, baseport, amount, dockerparams):
        print("Creating DockerPorts with {} instances starting at baseport {}, using \"docker run -detach {}\"".format(amount, baseport, dockerparams))
        self.dockerparams = dockerparams
        self.ports = dict([(port, None) for port in range(baseport, baseport + amount)])

    def create(self):
        freeports = [p for p,v in self.ports.items() if v == None]
        if len(freeports) > 0:
            p = freeports[0]
            instance = DockerInstance(p, self.dockerparams)
            self.ports[p] = instance
            instance.start()
            return self.ports[p]
        return None

    def destroy(self, instance):
        instance.stop()
        p = instance.port
        self.ports[p] = None


# this class represents a single docker instance listening on the given port.
# The port is managed by the DockerPorts global object
# After the docker container is started, we wait until the port becomes reachable
# before returning
class DockerInstance():
    # wait until booted
    def __init__(self, port, dockerparams):
        self.dockerparams = dockerparams
        self.port = port
        self.instanceid = None

    def start(self):
        cmd = "docker run --detach {}".format(self.dockerparams)
        (rc, out) = subprocess.getstatusoutput(cmd.format(self.port))
        if rc != 0:
            print("Failed to start instance for port {}".format(self.port))
            print("rc={}, out={}".format(rc, out))
            return None

        self.instanceid = out.strip()
        print("Started instance on port {} with ID {}".format(self.port, self.instanceid))
        if self.__waitForOpenPort():
            return self.instanceid
        else:
            self.stop()
            return None

    def stop(self):
        print("Killing and removing {} (port {})".format(self.instanceid, self.port))
        (rc, _) = subprocess.getstatusoutput(("docker kill {}".format(self.instanceid)))
        if rc != 0:
            print("Failed to stop instance for port {}, id {}".format(self.port, self.instanceid))
            return False
        (rc, _) = subprocess.getstatusoutput(("docker rm {}".format(self.instanceid)))
        if rc != 0:
            print("Failed to remove instance for port {}, id {}".format(self.port, self.instanceid))
            return False
        return True

    def __isPortOpen(self, readtimeout=0.1):
        s = socket.socket()
        ret = False
        try:
            s.connect(("0.0.0.0", self.port))
            # just connecting is not enough, we should try to read and get at least 1 byte back
            # since the daemon in the container might not have started accepting connections yet, while docker-proxy does
            s.settimeout(readtimeout)
            data = s.recv(1)
            ret = len(data) > 0
        except socket.error:
            ret = False

        s.close()
        return ret

    def __waitForOpenPort(self, timeout=5, step=0.1):
        started = time.time()

        while started + timeout >= time.time():
            if self.__isPortOpen():
                return True
            time.sleep(step)
        return False
        

class DockerProxyServer(ProxyServer):
    clientProtocolFactory = ProxyClientFactory
    reactor = None

    # This is a reimplementation, except that we want to specify host and port...
    def connectionMade(self): 
        # Don't read anything from the connecting client until we have
        # somewhere to send it to.
        self.transport.pauseProducing()

        client = self.clientProtocolFactory()
        client.setServer(self)

        if self.reactor is None:
            from twisted.internet import reactor
            self.reactor = reactor
        self.dockerinstance = self.factory.dports.create()
        if self.dockerinstance == None:
            self.transport.write(bytearray("dockerports says no :(\r\n", "utf-8"))
            self.transport.loseConnection()
        else:
            self.reactor.connectTCP("0.0.0.0", self.dockerinstance.port, client)

    def connectionLost(self, reason):
        if self.dockerinstance != None:
            self.factory.dports.destroy(self.dockerinstance)
        self.dockerinstance = None
        super().connectionLost(reason)

class DockerProxyFactory(ProxyFactory):
    protocol = DockerProxyServer

    def __init__(self, dports):
        self.dports = dports

def readConfig(fn):
    import configparser, glob
    # read the configfile.
    config = configparser.ConfigParser()
    print("Reading configfile from {}".format(fn))
    config.read(fn)

    # if there is a configdir directory, reread everything
    if "global" in config.sections() and "splitconfigfiles" in config["global"]:
        fnlist = [fn] + [f for f in glob.glob(config["global"]["splitconfigfiles"])]
        print("Detected configdir directive. Reading configfiles from {}".format(fnlist))
        config = configparser.ConfigParser()
        config.read(fnlist)

    return config


if __name__ == "__main__":
    import sys

    config = readConfig(sys.argv[1] if len(sys.argv) > 1 else '/etc/docker-tcp-switchboard.ini')

    if len(config.sections()) == 0 or (len(config.sections()) == 1 and "global" in config.sections()):
        print("invalid configfile. No docker images")
        sys.exit(1)

    for imagesection in [n for n in config.sections() if n != "global"]:
        dports = DockerPorts(
            baseport=int(config[imagesection]["baseport"]),
            amount=int(config[imagesection]["amount"]),
            dockerparams=config[imagesection]["dockerparams"]
            )

        listenport = int(config[imagesection]["proxyport"])
        print("Listening on port {}".format(listenport))
        reactor.listenTCP(listenport, DockerProxyFactory(dports))
    reactor.run()


