#!/usr/bin/env python3

from twisted.protocols.portforward import *
from twisted.internet import reactor

import time, socket
import configparser, glob
import random, string
import docker

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

        for imagesection in [n for n in config.sections() if n != "global"]:
            outerport = int(config[imagesection]["outerport"])
            innerport = int(config[imagesection]["innerport"])
            containername = config[imagesection]["containername"]
            self.registerProxy(imagesection, containername, outerport, innerport,
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

    def registerProxy(self, imagename, containername, outerport, innerport, limit, reuse):
        self.imageParams[imagename] = {
            "imagename": imagename,
            "containername": containername,
            "outerport": outerport,
            "innerport": innerport,
            "dockeropts": { # FIXME: must be configurable
                #"remove": True,
                # cannot use detach and remove together
                # See https://github.com/docker/docker-py/issues/1477
                "detach": True, 
                #"auto_remove": True, 
                "ports": {
                    innerport: None,
                }
            },
            "limit": limit,
            "reuse": reuse
        }

    def create(self, imagename):
        outerport = self.imageParams[imagename]["outerport"]
        innerport = self.imageParams[imagename]["innerport"]
        containername = self.imageParams[imagename]["containername"]
        imagelimit = self.imageParams[imagename]["limit"]
        reuse = self.imageParams[imagename]["reuse"]
        dockeropts = self.imageParams[imagename]["dockeropts"]

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
            instance = DockerInstance(imagename, containername, dockeropts)
            instance.start()

        if imagename not in self.instancesByName:
            self.instancesByName[imagename] = []

        # in case of reuse, the list will have duplicates
        self.instancesByName[imagename] += [instance]

        return instance

    def destroy(self, instance):
        imagename = instance.getImageName()
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
    def __init__(self, imagename, containername, dockeropts):
        # TODO FIXME: keep a cleaner datastructure in DockerInstance, instead of a bunch of single variables
        self._imagename = imagename
        self._containername = containername
        self._dockeroptions = dockeropts
        self._instance = None

    def getDockerOptions(self):
        return self._dockeroptions

    def getContainerName(self):
        return self._containername

    def getMiddlePort(self):
        try:
            return int(list(self._instance.attrs["NetworkSettings"]["Ports"].values())[0][0]["HostPort"])
        except Exception as e:
            logger.warn("Failed to get port information from {}: {}".format(self.getInstanceID(), e))
        return None

    def getImageName(self):
        return self._imagename

    def getInstanceID(self):
        try:
            return self._instance.id
        except Exception as e:
            logger.warn("Failed to get instanceid: {}".format(e))
        return "None"

    def start(self):
        # get docker client
        client = docker.from_env()

        # start instance
        try:
            logger.debug("Starting instance {} of container {}".format(self.getImageName(), self.getContainerName()))
            clientres = client.containers.run(self.getContainerName(), **self.getDockerOptions())
            self._instance = client.containers.get(clientres.id)
            logger.debug("Done starting instance {} of container {}".format(self.getImageName(), self.getContainerName()))
        except Exception as e:
            logger.debug("Failed to start instance {} of container {}: {}".format(self.getImageName(), self.getContainerName(), e))
            self.stop()
            return False

        # wait until innerport is available
        logger.debug("Started instance on middleport {} with ID {}".format(self.getMiddlePort(), self.getInstanceID()))
        if self.__waitForOpenPort():
            logger.debug("Started instance on middleport {} with ID {} has open port".format(self.getMiddlePort(), self.getInstanceID()))
            return True
        else:
            logger.debug("Started instance on middleport {} with ID {} has closed port".format(self.getMiddlePort(), self.getInstanceID()))
            self.stop()
            return False

    def stop(self):
        mp = self.getMiddlePort()
        cid = self.getInstanceID()
        logger.debug("Killing and removing {} (middleport {})".format(cid, mp))
        try:
            self._instance.remove(force=True)
        except Exception as e:
            logger.warn("Failed to remove instance for middleport {}, id {}".format(mp, cid))
            return False
        return True

    def __isPortOpen(self, readtimeout=0.1):
        s = socket.socket()
        ret = False
        logger.debug("Checking whether port {} is open...".format(self.getMiddlePort()))
        if self.getMiddlePort() == None:
            time.sleep(readtimeout)
        else:
            try:
                s.connect(("0.0.0.0", self.getMiddlePort()))
                # just connecting is not enough, we should try to read and get at least 1 byte back
                # since the daemon in the container might not have started accepting connections yet, while docker-proxy does
                s.settimeout(readtimeout)
                data = s.recv(1)
                ret = len(data) > 0
            except socket.error:
                ret = False

        logger.debug("result = ".format(ret))
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
        if self.dockerinstance == None:
            self.transport.write(bytearray("Maximum connection-count reached. Try again later.\r\n", "utf-8"))
            self.transport.loseConnection()
        else:
            logger.info("[Session {}] Incoming connection for image {} from {} at {}".format(self.sessionID, self.dockerinstance.getImageName(),
                self.transport.getPeer(), self.sessionStart))
            self.reactor.connectTCP("0.0.0.0", self.dockerinstance.getMiddlePort(), client)

    def connectionLost(self, reason):
        imagename = "<none>"
        if self.dockerinstance != None:
            global globalDockerPorts
            globalDockerPorts.destroy(self.dockerinstance)
            imagename = self.dockerinstance.getImageName()
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


