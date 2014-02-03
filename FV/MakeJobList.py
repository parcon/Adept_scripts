#!/usr/bin/python
#Create list of jobs in the form of:
# [0.00:00:00.000] queuePickupDropoff Tool1 Tool5 15 20 AMA6008
from random import choice 
import random
import time
import sys
import os
import datetime

numberofjobs = 1800;

timestep= 30;
timeflux=30;
time =1.3;


goals=['Goal1', 'Goal2','Goal3','Goal4','Goal5','Goal6','Goal7','Goal8','Goal9','Goal10', 'Goal11','Goal12','Goal13','Goal14','Goal15','Goal16','Goal17','Goal18','Goal19','Goal20','Goal21','Goal22','Goal23','Goal24','Goal25']

f=open('joblist.txt','w')

for job in range(0,numberofjobs):
	
	f.write('[0.0') #hack to get about date problem
	timestring=str(datetime.timedelta(seconds=time))
	timestringmod=timestring[:-3]
	#print timestring
	f.write(timestringmod)
	f.write('] queuePickupDropoff ')
#choose the goals
	chosegoal1=choice(goals)
	#print chosegoal1
	goals.remove(chosegoal1)
	chosegoal2=choice(goals)
	#print chosegoal2
#add goals back to list
	goals.append(chosegoal1)
#make more string
	f.write(str(chosegoal1))
	f.write(' ')
	f.write(str(chosegoal2))
	f.write(' 15 20 AMA')
	f.write(str(job))
	f.write('\r\n')
	time=time+timestep+timeflux*random.random();

f.close()
#print 'done'

