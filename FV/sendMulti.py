#!/usr/bin/python

from telnetlib import Telnet
import time
import sys
import os

sock = Telnet()

EMAddress="10.0.202.97"
EMPW="adept"
EMPort=7171

print "Attempting to synchronize clock with EM %s\n" %(EMAddress)

# Telnet to the EM ARCL port

try:
  sock.open(EMAddress, EMPort)
  print "Waiting for password prompt\n"
  buf = sock.read_until("Enter password:\r\n", 5)
  print "Entering password\n"
  sock.write("%s\n" %(EMPW))
  #sock.write("queuePickupDropoff PAVN-A02_1 FWIP-A02_W1-R1-C3\n")
  #time.sleep(10)
  #sock.write("quit\n")
  #sock.close()
  #print "Waiting for end of command listing\n"
  #sock.read_until("End of commands\r\n", 5)
except:
  print "Failed to connect"
  sys.exit()

#sock.close()
#sys.exit()
i=1

while ( i <= 1500  ):
  print "loop %s" %(i)
  sock.open(EMAddress, EMPort)
  #buf = sock.read_until("Enter password:\r\n", 5)
  #sock.write("%s\n" %(EMPW))
  sock.write("adept\nqueuePickupDropoff goal3 goal3\nquit\n")
  sock.close();

  #sock.write("queuePickupDropoff PAVN-A02_1 FWIP-A02_W1-R1-C3\n")
  #sock.write("multirobotsizeclear\n")
  #time.sleep(.001)
  i+=1

#sock.close()
print "done"

