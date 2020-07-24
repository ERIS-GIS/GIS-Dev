#-------------------------------------------------------------------------------
# Name:        Extract_Footprint.py
# Purpose:     Create seamless map of Mosaic US imagery
# Author:      Hamid Kiavarz
# Created:     06/2020
#-------------------------------------------------------------------------------
import arcpy, os ,timeit      
import json
import logging
from arcpy.sa import *
from multiprocessing import Pool
import os.path
import logging

arcpy.CheckOutExtension("Spatial")

def get_spatial_res(imagepath):

    cellsizeX = float(str(arcpy.GetRasterProperties_management(imagepath,'CELLSIZEX')))
    cellsizeY = float(str(arcpy.GetRasterProperties_management(imagepath,'CELLSIZEY')))
    if cellsizeY > cellsizeX:
        return str(cellsizeY)
    else:
        return str(cellsizeX)
   
def get_filesize(imagepath):
    return str(os.stat(imagepath).st_size)
def get_imagepath(imagepath,ext):
    imagepath = imagepath.replace('.TAB',ext)
    return imagepath
def get_year(filename,netpath):
    x = netpath.split('\\')
    years = ['2000','2001','2002','2003','2004','2005','2006','2007','2008','2009','2010','2011','2012','2013','2014','2015','2016','2017','2018','2019']
    no_years = ['199x','200x','201x']
    for item in x:
        if item in years:
            return item
            break
    # if item is not in the years list
    for item in x:
        if item in no_years:
             return item
def get_file_extension(fileName):
    extArray = fileName.split('.')
    ext = '.' + extArray[len(extArray)-1]
    if ext == '.alg':
        ext = '.jp2'
    return ext       
def get_ImagePathandExt(inputFile):
    image_Path = ""
    ext=""
    tab_File = open(inputFile, 'r')
    all_lines = tab_File.readlines()
    for line in all_lines:
        if 'File' in line:
            file = line.split('"')[1]
            ext = get_file_extension(file)
            if os.path.isfile(inputFile.replace(".TAB", ext)):
                image_Path = inputFile.replace(".TAB", ext)
                print("yes1")
            elif os.path.isfile(os.path.join(os.path.dirname((os.path.dirname(inputFile))),os.path.basename(file))):
                image_Path = os.path.join(os.path.dirname((os.path.dirname(inputFile))),os.path.basename(file))
                print("yes2")
            elif len(os.path.dirname(file)) > 0: ## if there is a folder and file name in TAB file, extract file and its direct folder then replace by TAB folder
                print("yes3")
                splt = file.split('\\')
                filepPath = os.path.join(splt[len(splt)-2],splt[len(splt)-1])
                tabFile_parentFolder = os.path.dirname((inputFile))
                print(os.path.join(tabFile_parentFolder,filepPath))
                if os.path.isfile(os.path.join(tabFile_parentFolder,filepPath)):
                    image_Path = os.path.join(tabFile_parentFolder,filepPath)
            elif os.path.isfile(os.path.join(os.path.dirname(inputFile), file)): ## if only file name is in TAB file, join it to TAB folder
                print("yes4")
                image_Path = os.path.join(os.path.dirname(inputFile), file)
            # if os.path.isfile(os.path.join(r'\\cabcvan1nas003\doqq\200x\TX\_FULL_STATE_COVERAGE\2005\UTM\15',os.path.basename(file))):
            #     image_Path = os.path.join(r'\\cabcvan1nas003\doqq\200x\TX\_FULL_STATE_COVERAGE\2005\UTM\15',os.path.basename(file))

            break
    return [image_Path,ext]
def get_Image_Metadata(imagepath,extension,FID):
    originalFID = 'NA'
    bits = 'NA'
    width = 'NA'
    length = 'NA'
    ext = 'NA'
    geoRef = 'Y'
    fileSize = 'NA'
    spatial_res = 'NA'
    
    originalFID = str(FID)
    bits = arcpy.GetRasterProperties_management(imagepath,'VALUETYPE')
    width = arcpy.GetRasterProperties_management(imagepath,'COLUMNCOUNT')
    length = arcpy.GetRasterProperties_management(imagepath,'ROWCOUNT')
    ext = extension.split('.')[1]
    fileSize = get_filesize(imagepath)
    spatial_res = get_spatial_res(imagepath)
    desc = arcpy.Describe(imagepath)
    year = get_year(desc.baseName,desc.path)
    
    return [originalFID, bits, width, length, ext, geoRef, fileSize, imagepath, spatial_res, year]
def get_Footprint(inputRaster):
    try:
        ws = arcpy.env.scratchFolder
        arcpy.env.workspace = ws
        srWGS84 = arcpy.SpatialReference('WGS 1984')
        tmpGDB =os.path.join(ws,r"temp.gdb")
        if not os.path.exists(tmpGDB):
            arcpy.CreateFileGDB_management(ws,r"temp.gdb")

        # Calcuate Footprint geometry
        resampleRaster = os.path.join(ws,'resampleRaster' + '.tif')
        bin_Raster = os.path.join(ws,'bin_Raster' + '.tif')
        polygon_with_holes= os.path.join(tmpGDB,'polygon_with_holes')
        out_Vertices = os.path.join(tmpGDB,'Out_Vertices')

        arcpy.AddMessage('Start resampling the input raster...')
        start1 = timeit.default_timer()
        rasterProp = arcpy.GetRasterProperties_management(inputRaster, "CELLSIZEX")
        resampleRaster = arcpy.Resample_management(inputRaster,resampleRaster ,4, "NEAREST")
        inputSR = arcpy.Describe(resampleRaster).spatialReference
        end1 = timeit.default_timer()
        arcpy.AddMessage(('End resampling the input raster. Duration:', round(end1 -start1,4)))
        
 
        arcpy.AddMessage('Start creating binary raster (Raster Calculator)...')
        start2 = timeit.default_timer()
        expression = 'Con(' + '"' + 'resampleRaster' + '.tif' + '"' + ' >= 10 , 1)'
        bin_Raster = arcpy.gp.RasterCalculator_sa(expression, bin_Raster)
        end2 = timeit.default_timer()
        arcpy.AddMessage(('End creating binary raster. Duration:', round(end2 -start2,4)))

        # Convert binary raster to polygon       
        arcpy.AddMessage('Start creating prime polygon from raster...')
        start3 = timeit.default_timer()  
        # arcpy.RasterToPolygon_conversion(bin_Raster, 'primePolygon.shp', "SIMPLIFY", "VALUE")
        polygon_with_holes =  arcpy.RasterToPolygon_conversion(in_raster= bin_Raster, out_polygon_features=polygon_with_holes, simplify="SIMPLIFY", raster_field="Value", create_multipart_features="SINGLE_OUTER_PART", max_vertices_per_feature="")
        end3 = timeit.default_timer()
        arcpy.AddMessage(('End creating polygon. Duration:', round(end3 -start3,4)))

        ### extract the main polygon (with maximum area) which includes several donuts
        arcpy.AddMessage('Start extracting exterior ring (outer outline) of polygon...')
        start4 = timeit.default_timer()      
        sql_clause = (None, 'ORDER BY Shape_Area DESC')
        geom = arcpy.Geometry()
        row = arcpy.da.SearchCursor(polygon_with_holes,('SHAPE@'),None,None,False,sql_clause).next()
        geom = row[0]
        end4 = timeit.default_timer()
        arcpy.AddMessage(('End extracting polygon. Duration:', round(end4 -start4,4)))
        
        ### extract the exterior points from main polygon to generate pure polygon from ouer line of main polygon
        arcpy.AddMessage('Start extracting exterior points ...')
        start5 = timeit.default_timer()      
        outer_coords = []
        for island in geom.getPart():
            # arcpy.AddMessage("Vertices in island: {0}".format(island.count))
            for point in island:
                # coords.append = (point.X,point.Y)
                if not isinstance(point, type(None)):
                    newPoint = (point.X,point.Y)
                    if len(outer_coords) == 0:
                        outer_coords.append(newPoint)
                    elif not newPoint == outer_coords[0]:   
                        outer_coords.append((newPoint))
                    elif len(outer_coords) > 50:
                        outer_coords.append((newPoint))
                        break
        
        # # # # points_FC = arcpy.CreateFeatureclass_management(tmpGDB,"points_FC", "POINT", "", "DISABLED", "DISABLED", inputSR)
        # # # # i = 0
        # # # # with arcpy.da.InsertCursor(points_FC,["SHAPE@XY"]) as cursor: 
        # # # #     for coord in outer_coords:
        # # # #         cursor.insertRow([coord]) 
        # # # #         i+= 1
        # # # #         if i > 2:
        # # # #             break       
        # # # #     del cursor
        
        ### Create footprint  featureclass -- > polygon 
        footprint_FC = arcpy.CreateFeatureclass_management(tmpGDB,"footprint_FC", "POLYGON", "", "DISABLED", "DISABLED", inputSR)
        cursor = arcpy.da.InsertCursor(footprint_FC, ['SHAPE@'])
        cursor.insertRow([arcpy.Polygon(arcpy.Array([arcpy.Point(*coords) for coords in outer_coords]),inputSR)])
        del cursor
        end5 = timeit.default_timer()
        arcpy.AddMessage(('End extracting exterior points and inserted as FC. Duration:', round(end5 -start5,4)))
        
        arcpy.AddMessage('Start simplifying footprint polygon...')
        start6 = timeit.default_timer() 
        arcpy.Generalize_edit(footprint_FC, '100 Meter')
        finalGeometry = (arcpy.da.SearchCursor(footprint_FC,('SHAPE@')).next())[0]
        end6 = timeit.default_timer()
        arcpy.AddMessage(('End simplifying footprint polygon. Duration:', round(end6 -start6,4)))
        footprint_WGS84 = finalGeometry.projectAs(srWGS84)
        return(footprint_WGS84)
    except:
        msgs = "ArcPy ERRORS:\n %s\n"%arcpy.GetMessages(2)
        arcpy.AddError(msgs)
        raise
def UpdateSeamlessFC(DQQQ_footprint_FC,metaData,ft_Polygon):
    arcpy.AddMessage('Start Uploading to seamless FC...')
    start7 = timeit.default_timer() 
    srWGS84 = arcpy.SpatialReference('WGS 1984')
    insertRow = arcpy.da.InsertCursor(DQQQ_footprint_FC, ['Original_FID','BITS','WIDTH','LENGTH','EXT','GEOREF','FILESIZE','IMAGEPATH','SPATIAL_RESOLUTION','YEAR','SHAPE@'])
    rowtuple=[str(metaData[0]),str(metaData[1]),str(metaData[2]),str(metaData[3]),str(metaData[4]),str(metaData[5]),str(metaData[6]),str(metaData[7]),str(metaData[8]),str(metaData[9]),ft_Polygon]
    insertRow.insertRow(rowtuple)
    end7 = timeit.default_timer()
    arcpy.AddMessage(('End Uploading to seamless FC. Duration:', round(end7 -start7,4)))
    del insertRow

if __name__ == '__main__':
    
    ws =  arcpy.env.scratchFolder
    arcpy.env.workspace = ws
    arcpy.env.overwriteOutput = True   
    arcpy.AddMessage(ws)
    inputRaster = arcpy.GetParameterAsText(0)
    DQQQ_footprint_FC = r'F:\Aerial_US\USImagery\Data\Seamless_Map.gdb\Aerial_Footprint_Mosaic'
    # DQQQ_footprint_FC = r'F:\Aerial_US\USImagery\Data\Seamless_Map.gdb\Aerial_Footprint_Mosaic_Envelope'
    logfile = r'C:\Users\HKiavarz\Documents\log2.txt'
    DQQQ_ALL_FC = r'F:\Aerial_US\USImagery\Data\DOQQ_ALL.shp'
    
    
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.WARNING)
    handler = logging.FileHandler(logfile)
    handler.setLevel(logging.WARNING)
    logger.addHandler(handler)
    
    startTotal = timeit.default_timer()
    
    srWGS84 = arcpy.SpatialReference('WGS 1984')
    
    params =[]
    
    # expression = "FID >= 170000 AND FID <= 170691"
    # expression = "FID = 170000"
    list = [70015,
70016,
70017,
70018,
70019,
70020,
70021,
70022,
70023,
70024,
70025,
70026,
70027,
70028,
70029,
70030,
70031,
70032,
70033,
70034,
70035,
70036,
70037,
70038,
70039,
70040,
70041,
70042,
70043,
70044,
70045,
70046,
70047,
70048,
70049,
70050,
70051,
70052,
70053,
70054,
70055,
70056,
70057,
70058,
70059,
70060,
70061,
70062,
70063,
70064,
70065,
70066,
70067,
70068,
70069,
70070,
70071,
70072,
70073,
70074,
70268,
70269,
70270,
70271,
70272,
70273,
70274,
70275,
70276,
70277,
70278,
70279,
70280,
70281,
70282,
70283,
70284,
70285,
70286,
70287,
70288,
70289,
70290,
70291,
70292,
70293,
70294,
70295,
70296,
70297,
70298,
70299,
70300,
70301,
70302,
70303,
70304,
70305,
70306,
70307,
70308,
70309,
70310,
70311,
70312,
70313,
70314,
70315,
70316,
70317,
70318,
70319,
70320,
70321,
70322,
70323,
70324,
70325,
70326,
70327,
70328,
70329,
70330,
70331,
70332,
70333,
70334,
70335,
70336
]
    rowExist = 0
    for item in list:
        expression = "FID = " + str(item)
        # expressionFC = "Original_FID = '" + str(item) + "'"
        # try:
        #     Original_FID = arcpy.da.SearchCursor(DQQQ_footprint_FC, ['Original_FID'],expression).next()[0]
        #     rowExist = 1
        # except StopIteration:
        #     rowExist = 0
        # if rowExist == 0: # check if it is already processed
        rows = arcpy.da.SearchCursor(DQQQ_ALL_FC,["FID", 'TABLE_','SHAPE@'],where_clause=expression)
        for row in rows:
            startDataset = timeit.default_timer()   
            arcpy.AddMessage('-------------------------------------------------------------------------------------------------')
            arcpy.AddMessage('Start FID: ' + str(row[0]) + ' - processing Dataset: ' + row[1])
            tabfile_Path = row[1].replace('nas2520','cabcvan1nas003')
            if os.path.isfile(tabfile_Path) > 0:
                imagePathInfo = get_ImagePathandExt(tabfile_Path)
                if len(imagePathInfo[0]) > 0:
                    if imagePathInfo[1].lower() in ['.tif','.jpg','.sid','.png','.tiff','.jpeg','.jp2','.ecw']:
                        metaData = get_Image_Metadata(imagePathInfo[0],imagePathInfo[1],row[0])
                        # footprint_Polygon = get_Footprint(image_Path)
                        footprint_Polygon = row[2].projectAs(srWGS84)
                        UpdateSeamlessFC(DQQQ_footprint_FC,metaData,footprint_Polygon)
                    else:
                        arcpy.AddWarning("FID : {} - Input raster: is not the type of Composite Geodataset, or does not exist".format(row[0]))
                        logger.warning("FID :, {}, Input raster: is not the type of Composite Geodataset, or does not exist:, {} ".format(row[0], row[1]))
                else:
                    arcpy.AddWarning("FID :  {} -  Images is not available forthis path : {} ".format(row[0], row[1]))
                    logger.warning("FID : , {}, Images is not available for this path :, {} ".format(row[0], row[1]))
            else:
                arcpy.AddWarning("FID : {} - Tab file Path is not valid or available for: ".format(row[0]))
                logger.warning("FID : , {}, Tab file Path is not valid or available for:, {} ".format(row[0], row[1]))
            endDataset = timeit.default_timer()
            arcpy.AddMessage(('End FID: ' + str(row[0]) + ' - processed Dataset. Duration:', round(endDataset - startDataset,4)))    
            
    endTotal= timeit.default_timer()
    arcpy.AddMessage(('Total Duration:', round(endTotal -startTotal,4)))
    
    
    