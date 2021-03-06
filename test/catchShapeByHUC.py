# This utility is an efficient way to do inner join of the catchment layer
# in NHDPlus MR with the flowline layer of each HUC.
# using ogr2ogr is very very slow: the catchment layer has 3m records on CONUS; 
# each HUC6 has thousands to tens of thousands of flowlines.
# We build a hash for flowline objects; then use the hash to query the big
# catchment database.
# Yan Y. Liu <yanliu@illinois.edu>
# 10/31/2016
# Input: HUC code
# Input: HUC flowline shape file
# Input: NHDPlus MR filegdb path
# Output: SQLite catchment ploygon file (to avoid the 2GB shapefile limit)
# Dependency: GDAL 2.1+ with python library support
import sys, os, string
from osgeo import gdal
from osgeo import ogr
import numpy as np

# function: filter Catchment layer to store only the catchment shape for the HUC
def queryCatchByHash(NHDDBPath = None, NHDCatchLayerName = None, Hucid = None, odir = None, flowHash = None):
    global keys
    global slopes
    global linelens
    global areasqkms

    if flowHash is None or len(flowHash) <= 0:
        print ("queryCatchByHash(): ERROR Flowline HASH is empty. ")
        sys.exit( 1 )
    if not os.path.isdir(odir):
        print ("queryCatchByHash(): ERROR output dir not exists: " + str(odir) )
        sys.exit( 1 )
    of = odir + "/" + Hucid + "_catch.sqlite"
    comidfile = odir + "/" + Hucid + "_comid.txt"
    if os.path.exists(of):
        print ("queryCatchByHash(): ERROR output file already exists: " + str(of) + ". Remove and run this program again if you want to re-create. " )
        sys.exit( 1 )
    
    # open NHDPlus DB
    ds = gdal.OpenEx( NHDDBPath, gdal.OF_VECTOR | gdal.OF_READONLY)
    if ds is None :
        print ("queryCatchByHash(): ERROR Open failed: " + str(NHDDBPath) )
        sys.exit( 1 )
    lyr = ds.GetLayerByName( NHDCatchLayerName )
    if lyr is None :
        print ("queryCatchByHash(): ERROR fetch layer: " + str(NHDCatchLayerName) )
        sys.exit( 1 )
    lyr.ResetReading()
    num_records = lyr.GetFeatureCount()
    lyr_defn = lyr.GetLayerDefn()
    srs = lyr.GetSpatialRef()
    geomType = lyr.GetGeomType()
    geomTypeStr = ""
    if geomType == ogr.wkbPolygon:
        geomTypeStr = "Polygon"
    if geomType == ogr.wkbMultiPolygon:
        geomTypeStr = "MultiPolygon"
    fi_comid = lyr_defn.GetFieldIndex('FEATUREID')
    fdef_comid = lyr_defn.GetFieldDefn(fi_comid)
    fi_shplen = lyr_defn.GetFieldIndex('Shape_Length')
    fdef_shplen = lyr_defn.GetFieldDefn(fi_shplen)
    fi_shparea = lyr_defn.GetFieldIndex('Shape_Area')
    fdef_shparea = lyr_defn.GetFieldDefn(fi_shparea)
    fi_areasqkm = lyr_defn.GetFieldIndex('AreaSqKM')
    fdef_areasqkm = lyr_defn.GetFieldDefn(fi_areasqkm)

    print ("queryCatchByHash(): Catchment layer GeomType: " + geomTypeStr + " num_records: " + str(num_records) )

    # create output SQLite (to avoid 2GB shp file limit since polygons take more space)
    #driverName = "ESRI Shapefile"
    driverName = "SQLite"
    drv = gdal.GetDriverByName( driverName )
    if drv is None:
        print ("queryCatchByHash(): ERROR %s driver not available.\n" % (driverName) )
        sys.exit( 1 )
    ods = drv.Create( of, 0, 0, 0, gdal.GDT_Unknown )
    if ods is None:
        print ("queryCatchByHash(): ERROR Creation of output file failed: "+of)
        sys.exit( 1 )
    olyr = ods.CreateLayer( NHDCatchLayerName, srs, geomType)
    if olyr is None:
        print ("queryCatchByHash(): ERROR Layer creation failed: "+NHDCatchLayerName )
        sys.exit( 1 )
    # create fields
    ofdef_comid = ogr.FieldDefn( "COMID", ogr.OFTInteger)
    ofdef_slope = ogr.FieldDefn( "SLOPE", ogr.OFTReal)
    ofdef_linelen = ogr.FieldDefn( "LINELEN", ogr.OFTReal)
    if olyr.CreateField ( ofdef_comid ) != 0 or olyr.CreateField ( fdef_shplen) != 0 or olyr.CreateField ( fdef_shparea ) != 0 or olyr.CreateField ( fdef_areasqkm ) != 0 or olyr.CreateField ( ofdef_slope ) != 0 or olyr.CreateField ( ofdef_linelen ) != 0:
        print ("queryCatchByHash(): ERROR Creating fields in output .")
        sys.exit( 1 )
    # get integer index to speed up the loops
    olyr_defn = olyr.GetLayerDefn()
    ofi_comid = olyr_defn.GetFieldIndex('COMID')
    ofi_shplen = olyr_defn.GetFieldIndex('Shape_Length')
    ofi_shparea = olyr_defn.GetFieldIndex('Shape_Area')
    ofi_areasqkm = olyr_defn.GetFieldIndex('AreaSqKM')
    ofi_slope= olyr_defn.GetFieldIndex('SLOPE') # line segment slope
    ofi_linelen = olyr_defn.GetFieldIndex('LINELEN') # line segment length
    # filter and keep only the records with FEATUREID=COMID
    i = 0
    count = 0
    comid_index_list = np.zeros(len(flowHash), dtype='int32')
    progressStr = "0%"
    for f in lyr: # for each row. in NHDPlus MR, it's 2.67m
        comid = f.GetFieldAsInteger(fi_comid)
        if comid in flowHash: # computationally expensive if hash size is big
            shplen = f.GetFieldAsDouble(fi_shplen) 
            shparea = f.GetFieldAsDouble(fi_shparea) 
            areasqkm = f.GetFieldAsDouble(fi_areasqkm) 
            # create feature
            fc = ogr.Feature( olyr_defn )
            fc.SetField(ofi_comid, comid)
            fc.SetField(ofi_shplen, shplen)
            fc.SetField(ofi_shparea, shparea)
            fc.SetField(ofi_areasqkm, areasqkm)
            comid_index = flowHash[comid]
            fc.SetField(ofi_slope, slopes[comid_index])
            fc.SetField(ofi_linelen, linelens[comid_index])
            areasqkms[comid_index] = areasqkm
            # create geom field
            geom = f.GetGeometryRef()
            fc.SetGeometry( geom ) # this method makes a copy of geom
            if olyr.CreateFeature( fc ) != 0:
                print ("queryCatchByHash(): ERROR Creating new feature in output for COMID=" + str(comid) )
                sys.exit( 1 )
            fc.Destroy()
            comid_index_list[count] = comid_index
            count += 1
        i += 1
        if (i % (num_records / 10 + 1) == 0):
            progressStr += "-->" + str((i * 100)/num_records) + "%"

    print (progressStr)
    print ("\nDone\n")
    print ("CATCHMENT_POLYGON_COUNT " + str(count) )
    fcomid = open(comidfile, "w")
    fcomid.write(str(count) + "\n") # first row is count
    for i in range(0, count):
        fcomid.write(str(keys[comid_index_list[i]]) + " " + str(slopes[comid_index_list[i]]) + " " + str(linelens[comid_index_list[i]]) +  " " + str(areasqkms[comid_index_list[i]]) + "\n") # each row is comid
    fcomid.close()
    ds = None
    ods = None
   

# function: build hash for flowline keys (COMID) 
def buildFlowlineHash(flowShpFile = None, lyrName = None, keyFieldName = None):
    global keys
    global slopes
    global linelens
    global areasqkms
    # open shape file
    ds = gdal.OpenEx( flowShpFile, gdal.OF_VECTOR | gdal.OF_READONLY)
    if ds is None :
        print ("buildFlowlineHash(): ERROR Open failed: " + str(flowShpFile) )
        sys.exit( 1 )
    lyr = ds.GetLayerByName( lyrName )
    if lyr is None :
        print ("buildFlowlineHash(): ERROR fetch layer: " + str(lyrName) )
        sys.exit( 1 )
    lyr.ResetReading()
    num_records = lyr.GetFeatureCount()
    lyr_defn = lyr.GetLayerDefn()
    fi_comid = lyr_defn.GetFieldIndex(keyFieldName)
    fi_slope = lyr_defn.GetFieldIndex('SLOPE')
    fi_linelen = lyr_defn.GetFieldIndex('LENGTHKM')
    if fi_comid < 0 or fi_slope < 0 :
        print ("buildFlowlineHash(): ERROR no key/slope field: " + str(keyFieldName) )
        sys.exit( 1 )

    # scan for keys 
    keys = np.zeros(num_records, dtype='int32')
    slopes = np.zeros(num_records, dtype='float64')
    linelens = np.zeros(num_records, dtype='float64')
    areasqkms = np.zeros(num_records, dtype='float64') # catchment attr, not flowline, just mem alloc here
    i = 0
    for f in lyr:
        keys[i] = f.GetFieldAsInteger(fi_comid)
        slopes[i] = f.GetFieldAsDouble(fi_slope)
        linelens[i] = f.GetFieldAsDouble(fi_linelen)
        i+=1

    ds = None   # close input layer 

    # build hash
    #flowHash = frozenset(keys) # hash as frozenset
    flowHash = dict.fromkeys(keys) # hash as pre-sized dictionary
    for j in range(0, i):
        flowHash[keys[j]] = j

    # return
    return flowHash

# global vars
keys=None
slopes=None
linelens=None
areasqkms=None

# usage: 
# module purge
# module load gdal2.1.2-stack
# python catchShapeByHUC.py 120401 /gpfs_scratch/nfie/hydro-properties/test/120401/120401-flows.shp 120401-flows COMID /gpfs_scratch/usgs/nhd/NFIEGeoNational.gdb Catchment /gpfs_scratch/nfie/hydro-properties/test/120401
if __name__ == '__main__':
    flowHucid = sys.argv[1] # HUC id
    flowShpFile = sys.argv[2] # flowline shp path for the HUC   
    flowLyrName = sys.argv[3] # layer name   
    flowIDField = sys.argv[4] # COMID   
    NHDDBPath = sys.argv[5] # NHDPlus DB (filegdb) path
    NHDCatchLayerName = sys.argv[6] # NHDPlus DB (filegdb) catchment layer name
    outputdir = sys.argv[7] # NHDPlus DB (filegdb) catchment layer name

    # build hash for COMID
    flowHash = buildFlowlineHash(flowShpFile, flowLyrName, flowIDField)
    print (sys.argv[0] + ": Built hash with " + str(len(flowHash)) + " COMIDs" )

    # filter Catchment layer and output
    queryCatchByHash(NHDDBPath, NHDCatchLayerName, flowHucid, outputdir, flowHash)



