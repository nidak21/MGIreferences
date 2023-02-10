#!/bin/bash

# wrapper to run all the steps to pull the MGI References dataset out of the db
# for each dataset, output both samplefile and table output formats

db=prod
getScript=../sdGetMGIRefs.py
logFile=getMGIRefs.log
echo writing to $logFile
set -x
python $getScript -s $db counts   > counts       2> $logFile
cat counts >> $logFile

python $getScript -s $db selected > selected.txt 2>> $logFile
python $getScript -s $db -o table selected > selected.tbl.txt 2>> $logFile

python $getScript -s $db rejected > rejected.txt 2>> $logFile
python $getScript -s $db -o table rejected > rejected.tbl.txt 2>> $logFile

python $getScript -s $db older > older.txt 2>> $logFile
python $getScript -s $db -o table older > older.tbl.txt 2>> $logFile

echo done `date`
