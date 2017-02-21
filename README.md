This is how it should work:

For an incoming connection to a certain port X :
	allocate a new port Y for docker to listen to in a specific range
		if there are no free ports in the range, wait up to 5 seconds before giving up
	start docker and connect SSH to port Y
	forward data between port X and Y
		if the datarate or volume exceeds some treshold, slow down or terminate the connection

When the connection terminates (port X forwarded to port Y):
	clean up the docker environment
	free port Y
