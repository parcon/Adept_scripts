#!/usr/bin/python


#Replay file format:
#	pickup goalA goalB
#	pickupDropoff goalC goalE


#CIM flow:
#- start log
#- read in commands
#- connect to arcl
#- send command, put expected response in list
#- if connection lost, reconnect, but don't lose place in line
#- log connection lost
#- when command is completed, log status, id #, command, remove #from list

#CIM command class:
#- id number (rollover)
#- command
#- expected response type?
#- trap for success, failure messages
#- status of command - NOTYETSENT, SENT_WAITING_COMPLETION, #COMPLETED


#Handler flow:




# To Do
# - need to add read timeout
# - need to check connection status

from telnetlib import Telnet
import datetime as dt
import time
import socket
import sys
import select
import random

oldSockCount = 0
logTime = 0

# variable to use to signal when the script should exit
runCim = 1

# how many loops should be run of the replay list
numLoops = 5

# TCP port to listen to.  Use for controlling the script
cliListenPort = 1000

# Timeout for select statement
selectTimeout = .01

# interval between jobs, in seconds
jobInterval = 30

# filename for replay list
replayFile = "replayList.txt"

# file for logging
logFile = "cimLog.txt"

pickDropCycleTime = 45
socUpdateInterval = 2.0 # once every 5 minutes
maxRunTime = 10 * 3600 # runtime number of seconds, so multiply by 3600
maxChargeTime = 3 * 3600 # charge time in seconds, so multiply by 3600
dockedSOCIncrease = ( socUpdateInterval / maxChargeTime ) * 100 # SOC increase per socUpdateInterval when docked.  Full charge from 0-100 in 4 hours
undockedSOCDecrease = ( socUpdateInterval / maxRunTime ) * 100 # SOC decrease per socUpdateInterval when undocked

class SIM:
  def __init__(self):
    self.sockList = [];
    self.robotList = dict();
    self.numRobots = 0;
    self.startTime = time.time()
    self.dockedTime = 0

  def addRobot(self, host):
        self.numRobots+=1
        print "Adding robot %s %s" % (self.numRobots, host)
        self.robotList[host] = robot(host, self.numRobots)
        self.sockList.append(self.robotList[host].sock)

  def checkRobots(self):
        #print "Check robots"
        for robot in self.robotList:
          #print "Checking robot %s" %(robot)
          if ( self.robotList[robot].pauseState == "Paused" ) and ( time.time() - self.robotList[robot].pauseStartTime > pickDropCycleTime ):
            self.robotList[robot].sock.send("modeUnlock\n")
            self.robotList[robot].sock.send("pauseTaskCancel\n")
            self.robotList[robot].sock.send("multirobotsizeclear\n")
            self.robotList[robot].pauseState = ""

          if ( time.time() - self.robotList[robot].socUpdateTime > socUpdateInterval ):
            if ( self.robotList[robot].docked == 1 ):
              self.robotList[robot].SOC += dockedSOCIncrease
              #print "Increase: %s Robot: %s %s" %(dockedSOCIncrease, robot, self.robotList[robot].SOC)
              if (self.robotList[robot].SOC > 100):
                self.robotList[robot].SOC = 100
            else:
              self.robotList[robot].SOC -= undockedSOCDecrease
              #print "Decrease: %s Robot: %s %s" %(undockedSOCDecrease, robot, self.robotList[robot].SOC)
              if (self.robotList[robot].SOC < 0):
                self.robotList[robot].SOC = 0
            self.robotList[robot].SOC = 100
            self.robotList[robot].sock.send("setStateOfCharge %2.2f\n" % (self.robotList[robot].SOC))
            self.robotList[robot].socUpdateTime = time.time()


def log(msg):
  timeStamp = time.asctime()
  print "%s %s" % (timeStamp, msg)
  sys.stdout.flush()

class robot:
  def __init__(self, ip, num):
        self.pauseState = ""
        self.pauseStartTime = 0
        print "Initializing new robot, %d" % (num)
        self.ip = ip
        self.id = num
        self.connected = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.openConnection()
        self.SOC = random.randint(40,100)
        self.socUpdateTime = 0
        self.docked = 0
        self.queryInProgressIssued = 0
        self.queryPendingIssued = 0
        self.queryIssued = 0
        self.inProgressCount = 0
        self.pendingCount = 0

  def openConnection(self):
        print "Opening connection to %s" %(self.ip)
        try:
          self.sock.connect((self.ip, 7171))
          self.sock.send("adept\n")
          self.sock.send("pausetaskcancel\n")
          self.sock.send("modeunlock\n")
          self.sock.send("multirobotsizeclear\n")
          self.sock.send("stop\n")
          # send a status query so that the docking state will be properly reflected
          self.sock.send("status\n")
          self.connected = 1
        except:
          print "Failed connecting to %s" % (self.ip)
          self.connected = 0


class CIM:

  def __init__(self):
	# The dict to use for tracking the outstanding jobs
	self.activeJobList = dict()
        self.longestCompletionTime = 0
        self.shortestCompletionTime = 0
        self.longestPendingTime = 0
        self.completionTimeTotal = 0
        self.pendingTimeTotal = 0
        self.averageCompletionTime = 0
        self.averagePendingTime = 0

        self.successfullSwaps = 0
        self.failedSwaps = 0
        self.swapIssued = 0
        self.swapsIssued = 0

	# number of jobs in replay list
	self.numReplayJobs = 0
        self.numSwaps = 0

	# list of replay jobs
	self.rawReplayJobList = []

        self.lastTime = 0;

	# counter for the current job in the replay list
        self.currentReplayJob = 0

	# number of active jobs
	self.numJobsActive = 0

        self.numJobsPending = 0

	# number of jobs issued regardless of completion status)
	self.numJobsIssued = 0

	# flag for whether the connection is established or not
	self.isConnected = 0

	# address for the EM
	#self.emAddress = "10.0.201.71"
	self.emAddress = "10.0.202.101"

	# ARCL port for EM
	self.emArclPort = 7171

        self.emArclPassword = "adept";

	# Socked for ARCL communications
	self.sock = Telnet()

	# time last job was sent
	self.lastJobTime = 0

	# number of job commands issued
	self.numIssuedJobs = 0

	# number of jobs successfully completed
	self.numSuccessfulJobs = 0

	# number of jobs cancelled by CIM
	self.numCIMCancelledJobs = 0

	# number of interrupted jobs
	self.numInterruptedJobs = 0

	# number of failed jobs
	self.numFailedJobs = 0

	# buffer for incoming socket data
	self.oldSockData = ""

  # compares two times in the format HH:MM:SS and returns the number of seconds between former and latter
  def getInterval(self, lastTime, curTime):
    FMT = "%H:%M:%S"
    return dt.datetime.strptime(curTime, FMT) - dt.datetime.strptime(lastTime, FMT)

  # Routine to read in the jobs from the file
  # Should they all be read in at once? Or only as needed?
  def readJobs(self, filename):
	self.numReplayJobs = 0
	# need to measure the time between jobs.
	# Just set to fixed value for now
	lastJobTimeStamp = 0
	REPLAYLIST = open(replayFile)
        f = open(replayFile)
        jobs = f.readlines()
        f.close()
        FMT = '%H:%M:%S'
        lastDrop = ""
        for job in jobs: 
          job = job.strip()
          (timestamp, type, pick, drop, pickpri, droppri, echo_string) = job.split(" ", 6)
          #interval = self.getInterval(self.lastTime, timestamp)
          #print "Interval is %s %s %s" %( timestamp, self.lastTime, interval)
          self.lastTime = timestamp
	  newJob = ReplayEntry()
	  self.numReplayJobs += 1
	  newJob.id = self.numReplayJobs
	  newJob.type = type
          currentTime = time.strptime(timestamp, FMT)
          if ( self.numReplayJobs == 1 ):
            newJob.interval = 0
          else:
            newJob.interval = time.mktime(currentTime) - time.mktime(lastJobTimeStamp)
            if ( newJob.interval < 0 ):
              newJob.interval += 24*60*60
          lastJobTimeStamp = currentTime
	  newJob.pickupGoal = pick
	  newJob.dropoffGoal = drop
          newJob.pickPri = pickpri
          newJob.dropPri = droppri
          newJob.echoStr = echo_string
          if ( pick == lastDrop ):
            self.numSwaps += 1
          lastDrop = drop
	  self.rawReplayJobList.append(newJob)
          log("Added job: %s %s %s %s %s" % (self.numReplayJobs, type, pick, drop, newJob.interval))
        log("Total jobs: %s Swaps: %s" % (self.numReplayJobs, self.numSwaps))

  # routine to clear old jobs.  This should be used at startup
  def clearQueue(self):
        # flush incoming buffer
        self.sock.read_lazy()
        log("Clearing EM queue")
        self.sock.write("queueshow\n")
        jobList = []
        queueIsClear = 0
        while ( queueIsClear == 0 ):
          buf = self.sock.read_until("\n", .1)
          buf = buf.rstrip()
          #log (buf)

          if ( buf == "EndQueueShow" ):
            queueIsClear = 1
            return

          ( first, rest ) = buf.split(" ", 1)
          if ( first == "QueueShow:" ):
            ( id, jobid, priority, status, rest ) = rest.split(" ", 4)
            if ( status == "Pending" or status == "InProgress" ):
              self.sock.write("queuecancel jobid %s\n" % (jobid))
              self.sock.write("queuecancel id %s\n" % (id))
              log("Clearing job %s" % (id))
              time.sleep(.1)
          elif ( first == "QueueRobot:" ):
            ( robot, rest) = rest.split(" ", 1)
            log("Cancelling robot %s" % (robot))
            self.sock.write("queuecancel robotname %s\n" % (robot))


          


  # Routine to establish the 
  def initializeConnection(self):
  	try:
	  log("Initialzing CIM connection to EM %s:%s" % (self.emAddress, self.emArclPort))
	  self.sock.open(self.emAddress, self.emArclPort)
	  self.sock.read_until("Enter password:\r\n", 5)
	  self.sock.write("%s\n" % self.emArclPassword)
	  self.sock.read_until("End of commands\r\n")
          log ("EM connection initialized")

	except:
	  print "CIM connection failed - closing"
	  self.sock.close()

  # Routine to randomly query
  # Should this use a time interval?
  def queryCommand(self):
	print "query"

  # Routine to randomly cancel a job
  # Should this use a time rinterval?  Or a percentage of jobs?
  def cancelJob(self):
	print "cancel"

  # Any other random things that should happen?

  # Routine to send the next job
  def sendJob(self,job):
	log("Starting job %s %s %s" % (job.type, job.pickupGoal, job.dropoffGoal))
	self.sock.write("%s %s %s %s %s %s\n" % (job.type, job.pickupGoal, job.dropoffGoal, job.pickPri, job.dropPri, job.echoStr))
	self.lastJobTime = time.time()
	self.numJobsActive += 1
        self.numJobsIssued += 1
        self.numJobsPending += 1
        newJob = CIM_Command()
        newJob.pickupGoal = job.pickupGoal
        newJob.dropoffGoal = job.dropoffGoal
	newJob.startTime = time.time()
        newJob.status = "Pending"
        newJob.id = job.echoStr
	self.activeJobList[job.echoStr] = newJob

  # Routine for parsing the response
  def parseResponse(self,data):
	# read line.  Things we care about:
	#   		When a job is accepted and assigned a jobID
	#		When a job is assigned to a robot
	#		When a job is completed
	#		When a job fails
	#		When a job is interrupted
	#
	#  Responses of interest:
	#  		QueueUpdate
	#  		RobotUpdate
	# 
	
	lines = data.split("\n")
	for line in lines:
		line = line.rstrip()
                if ( line == "" or line == "\n" ):
                  continue

		# remove trailing CR/LF
		line = line.rstrip()

                # check for queueupdate
                #log("line is %s" % (line))
                ( type, rest ) = line.split(" ", 1)

                if ( type == "queuepickupdropoff" ):
                  #log (rest)
                  toks = rest.split(" ")
                  #job_id = toks[12]
                  job_id = toks[14]
                  # add the ID to the last job that was queued
                  #self.activeJobList[job_id] = self.activeJobList['LATEST']
                  #self.activeJobList[job_id].id = job_id
                  self.activeJobList[job_id].pickupID = toks[10]
                  self.activeJobList[job_id].dropoffID = toks[12]
                  #del self.activeJobList['LATEST']


                if ( type == "QueueUpdate:" ):
                  #log (rest)
                  ( id, jobid, priority, status, substatus, type, goal, robot, jdate, jtime, ignore1, ignore2 ) = rest.split(" ", 11)

                  # look through the list of jobs and see if the status update applies
		  for job in ( self.activeJobList.keys() ):
                        #log("Checking job %s %s" %(job, self.activeJobList[job].id))
                        if ( job == jobid and id == self.activeJobList[job].pickupID ):
                          #log("Job matches1, checking status")
                          self.activeJobList[job].pickupStatus = status
                          self.activeJobList[job].robotName = robot
                        elif ( job == jobid and id == self.activeJobList[job].dropoffID ):
                          #log("Job matches1, checking status")
                          self.activeJobList[job].dropoffStatus = status
                          self.activeJobList[job].robotName = robot

                        if ( ( self.activeJobList[job].pickupStatus == "InProgress" and 
                               self.activeJobList[job].status == "Pending" ) or
                             ( self.activeJobList[job].dropoffStatus == "InProgress" and
                               self.activeJobList[job].status == "Pending" )):
                          self.numJobsPending -= 1
                          self.activeJobList[job].status = "InProgress"
                          self.activeJobList[job].pickupStartTime = time.time()

                        if ( self.activeJobList[job].dropoffStatus == "Completed" and
                            self.activeJobList[job].status == "InProgress" ):
                          self.activeJobList[job].endTime = time.time()
                          self.numSuccessfulJobs += 1
                          totalTime = time.time() - self.activeJobList[job].startTime
                          pendingTime = self.activeJobList[job].pickupStartTime - self.activeJobList[job].startTime
                          if ( totalTime > self.longestCompletionTime ):
                            self.longestCompletionTime = totalTime
                          if ( self.shortestCompletionTime == 0 or totalTime < self.shortestCompletionTime ):
                            self.shortestCompletionTime = totalTime
                          if ( pendingTime > self.longestPendingTime ):
                            self.longestPendingTime = pendingTime
                          self.completionTimeTotal += totalTime
                          self.pendingTimeTotal += pendingTime
                          self.averageCompletionTime = self.completionTimeTotal / self.numSuccessfulJobs
                          self.averagePendingTime = self.pendingTimeTotal / self.numSuccessfulJobs
                          log("Job %s completed in %6.0f sec total %6.0f sec pending %6.0f sec operating" % (id, totalTime, pendingTime, totalTime - pendingTime))
                          del self.activeJobList[job]
                          self.numJobsActive -= 1
                          return

                        if ( job == jobid and ( status == "Failed" or status == "Interrupted" ) ):
                          self.numFailedJobs += 1
                          log("Job %s failed" % id)
                          #del self.activeJobList[job]
                          self.numJobsPending += 1 
                          self.activeJobList[job].status = "Pending"
                          return



class ReplayEntry:
  def __init__ (self):
	# jobType should be:
	# 	pickup
	#	pickupDropoff
	self.jobType = ""
	self.pickupGoal = ""
	self.dropoffGoal = ""
        self.pickPri = 10
        self.dropPri = 20
        self.echoStr = ""

	# how many milliseconds between last job and this job
	self.interval = 0

	# do we need this?
	self.jobID = ""

class CIM_Command:
  def __init__(self):
	self.status = ""
	self.responseString = ""
	self.command = ""
	self.response = ""
	self.startTime = 0
        self.pickupStartTime = 0
	self.endTime = 0
	self.cencelPending = 0
	self.robotName = ""
	self.emJobID = ""
        self.pickupStatus = ""
        self.dropoffStatus = ""
        self.pickupID = ""
        self.dropoffID = ""



##
## Main program starts here
##


# connect to EM
# clear EM jobs
# connect to robot
# stop robot
# wait 10
# loop:
#  submit qpd1
#  wait X
#  submit qpd2
#  wait 5
#  check robot for inprogress
#  if inprogress then check for pending
#  if 1 job then fail, if 3 jobs then succeed
#  cancel all jobs
#  wait 5

# TODO: open a log file to write results into


#hostList = ["10.0.202.102", "10.0.202.103", "10.0.202.104"];
hostList = ["10.0.202.102"]
sim = SIM()

i=0
for host in hostList:
  sim.addRobot(host)

cim = CIM()

#cim.readJobs(replayFile)

cim.initializeConnection()


# To Do
# Need to initialize robots
# need to use select to check for pausetask
# if pausing, then start timer

# TODO: clearQueue doesn't fully clear the queue.....
cim.clearQueue()

time.sleep(5)

# flush the buffer
sockData = cim.sock.read_until("\n\n", 2)
runCim = 1

swap1 = "queuePickupDropoff g1 g2\n"
swap2 = "queuePickupDropoff g2 g3\n"
swap3 = "queuePickupDropoff g7 g5\n"
swap4 = "queuePickupDropoff g5 g6\n"

firstSwap = swap1
secondSwap = swap2

jobDelay = 0.0


# Main loop.  Run a single loop of the list
while ( runCim ):
  sockData = ""

  # read from robots
  try:
    rList, wList, eList = select.select (sim.sockList, [], [], 0.01)
  except:
    print "Error"
    break

  if ( cim.swapIssued and (time.time() - swapTime > 5) and sim.robotList["10.0.202.102"].queryIssued == 0 ):
    # send first query
    log("Sending InProgress query")
    sim.robotList["10.0.202.102"].sock.send("queueQueryLocal status InProgress\n");
    sim.robotList["10.0.202.102"].queryIssued = 1
    sim.robotList["10.0.202.102"].queryInProgressIssued = 1
  elif ( cim.swapIssued and (time.time() - swapTime > 5) and sim.robotList["10.0.202.102"].queryIssued == 1 ):
    for sock in rList:
      sockData = sock.recv(1024)
      ipaddr, port = sock.getpeername()
      pos = 0
      pos = sockData.find("\n")
      while ( pos > 0 ):
        line = sockData[:pos];
        log("line is: %s" % (line))
        sockData = sockData[pos+1:];
        if ( sim.robotList[ipaddr].queryInProgressIssued ):
          if ( line.find("QueueQuery:") >= 0 ):
            print("InProgress")
            sim.robotList[ipaddr].inProgressCount += 1
          if ( line.find("EndQueueQuery") >= 0):
            log("Finished InProgress query")
            time.sleep(2)
            sim.robotList[ipaddr].queryInProgressIssued = 0
            sim.robotList[ipaddr].sock.send("queueQueryLocal status Pending\n")
            sim.robotList[ipaddr].queryPendingIssued = 1
            log("Sending Pending query")
        elif ( sim.robotList[ipaddr].queryPendingIssued ):
          if ( line.find("QueueQuery:") >= 0 ):
            print("Pending")
            sim.robotList[ipaddr].pendingCount += 1
          if ( line.find("EndQueueQuery") >= 0):
            log("Finished Pending query")
            sim.robotList[ipaddr].queryPendingIssued = 0
        pos = sockData.find("\n")
    #if ( time.time() - swapTime ) > 20 ):
    if (( sim.robotList["10.0.202.102"].queryInProgressIssued == 0 ) and
        ( sim.robotList["10.0.202.102"].queryPendingIssued == 0 ) and
        ( sim.robotList["10.0.202.102"].queryIssued == 1)):
      # time to end

      cim.swapIssued = 0
      if ( ( sim.robotList["10.0.202.102"].inProgressCount == 1 ) and
           ( sim.robotList["10.0.202.102"].pendingCount == 3 )):
        cim.successfullSwaps += 1
        log("Successful swap")
      else:
        cim.failedSwaps += 1
        log("Failed swap")

      # clean up 
      swapsIssued = 0
      sim.robotList["10.0.202.102"].inProgressCount = 0
      sim.robotList["10.0.202.102"].pendingCount = 0
      sim.robotList["10.0.202.102"].queryInProgressIssued = 0
      sim.robotList["10.0.202.102"].queryPendingIssued = 0
      sim.robotList["10.0.202.102"].queryIssued = 0
      cim.sock.write("queuecancel status pending\n")
      cim.sock.write("queuecancel status inprogress\n")
      time.sleep(10)
      # clear sock
  elif ( cim.swapIssued == 0):
    # need to send new swaps
    # clear buffers
    log("Issuing firstSwap - waiting %s" % (jobDelay))
    cim.sock.write(firstSwap)
    time.sleep(jobDelay)
    log("Issuing secondSwap")
    cim.sock.write(secondSwap)
    cim.swapsIssued += 1
    cim.swapIssued = 1
    swapTime = time.time()
    if ( cim.swapsIssued %2 == 1):
      firstSwap = swap3
      secondSwap = swap4
    else:
      firstSwap = swap1
      secondSwap = swap2
    if ( cim.swapsIssued%2 == 0):
      jobDelay += .005


  sockData = ""
  try:
    sockData = cim.sock.read_until("\n", .02)
    sockData = cim.oldSockData + sockData
  except:
    log("Failure reading from EM")
  
  time.sleep (.01)

  if ( time.time() - logTime > 5 ):
    log("=============")
    log("Sim runtime: %6.2f min Swaps issued: %s Success: %s Failed: %s Current delay: %2.3f" % ((time.time() - sim.startTime)/60, cim.swapsIssued, cim.successfullSwaps, cim.failedSwaps, jobDelay))
    logTime = time.time()

#end

cim.sock.close()
close(LOGFILE)
