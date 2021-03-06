#!/bin/bash
## huc6tms: create Height Above Nearest Drainage raster TMS Tile Map Service titles
## called by srun in SLURM to get cluster env such as process id
## version: v0.2
## Author: Yan Y. Liu
## Date: 05/13/2020

t1=`date +%s`

# env setup
source $HOME/sw/softenv
m=cades
sdir=$HOME/nfie-floodmap/test
source $sdir/handbyhuc.${m}.env

huc=HUC6
ddir=$HOME/data/HAND/current
odir=$HOME/scratch_br/test/huc6tms
tdir=/dev/shm
todir=$tdir/tms
[ ! -d $odir ] && mkdir -p $odir

colorfile=$sdir/HAND-blues.clr
rastermetatool=$sdir/getRasterInfo.py

# get list of HUC6 HAND files in zip
dataarray=(`ls $ddir/*.zip`)

# calc local workload
numtasks=${#dataarray[@]}
#numtasks=2 # debug
numprocs=$SLURM_NPROCS #num of processors
numlast=$((numtasks % numprocs))  # remaining
numlocal=$((numtasks / numprocs)) # num of items to process locally
starti=$((SLURM_PROCID * numlocal + numlast))
if [ $SLURM_PROCID -lt $numlast ]; then # take extra
  starti=$((SLURM_PROCID * (numlocal + 1)))
  let "numlocal+=1"
fi
echo "[$SLURM_PROCID] `date +%s`: starti: $starti numlocal: $numlocal total:$numtasks nnodes=$SLURM_NNODES numprocs=$SLURM_NPROCS onnode=$SLURM_NODEID"

i=$starti
let "endi=starti+numlocal"
while [ $i -lt $endi ]
do
  [ $i -ge $numtasks ] && continue # debug
  f=${dataarray[$i]}
  n=`basename $f .zip`
  [ -f $odir/${n}.zip ] && let "i+=1" && continue # skip if output exists

  echo "[$SLURM_PROCID] processing HUC6 $n ..."
  # unzip hand
  hand=$n/${n}hand.tif
  colordd=$n/${n}clr.tif
  tmsdir=$todir/$n
  mkdir -p $tmsdir
  cd $tdir
  unzip -q $f $hand
  # create color relief
  gdaldem color-relief $hand $colorfile $colordd -of GTiff -alpha 
  # create TMS tiles
  $sdir/gdal2tiles_cfim.py -e -z 5-12 -a 0,0,0 -p geodetic -s epsg:4326 -r bilinear -w openlayers -u https://cfim.ornl.gov/data/tms/$n -t "HAND Raster - HUC $n (v0.2)" $colordd $tmsdir 
  # get extent metadata
  read fsizeDEM colsDEM rowsDEM nodataDEM xmin ymin xmax ymax cellsize_resx cellsize_resy<<<$(python $rastermetatool $hand) && echo "$xmin $ymin $xmax $ymax" > $tmsdir/extent.txt
  # copy and clean up
  cd $todir
  echo "==SIZE== $n `du -smc $n | tail -n 1`"
  zip -q -r $odir/${n}.zip $n
  rm -fr $tdir/$n
  rm -fr $tmsdir

  let "i+=1"
done 

t2=`date +%s`
echo "[$SLURM_PROCID] =STAT= `expr $t2 \- $t1` seconds in total"
