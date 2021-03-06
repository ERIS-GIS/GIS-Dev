#-------------------------------------------------------------------------------
# Name:        US_Georeferencing
# Purpose:     Georeferecing the input images
# Author:      hkiavarz
# Created:     19/08/2020
#-------------------------------------------------------------------------------
import sys
import os
import arcpy
import cx_Oracle
import contextlib
import json
import ast
import shutil
import timeit
import urllib
import os
import json
from os import path

class Machine:
    machine_test = r"\\cabcvan1gis006"
    machine_prod = r"\\cabcvan1gis007"
class Credential:
    oracle_test = r"ERIS_GIS/gis295@GMTESTC.glaciermedia.inc"
    oracle_production = r"ERIS_GIS/gis295@GMPRODC.glaciermedia.inc"
class ImageBasePath:
    caaerial_test= r"\\CABCVAN1OBI007\ErisData\test\aerial_ca"
    caaerial_prod= r"\\CABCVAN1OBI007\ErisData\prod\aerial_ca"
class OutputDirectory:
    job_directory_test = r'\\192.168.136.164\v2_usaerial\JobData\test'
    job_directory_prod = r'\\192.168.136.164\v2_usaerial\JobData\prod'
    georef_images = r'\\cabcvan1nas003\historical\Georeferenced_Aerial_test'
class TransformationType():
    POLYORDER0 = "POLYORDER0"
    POLYORDER1 = "POLYORDER1"
    POLYORDER2 = "POLYORDER2"
    POLYORDER3 = "POLYORDER3"
    SPLINE = "ADJUST SPLINE"
    PROJECTIVE = "PROJECTIVE "
class ResamplingType():
    NEAREST  = "NEAREST"
    BILINEAR = "BILINEAR"
    CUBIC = "CUBIC"
    MAJORITY = "MAJORITY"
## Custom Exceptions ##
class OracleBadReturn(Exception):
    pass
class NoAvailableImage(Exception):
    pass
class Oracle:
    #static variable: oracle_functions
    oracle_functions = {'getorderinfo':"eris_gis.getOrderInfo"}
    erisapi_procedures = {'getGeoreferencingInfo':'flow_gis.getGeoreferencingInfo','passclipextent': 'flow_autoprep.setClipImageDetail',
                          'getImageInventoryInfo':'flow_gis.getImageInventoryInfo','UpdateInventoryImagePath':'Flow_gis.UpdateInventoryImagePath'}
    def __init__(self,machine_name):
        # initiate connection credential
        if machine_name.lower() =='test':
            self.oracle_credential = Credential.oracle_test
        elif machine_name.lower()=='prod':
            self.oracle_credential = Credential.oracle_production
        else:
            raise ValueError("Bad machine name")
    def connect_to_oracle(self):
        try:
            self.oracle_connection = cx_Oracle.connect(self.oracle_credential)
            self.cursor = self.oracle_connection.cursor()
        except cx_Oracle.Error as e:
            print(e,'Oracle connection failed, review credentials.')
    def close_connection(self):
        self.cursor.close()
        self.oracle_connection.close()
    def call_function(self,function_name,orderID):
        self.connect_to_oracle()
        cursor = self.cursor
        try:
            outType = cx_Oracle.CLOB
            func = [self.oracle_functions[_] for _ in self.oracle_functions.keys() if function_name.lower() ==_.lower()]
            if func !=[] and len(func)==1:
                try:
                    if type(orderID) !=list:
                        orderID = [orderID]
                    output=json.loads(cursor.callfunc(func[0],outType,orderID).read())
                except ValueError:
                    output = cursor.callfunc(func[0],outType,orderID).read()
                except AttributeError:
                    output = cursor.callfunc(func[0],outType,orderID)
            return output
        except cx_Oracle.Error as e:
            raise Exception(("Oracle Failure",e.message.message))
        except Exception as e:
            raise Exception(("JSON Failure",e.message.message))
        except NameError as e:
            raise Exception("Bad Function")
        finally:
            self.close_connection()
    def call_erisapi(self,erisapi_input):
        self.connect_to_oracle()
        cursor = self.cursor
        self.connect_to_oracle()
        cursor = self.cursor
        arg1 = erisapi_input
        arg2 = cursor.var(cx_Oracle.CLOB)
        arg3 = cursor.var(cx_Oracle.CLOB) ## Message
        arg4 = cursor.var(str)  ## Status
        try:
            func = ['eris_api.callOracle']
            if func !=[] and len(func)==1:
                try:
                    output = cursor.callproc(func[0],[arg1,arg2,arg3,arg4])
                except ValueError:
                    output = cursor.callproc(func[0],[arg1,arg2,arg3,arg4])
                except AttributeError:
                    output = cursor.callproc(func[0],[arg1,arg2,arg3,arg4])
            return output[0],cx_Oracle.LOB.read(output[1]),cx_Oracle.LOB.read(output[2]),output[3]
        except cx_Oracle.Error as e:
            raise Exception(("Oracle Failure",e.message))
        except Exception as e:
            raise Exception(("JSON Failure",e.message))
        except NameError as e:
            raise Exception("Bad Function")
        finally:
            self.close_connection()
def CoordToString(inputObj):
    coordPts_string = ""
    for i in range(len(inputObj)-1):
        coordPts_string +=  "'" + " ".join(str(i) for i in  inputObj[i]) + "';"
    result =  coordPts_string[:-1]
    return result
def createGeometry(pntCoords,geometry_type,output_folder,output_name, spatialRef = arcpy.SpatialReference(4326)):
    # print('FC folder: %s' % output_folder)
    # print('FC Name: %s' % output_name)
    outputFC = os.path.join(output_folder,output_name)
    if geometry_type.lower()== 'point':
        arcpy.CreateFeatureclass_management(output_folder, output_name, "MULTIPOINT", "", "DISABLED", "DISABLED", spatialRef)
        cursor = arcpy.da.InsertCursor(outputFC, ['SHAPE@'])
        cursor.insertRow([arcpy.Multipoint(arcpy.Array([arcpy.Point(*coords) for coords in pntCoords]),spatialRef)])
    elif geometry_type.lower() =='polyline':        
        arcpy.CreateFeatureclass_management(output_folder, output_name, "POLYLINE", "", "DISABLED", "DISABLED", spatialRef)
        cursor = arcpy.da.InsertCursor(outputFC, ['SHAPE@'])
        cursor.insertRow([arcpy.Polyline(arcpy.Array([arcpy.Point(*coords) for coords in pntCoords]),spatialRef)])
    elif geometry_type.lower() =='polygon':
        arcpy.CreateFeatureclass_management(output_folder,output_name, "POLYGON", "", "DISABLED", "DISABLED", spatialRef)
        cursor = arcpy.da.InsertCursor(outputFC, ['SHAPE@'])
        cursor.insertRow([arcpy.Polygon(arcpy.Array([arcpy.Point(*coords) for coords in pntCoords]),spatialRef)])
    del cursor
    return outputFC
def ApplyGeoref(scratchFolder,inputRaster,srcPoints,gcpPoints,transType, resType):
    arcpy.AddMessage('Start Georeferencing...')
    out_coor_system = arcpy.SpatialReference(4326)
    # georeference to WGS84
    # gcsImage_wgs84 = arcpy.Warp_management(inputRaster, srcPoints,gcpPoints,os.path.join(scratchFolder,'image_gc.tif'), transType, resType)
    gcsImage = arcpy.Warp_management(inputRaster, srcPoints,gcpPoints,os.path.join(scratchFolder,'image_gc.tif'))
    arcpy.AddMessage('--Georeferencing Done.')
    return os.path.join(scratchFolder,'image_gc.tif')
def export_to_jpg(env,imagepath,outputImage_jpg,ordergeometry,auid):

    mxd = arcpy.mapping.MapDocument(mxdexport_template)
    df = arcpy.mapping.ListDataFrames(mxd,'*')[0]
    sr = arcpy.SpatialReference(4326)
    df.SpatialReference = sr
    lyrpath = os.path.join(arcpy.env.scratchFolder,auid + '.lyr')
    arcpy.MakeRasterLayer_management(imagepath,lyrpath)
    image_lyr = arcpy.mapping.Layer(lyrpath)
    geo_lyr = arcpy.mapping.Layer(ordergeometry)
    arcpy.mapping.AddLayer(df,image_lyr,'TOP')
    arcpy.mapping.AddLayer(df,geo_lyr,'TOP')
    geometry_layer = arcpy.mapping.ListLayers(mxd,'OrderGeometry',df)[0]
    geometry_layer.visible = False
    geo_extent = geometry_layer.getExtent(True)
    image_extent = geo_lyr.getExtent(True)
    df.extent = image_extent
    if df.scale <= MapScale:
        df.scale = MapScale
        export_width = 5100
        export_height = 6600
    elif df.scale > MapScale:
        df.scale = ((int(df.scale)/100)+1)*100
        export_width = int(5100*1.4)
        export_height = int(6600*1.4)
    arcpy.RefreshActiveView()
    ###############################
    ## NEED TO EXPORT DF EXTENT TO ORACLE HERE (arial_image)
    NW_corner= str(df.extent.XMin) + ',' +str(df.extent.YMax)
    NE_corner= str(df.extent.XMax) + ',' +str(df.extent.YMax)
    SW_corner= str(df.extent.XMin) + ',' +str(df.extent.YMin)
    SE_corner= str(df.extent.XMax) + ',' +str(df.extent.YMin)
    try:
        image_extents = str({"PROCEDURE":Oracle.erisapi_procedures['passclipextent'], "ORDER_NUM" : order_num,"AUI_ID":auid,"SWLAT":str(df.extent.YMin),"SWLONG":str(df.extent.XMin),"NELAT":(df.extent.XMax),"NELONG":str(df.extent.XMax)})
        message_return = Oracle(env).call_erisapi(image_extents)
        if message_return[3] != 'Y':
            raise OracleBadReturn
    except OracleBadReturn:
        arcpy.AddError('status: '+message_return[3]+' - '+message_return[2])
    ##############################
    arcpy.mapping.ExportToJPEG(mxd,outputImage_jpg,df,df_export_width=export_width,df_export_height=export_height,world_file=False,color_mode = '24-BIT_TRUE_COLOR', jpeg_quality = 50)
    mxd.saveACopy(os.path.join(arcpy.env.scratchFolder,auid+'_export.mxd'))
    del mxd
def ExportToOutputs(env,geroref_Image,outputImage_jpg,output_folder,out_img_name,orderGeometry):
    arcpy.AddMessage('Start Exporting...')
    ## Copy georefed image to inventory folder
    shutil.copy(geroref_Image, os.path.join(output_folder,out_img_name + '.tif'))
    ## Copy georefed image tfw file to inventory folder
    shutil.copy(os.path.join(os.path.dirname(geroref_Image),'image_gc.tfw'), os.path.join(output_folder,out_img_name +'.tfw'))
    # ## Export georefed image as jpg file to jpg folder for US Aerial UI app
    outputImage_jpg = os.path.join(outputImage_jpg,out_img_name + '.jpg')
    export_to_jpg(env,geroref_Image,outputImage_jpg,orderGeometry,str(auid))
    
    arcpy.AddMessage('Output Image: %s' % os.path.join(output_folder,out_img_name + '.tif'))
    arcpy.AddMessage('--Exporting Done.')
if __name__ == '__main__':
    ### set input parameters
    orderID = arcpy.GetParameterAsText(0)
    auid = arcpy.GetParameterAsText(1)
    # orderID = '934785'
    # auid = '29815903'
    env = 'prod'
    if str(orderID) != '' and str(auid) != '':
        mxdexport_template = r'\\cabcvan1gis006\GISData\Aerial_US\mxd\Aerial_US_Export.mxd'
        MapScale = 6000
        try:
            start = timeit.default_timer()
            ##get info for order from oracle
            orderInfo = Oracle(env).call_function('getorderinfo',str(orderID))
            order_num = str(orderInfo['ORDER_NUM'])
            job_folder = ''
            if env == 'test':
                job_folder = os.path.join(OutputDirectory.job_directory_test,order_num)
            elif env == 'prod':
                job_folder = os.path.join(OutputDirectory.job_directory_prod,order_num)
            ### get georeferencing info from oracle
            oracle_georef = str({"PROCEDURE":Oracle.erisapi_procedures["getGeoreferencingInfo"],"ORDER_NUM": order_num, "AUI_ID": str(auid)})
            aerial_us_georef = Oracle(env).call_erisapi(oracle_georef)
            aerial_georefjson = json.loads(aerial_us_georef[1])
            if  (len(aerial_georefjson)) == 0:
                arcpy.AddWarning('The  georeferencing information is not availabe!')
                arcpy.AddWarning(aerial_georefjson[2])
            else:  
                org_image_folder = os.path.join(job_folder,'org')
                jpg_image_folder = os.path.join(job_folder,'jpg')
                if not os.path.exists(job_folder):
                #     shutil.rmtree(job_folder)
                    os.mkdir(job_folder)
                    os.mkdir(org_image_folder)
                    os.mkdir(jpg_image_folder)  
                ### get input image from inventory
                aerial_inventory = str({"PROCEDURE":Oracle.erisapi_procedures["getImageInventoryInfo"],"ORDER_NUM":order_num , "AUI_ID": str(auid)})
                aerial_us_inventory = Oracle(env).call_erisapi(aerial_inventory)
                aerial_inventoryjson = json.loads(aerial_us_inventory[1])
                
                if  (len(aerial_inventoryjson)) == 0:
                    arcpy.AddWarning('There is no data for Image in inventory!')
                    arcpy.AddWarning(aerial_us_inventory[2])
                else:
                    image_input_path_inv = aerial_inventoryjson[0]['ORIGINAL_IMAGEPATH'] # image path from inventory
                    image_input_path_job = os.path.join(job_folder,aerial_georefjson['imgname'])
                    arcpy.AddMessage('Input Image : %s' % image_input_path_inv)
                    if  len(image_input_path_inv) == 0: # image is not in house
                        image_input_path = image_input_path_job 
                    else:
                        image_input_path = image_input_path_inv
                    if len(image_input_path) == 0 or not os.path.exists(image_input_path):
                        arcpy.AddWarning(image_input_path +' DOES NOT EXIST')
                    else:
                        year = aerial_inventoryjson[0]['AERIAL_YEAR'] 
                        img_source = aerial_inventoryjson[0]['IMAGE_SOURCE']
                        ## setup image custom name year_DOQQ_AUI_ID
                        out_img_name = '%s_%s_%s'%(year,img_source,str(auid))
                        ## set scratch folder
                        scratchFolder = arcpy.env.scratchFolder
                        arcpy.env.workspace = scratchFolder
                        arcpy.env.overwriteOutput = True 
                        ### temp gdb in scratch folder
                        tempGDB =os.path.join(scratchFolder,r"temp.gdb")
                        if not os.path.exists(tempGDB):
                            arcpy.CreateFileGDB_management(scratchFolder,r"temp.gdb")
                        ## get order geometry 
                        orderGeometry = createGeometry(eval(orderInfo[u'ORDER_GEOMETRY'][u'GEOMETRY'])[0],orderInfo['ORDER_GEOMETRY']['GEOMETRY_TYPE'],tempGDB,'OrderGeometry')
                        gcpPoints = CoordToString(aerial_georefjson['envelope'])
                        ### Source point from input extent
                        TOP = str(arcpy.GetRasterProperties_management(image_input_path,"TOP").getOutput(0))
                        LEFT = str(arcpy.GetRasterProperties_management(image_input_path,"LEFT").getOutput(0))
                        RIGHT = str(arcpy.GetRasterProperties_management(image_input_path,"RIGHT").getOutput(0))
                        BOTTOM = str(arcpy.GetRasterProperties_management(image_input_path,"BOTTOM").getOutput(0))
                        srcPoints = "'" + LEFT + " " + BOTTOM + "';" + "'" + RIGHT + " " + BOTTOM + "';" + "'" + RIGHT + " " + TOP + "';" + "'" + LEFT + " " + TOP + "'"
                        ### Georeferencing
                        img_Georeferenced = ApplyGeoref(scratchFolder,image_input_path, srcPoints, gcpPoints, TransformationType.POLYORDER1, ResamplingType.BILINEAR)
                        # # ### ExportToOutputs
                        ExportToOutputs(env,img_Georeferenced, jpg_image_folder, OutputDirectory.georef_images ,out_img_name,orderGeometry)
                        ## Update image path in DB if image is not in house
                        # if  len(image_input_path_inv) == 0: # image is not in house
                        output_tif_image = os.path.join(OutputDirectory.georef_images,out_img_name + '.tif')
                        strprod_update_path = str({"PROCEDURE":Oracle.erisapi_procedures["UpdateInventoryImagePath"],"AUI_ID": str(auid), "ORIGINAL_IMAGEPATH":output_tif_image})
                        message_return = Oracle(env).call_erisapi(strprod_update_path.replace('u','')) ## remove unicode chrachter u from json before calling strprod
            end = timeit.default_timer()
            arcpy.AddMessage(('Duration:', round(end -start,4)))
        except:
            msgs = "ArcPy ERRORS:\n %s\n"%arcpy.GetMessages(2)
            arcpy.AddError(msgs)
            raise
    else:
        arcpy.AddWarning('Order Id and Auid are not availabe')
    