#!/bin/bash
echo "Changes the EM IP for all the robots"

for((i=137;i<=139;i+=1));
do 
SIMIP="10.0.202.$i" ;
EMIP="10.0.200.200" ;

./setEM.sh $SIMIP $EMIP >> /dev/null

if (( $? == 0 )); then
	echo "Simbot $SIMIP Sucessfully Changed"
else
	echo "Simbot $SIMIP Not Modifed************"
	#read -p
fi

done
