#!/bin/bash
sshpass -p 'root' ssh root@$1 -t -t << EOF
sng_aramStop
gmount /usr/local/aramConfig rw
sed -i 's/^EnterpriseManagerAddress.*/EnterpriseManagerAddress $2 ; IP Address of the Enterprise Manager./' /usr/local/aramConfig/aramConfig.txt
gmount /usr/local/aramConfig ro
sng_aramStart
exit 
EOF
