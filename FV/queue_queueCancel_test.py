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
#replayFile = "20131129jobs.txt"

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
	self.emAddress = "10.0.200.200"
	#self.emAddress = "10.0.202.101"

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
          #job = "00:00:00 %s" % (job)
          (timestamp, type, pick, drop, pickpri, droppri, echo_string) = job.split(" ", 6)
          #interval = self.getInterval(self.lastTime, timestamp)
          #print "Interval is %s %s %s" %( timestamp, self.lastTime, interval)
          self.lastTime = timestamp
	  newJob = ReplayEntry()
	  self.numReplayJobs += 1
	  newJob.id = self.numReplayJobs
	  newJob.type = type
          #currentTime = time.strptime(timestamp, FMT)
          currentTime = 0
          #if ( self.numReplayJobs == 1 ):
          #  newJob.interval = 0
          #else:
          #  newJob.interval = time.mktime(currentTime) - time.mktime(lastJobTimeStamp)
          #  if ( newJob.interval < 0 ):
          #    newJob.interval += 24*60*60
          newJob.interval = .1
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

          try:
            ( first, rest ) = buf.split(" ", 1)
          except:
            print "FAILED - %s" %(buf)
            continue
          if ( first == "QueueShow:" ):
            ( id, jobid, priority, status, rest ) = rest.split(" ", 4)
            if ( status == "Pending" or status == "InProgress" ):
              self.sock.write("queuecancel jobid %s\n" % (jobid))
              self.sock.write("queuecancel id %s\n" % (id))
              log("Clearing job %s" % (id))
              time.sleep(.2)
          elif ( first == "QueueRobot:" ):
            ( robot, rest) = rest.split(" ", 1)
            log("Cancelling robot %s" % (robot))
            self.sock.write("queuecancel robotname %s\n" % (robot))
        # Now just try to cancel everything
        self.sock.write("queuecancel status Pending\n")
        self.sock.write("queuecancel status Interrupted\n")
        self.sock.write("queuecancel status InProgress\n")


          


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

# TODO: open a log file to write results into


# This is hte full list
#hostList = ["10.0.202.121", "10.0.202.122", "10.0.202.123", "10.0.202.124", "10.0.202.125", "10.0.202.126", "10.0.202.127", "10.0.202.128", "10.0.202.129", "10.0.202.130", "10.0.202.131", "10.0.202.132", "10.0.202.133", "10.0.202.134", "10.0.202.135", "10.0.202.137", "10.0.202.128", "10.0.202.129"];

# Remove 2, 5, 13, 6
hostList = ["10.0.202.121", "10.0.202.123", "10.0.202.124", "10.0.202.125", "10.0.202.126", "10.0.202.127", "10.0.202.128", "10.0.202.129", "10.0.202.131", "10.0.202.132", "10.0.202.134", "10.0.202.135", "10.0.202.137", "10.0.202.139"];
#hostList = ["10.0.202.103", "10.0.202.104"];
sim = SIM()

i=0
#for host in hostList:
#  sim.addRobot(host)

cim = CIM()

cim.readJobs(replayFile)

cim.initializeConnection()


# To Do
# Need to initialize robots
# need to use select to check for pausetask
# if pausing, then start timer

# TODO: clearQueue doesn't fully clear the queue.....
cim.clearQueue()

time.sleep(10)

# flush the buffer
sockData = cim.sock.read_until("\n\n", 2)


count = 0
while ( count < 100 ):
  log("Loop %s" % (count))
  jobsSent = 0
  j = 0
  while ( j < 500 ):
    cim.sendJob(cim.rawReplayJobList[j])
    jobsSent+=1
    j+=1

  log("Sent 500 jobs")
  time.sleep(40)
  log ("Cancelling jobs")
  cim.sock.write("queuecancel status Pending\n")
  cim.sock.write("queuecancel status InProgress\n")
  cim.sock.write("queuecancel status Interrupted\n")
  #cim.clearQueue()
  log("Sleeping")
  time.sleep(60)

  count+=1
  log ("Done with loop")



sys.exit()

## 
## we're not going to go any further
##






runCim = 1

# Main loop.  Run a single loop of the list
while ( runCim ):
  sockData = ""
  try:
    rList, wList, eList = select.select (sim.sockList, [], [], 0.01)
  except:
    print "Error"
    break
  for sock in rList:
    sockData = sock.recv(1024)
    ipaddr, port = sock.getpeername()
    pos = 0
    pos = sockData.find("\n")
    while ( pos > 0 ):
      line = sockData[:pos];
      #print "Found pos at %s: %s" % (pos, line)
      sockData = sockData[pos+1:];
      #print "line is %s" %(line)
      if ( line.find("PauseTask: Pausing") >= 0 ):
        #print "\n\n\n\nRobot is pausing\n\n\n\n"
        sim.robotList[ipaddr].sock.send("modeLock\n")
        sim.robotList[ipaddr].pauseState = "Paused"
        sim.robotList[ipaddr].pauseStartTime = time.time()
        sim.robotList[ipaddr].sock.send("multirobotsizeset 600 280 348 348 280\n")
      elif ( line.find("DockingState: Docked") >= 0 ):
        if ( sim.robotList[ipaddr].docked == 0):
          log("Robot %s docked" %(ipaddr))
          sim.robotList[ipaddr].docked = 1
          sim.robotList[ipaddr].dockStartTime = time.time()
      elif ( line.find("DockingState: Undocked") >= 0 ):
        if ( sim.robotList[ipaddr].docked == 1):
          log("Robot %s undocked" %(ipaddr))
          sim.robotList[ipaddr].docked = 0
          sim.robotList[ipaddr].dockEndTime = time.time()
          sim.dockedTime += (sim.robotList[ipaddr].dockEndTime - sim.robotList[ipaddr].dockStartTime)
      #else:
      #  print "no match"
      pos = sockData.find("\n")
      #time.sleep(1)


  sim.checkRobots()
    #print "reading %s bytes %s:%s" % (len(sockData), ipaddr, port)
    #print "-> %s" %(sockData)
    # watch for pause task


  sockData = ""
  try:
    sockData = cim.sock.read_until("\n", .02)
    sockData = cim.oldSockData + sockData
  except:
    log("Failure reading from EM")
  
  # process the received data.  Ingore if blank
  if ( sockData != "" and sockData != "\n" ):
    if ( sockData.count("\n") == 0 ):
      cim.oldSockData = sockData
      log("Incomplete line - using oldSockData\n")
      log(sockData)
      oldSockCount += 1
    else:
      cim.oldSockData = ""
      cim.parseResponse(sockData)

  # check if we should send a new job or not
  if ( cim.currentReplayJob < cim.numReplayJobs ):
    if (( time.time() - cim.lastJobTime) >
      cim.rawReplayJobList[cim.currentReplayJob].interval and
       cim.numJobsPending < 500 ):  # the "100" used to be 4   can probably take that out
      cim.sendJob(cim.rawReplayJobList[cim.currentReplayJob])
      cim.currentReplayJob += 1
  else:
    cim.currentReplayJob = 0

  # TODO: see if we should issue a new query

  # TODO: see if we should issue a cancel

  #time.sleep (.0001)

  if ( time.time() - logTime > 5 ):
    log("=============")
    log("Sim runtime: %6.2f min  Last Job:  %6.0f sec Next job: %6.0f sec" % ((time.time() - sim.startTime)/60, time.time() - cim.lastJobTime, cim.rawReplayJobList[cim.currentReplayJob].interval - (time.time() - cim.lastJobTime)))
    log("Jobs issued: %s  InProgress Jobs: %s Pending Jobs: %s" % (cim.numJobsIssued, (cim.numJobsActive - cim.numJobsPending), cim.numJobsPending))
    log("Jobs completed: %s Jobs failed: %s" % (cim.numSuccessfulJobs, cim.numFailedJobs))
    log("OldSockCount: %s" % (oldSockCount))
    log("Jobs in queue:")
    jobs = cim.activeJobList.keys()
    jobs.sort()
    oldestStartTime = time.time()
    for job in jobs:
      log("\t> %s %s %s %s %s %6.0f" % (cim.activeJobList[job].id, cim.activeJobList[job].robotName, cim.activeJobList[job].status, cim.activeJobList[job].pickupGoal, cim.activeJobList[job].dropoffGoal, time.time() - cim.activeJobList[job].startTime))
      log("\t\t%s %s %s %s" % (cim.activeJobList[job].pickupID, cim.activeJobList[job].pickupStatus, cim.activeJobList[job].dropoffID, cim.activeJobList[job].dropoffStatus))
      if ( cim.activeJobList[job].startTime < oldestStartTime ):
        oldestStartTime = cim.activeJobList[job].startTime
    if ( cim.numSuccessfulJobs > 0 ):
      avgJobRate = float(time.time() - sim.startTime) / cim.numSuccessfulJobs
      jobsPerDay = 24*3600 / avgJobRate
    else:
      avgJobRate = 0
      jobsPerDay = 0
    log("")
    for robot in sim.robotList:
      log("\tRobot: %s %2.0f%% %s" %(robot, sim.robotList[robot].SOC, sim.robotList[robot].docked))

    log("")
    log("\toldest job in queue:          %6.0f sec" %(time.time() - oldestStartTime))
    log("\tavg job rate:                 %6.0f sec" %(avgJobRate))
    log("\trate of jobs per day:         %6.0f / day" %(jobsPerDay))
    log("\taverage completion time:      %6.0f sec" %(cim.averageCompletionTime))
    log("\taverage pending time:         %6.0f sec" %(cim.averagePendingTime))
    log("\tlongest completion time:      %6.0f sec" %(cim.longestCompletionTime))
    log("\tlongest pending time:         %6.0f sec" %(cim.longestPendingTime))
    log("\tshortest completion time:     %6.0f sec" %(cim.shortestCompletionTime))
    log("\ttotal docked time:            %6.0f sec" %(sim.dockedTime))

    if ( sim.numRobots > 0 ):
      log("\tavg docked time per robot:    %6.0f sec" %(sim.dockedTime/sim.numRobots))
    logTime = time.time()

  # TODO: decide when to exit the program.  After X numbre of jobs??

#end

# print final stats
log("CIM script ending")
log("# Jobs issued: %s" % cim.numJobsIssued)
log("# Jobs completed successfully: %s" % cim.numSucessfulJobs)
log("# failed jobs: %s" % cim.numFailedJobs)
# for num robots
# log("Robot # %s: %s jobs executed %s jobs successful")
log("Print time stats - how long for each job")
# while loop has exited

cim.sock.close()
close(LOGFILE)
