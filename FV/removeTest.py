#!/usr/bin/python

from telnetlib import Telnet
import time
import sys
import os

sock = Telnet()
rsock = Telnet()

EMAddress="10.0.202.97"
EMPW="adept"
EMPort=7171

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

while ( i <= 10000  ):
  print "loop %s" %(i)
  print "starting ARAM"
  os.system("sng_aramStart")
  time.sleep(20)
  try:
    sock.write("\n");
  except:
    print "EM write failed"
    i = 10000
  print "connecting to robot"
  rsock.open("10.0.202.103", EMPort)
  print "Waiting for password prompt\n"
  buf = rsock.read_until("Enter password:\r\n", 5)
  print "Entering password\n"
  rsock.write("%s\n" %(EMPW))
  rsock.write("applicationfaultset -10020 s l false false\n");
  rsock.close()
  time.sleep(5)
  print "stopping ARAM"
  os.system("sng_aramStop")
  time.sleep(5)
  i+=1
  try:
    sock.write("\n");
  except:
    print "EM write failed"
    i = 10000

#sock.close()
print "done"

