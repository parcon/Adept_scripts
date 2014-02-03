#!/usr/bin/python

from telnetlib import Telnet
import time
import sys
import os

Robot="10.0.202.129"
if len(sys.argv) > 1:
  Robot=sys.argv[1]

sock = Telnet()

EMPW="adept"
EMPort=7171


try:
  sock.open(Robot, EMPort)
  print "Waiting for password prompt at %s\n" %(Robot)
  buf = sock.read_until("Enter password:\r\n", 5)
  print "Entering password\n"
  sock.write("%s\n" %(EMPW))
except:
  print "Failed to connect"
  sys.exit()

i=1

while ( i <= 10000  ):
  print "loop %s" %(i)
  buf = sock.read_lazy()
  sock.write("mapObjectUpdate goal 100 200 0 \"test3\" ICON \"Goal1\"\n");
  print "waiting for map change"
  buf = sock.read_until("Map changed\r\n", 20);
  print "buf is %s" %(buf)
  #os.system("free")
  #time.sleep(.001)
  i+=1
  time.sleep(1)

#sock.close()
print "done"

