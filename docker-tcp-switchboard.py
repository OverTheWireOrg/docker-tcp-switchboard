#!/usr/bin/env python3

from twisted.protocols.portforward import *
from twisted.internet import reactor

import time, socket, subprocess
import configparser, glob
import random, string

import logging
logger = logging.getLogger("docker-tcp-switchboard")

# this is a global object that keeps track of the free ports
# when requested, it allocated a new docker instance and returns it

class DockerPorts():
    def __init__(self):
        self.instancesByName = dict()
        self.imageParams = dict()

    def readConfig(self, fn):
        # read the configfile.
        config = configparser.ConfigParser()
        logger.debug("Reading configfile from {}".format(fn))
        config.read(fn)

        # set log file
        if "global" in config.sections() and "logfile" in config["global"]:
            #global logger
            handler = logging.FileHandler(config["global"]["logfile"])
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        # set log level
        if "global" in config.sections() and "loglevel" in config["global"]:
            #global logger
            logger.setLevel(logging.getLevelName(config["global"]["loglevel"]))

        # if there is a configdir directory, reread everything
        if "global" in config.sections() and "splitconfigfiles" in config["global"]:
            fnlist = [fn] + [f for f in glob.glob(config["global"]["splitconfigfiles"])]
            logger.debug("Detected configdir directive. Reading configfiles from {}".format(fnlist))
            config = configparser.ConfigParser()
            config.read(fnlist)

        if len(config.sections()) == 0 or (len(config.sections()) == 1 and "global" in config.sections()):
            logger.error("invalid configfile. No docker images")
            sys.exit(1)

        prefix = (config["global"]["dockerparamsprefix"] + " ") if "dockerparamsprefix" in config["global"] else ""

        for imagesection in [n for n in config.sections() if n != "global"]:
            outerport = int(config[imagesection]["outerport"])
            self.registerProxy(imagesection, outerport,
                prefix + config[imagesection]["dockerparams"],
                self._parseInt(config[imagesection]["limit"]) if "limit" in config[imagesection] else 0,
                self._parseTruthy(config[imagesection]["reuse"]) if "reuse" in config[imagesection] else False
                )

        return dict([(name, self.imageParams[name]["outerport"]) for name in self.imageParams.keys()])

    def _parseInt(self, x):
        return int(x)

    def _parseTruthy(self, x):
        if x.lower() in ["0", "false", "no"]:
            return False
        if x.lower() in ["1", "true", "yes"]:
            return True

        raise "Unknown truthy value {}".format(x)

    def registerProxy(self, imagename, outerport, params, limit, reuse):
        self.imageParams[imagename] = {
            "imagename": imagename,
            "outerport": outerport,
            "params": params,
            "limit": limit,
            "reuse": reuse
        }

    def create(self, imagename):
        outerport = self.imageParams[imagename]["outerport"]
        imagelimit = self.imageParams[imagename]["limit"]
        reuse = self.imageParams[imagename]["reuse"]
        params = self.imageParams[imagename]["params"]

        icount = 0
        if imagename in self.instancesByName:
            icount = len(self.instancesByName[imagename])

        if imagelimit > 0 and icount >= imagelimit:
            logger.warn("Reached max count of {} (currently {}) for image {}".format(imagelimit, icount, imagename))
            return None

        instance = None

        if reuse and icount > 0:
            logger.debug("Reusing existing instance for image {}".format(imagename))
            instance = self.instancesByName[imagename][0]
        else:
            instance = DockerInstance(imagename, params, reuse)
            instance.start()

        if imagename not in self.instancesByName:
            self.instancesByName[imagename] = []

        # in case of reuse, the list will have duplicates
        self.instancesByName[imagename] += [instance]

        return instance

    def destroy(self, instance):
        imagename = instance.imagename
        reuse = self.imageParams[imagename]["reuse"]

        # in case of reuse, the list will have duplicates, but remove() does not care
        self.instancesByName[imagename].remove(instance)

        # stop the instance if there is no reuse, or if this is the last instance for a reused image
        if not reuse or len(self.instancesByName[imagename]) == 0:
            instance.stop()


# this class represents a single docker instance listening on a certain middleport.
# The middleport is managed by the DockerPorts global object
# After the docker container is started, we wait until the middleport becomes reachable
# before returning
class DockerInstance():
    def __init__(self, imagename, dockerparams, reuse):
        # TODO FIXME: keep a cleaner datastructure in DockerInstance, instead of a bunch of single variables
        self.dockerparams = dockerparams
        self.imagename = imagename
        self.reuse = reuse
        self.middleport = None
        self.instanceid = None

    def start(self):
        cmd = "docker run --detach {}".format(self.dockerparams)
        (rc, out) = subprocess.getstatusoutput(cmd.format(0))
        if rc != 0:
            logger.warn("Failed to start instance")
            logger.warn("rc={}, out={}".format(rc, out))
            return None

        self.instanceid = out.strip()
        cmd = "docker port {}".format(self.instanceid)
        (rc, out) = subprocess.getstatusoutput(cmd)
        if rc != 0:
            logger.warn("Failed to get port information from {}".format(self.instanceid))
            logger.warn("rc={}, out={}".format(rc, out))
            return None

        try:
            # try to parse something like: "22/tcp -> 0.0.0.0:12345" to extract 12345
            # FIXME BUG: this parsing doesn't take into account that multiple ports may be forwarded
            # See Issue #1 at https://github.com/OverTheWireOrg/docker-tcp-switchboard/issues/1
            self.middleport = int(out.strip().split(" ")[2].split(":")[1])
        except:
            logger.warn("Failed to parse port from returned data for instanceid {}: {}".format(self.instanceid, out))
            self.stop()
            return None

        logger.debug("Started instance on middleport {} with ID {}".format(self.middleport, self.instanceid))
        if self.__waitForOpenPort():
            return self.instanceid
        else:
            self.stop()
            return None

    def stop(self):
        logger.debug("Killing and removing {} (middleport {})".format(self.instanceid, self.middleport))
        (rc, _) = subprocess.getstatusoutput(("docker kill {}".format(self.instanceid)))
        if rc != 0:
            logger.warn("Failed to stop instance for middleport {}, id {}".format(self.middleport, self.instanceid))
            return False
        (rc, _) = subprocess.getstatusoutput(("docker rm {}".format(self.instanceid)))
        if rc != 0:
            logger.warn("Failed to remove instance for middleport {}, id {}".format(self.middleport, self.instanceid))
            return False
        return True

    def __isPortOpen(self, readtimeout=0.1):
        s = socket.socket()
        ret = False
        try:
            s.connect(("0.0.0.0", self.middleport))
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
        
class LoggingProxyClient(ProxyClient):
    def dataReceived(self, data):
        payloadlen = len(data)
        self.factory.server.upBytes += payloadlen
        self.peer.transport.write(data)

class LoggingProxyClientFactory(ProxyClientFactory):
    protocol = LoggingProxyClient

class DockerProxyServer(ProxyServer):
    clientProtocolFactory = LoggingProxyClientFactory
    reactor = None

    def __init__(self):
        super().__init__()
        self.downBytes = 0
        self.upBytes = 0
        self.sessionID = "".join([random.choice(string.ascii_letters) for _ in range(16)])
        self.sessionStart = time.time()

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
        global globalDockerPorts
        self.dockerinstance = globalDockerPorts.create(self.factory.outerport)
        logger.info("[Session {}] Incoming connection for image {} from {} at {}".format(self.sessionID, self.dockerinstance.imagename,
                self.transport.getPeer(), self.sessionStart))
        if self.dockerinstance == None:
            self.transport.write(bytearray("Maximum connection-count reached. Try again later.\r\n", "utf-8"))
            self.transport.loseConnection()
        else:
            self.reactor.connectTCP("0.0.0.0", self.dockerinstance.middleport, client)

    def connectionLost(self, reason):
        imagename = "<none>"
        if self.dockerinstance != None:
            global globalDockerPorts
            globalDockerPorts.destroy(self.dockerinstance)
            imagename = self.dockerinstance.imagename
        self.dockerinstance = None
        super().connectionLost(reason)
        timenow = time.time()
        logger.info("[Session {}] server disconnected session for image {} from {} (start={}, end={}, duration={}, upBytes={}, downBytes={}, totalBytes={})".format(
                self.sessionID, imagename, self.transport.getPeer(),
                self.sessionStart, timenow, timenow-self.sessionStart,
                self.upBytes, self.downBytes, self.upBytes + self.downBytes))

    def dataReceived(self, data):
        payloadlen = len(data)
        self.downBytes += payloadlen
        self.peer.transport.write(data)


class DockerProxyFactory(ProxyFactory):
    protocol = DockerProxyServer

    def __init__(self, outerport):
        self.outerport = outerport


if __name__ == "__main__":
    import sys

    globalDockerPorts = DockerPorts()
    portsAndNames = globalDockerPorts.readConfig(sys.argv[1] if len(sys.argv) > 1 else '/etc/docker-tcp-switchboard.conf')

    for (name, outerport) in portsAndNames.items():
        logger.debug("Listening on port {}".format(outerport))
        reactor.listenTCP(outerport, DockerProxyFactory(name))
    reactor.run()


