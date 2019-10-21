

import sys
import os
import time
import random
import numpy
import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import requests
import json
import logging
import copy
import random
import time
import threading
import sse
import pytz


from bokeh.models import DatetimeTickFormatter, ColumnDataSource, BoxSelectTool, BoxAnnotation, Label, LegendItem, Legend, HoverTool, BoxEditTool, TapTool
from bokeh.models import Range1d,DataRange1d, Span
from bokeh import events
from bokeh.models.widgets import RadioButtonGroup, Paragraph, Toggle, MultiSelect, Button, Select, CheckboxButtonGroup,Dropdown
from bokeh.plotting import figure, curdoc
from bokeh.layouts import layout,widgetbox, column, row, Spacer
from bokeh.models import Range1d, PanTool, WheelZoomTool, ResetTool, ToolbarBox, Toolbar, Selection
from bokeh.models import FuncTickFormatter, CustomJSHover, SingleIntervalTicker, DatetimeTicker, CustomJS
from bokeh.themes import Theme
from pytz import timezone
from bokeh.models.glyphs import Rect
from bokeh.models.glyphs import Quad



haveLogger = False
globalAlpha = 0.3
globalRESTTimeout = 60


def setup_logging(loglevel=logging.DEBUG,tag = ""):
    global haveLogger
    print("setup_logging",haveLogger)
    if not haveLogger:
        # fileName = 'C:/Users/al/devel/ARBEIT/testmyapp.log'
        #logging.basicConfig(format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s', level=loglevel)

        #remove all initial handlers, e.g. console
        allHandlers = logging.getLogger('').handlers
        for h in allHandlers:
            logging.getLogger('').removeHandler(h)


        formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
        console = logging.StreamHandler()
        console.setLevel(loglevel)
        console.setFormatter(formatter)
        logging.getLogger('').addHandler(console)

        #logfile = logging.FileHandler('./log/widget_'+'%08x' % random.randrange(16 ** 8)+".log")
        #logfile = logging.FileHandler('./widget_' + '%08x' % random.randrange(16 ** 8) + ".log")
        if tag == "":
            tag = '%08x' % random.randrange(16 ** 8)
        logfile = logging.FileHandler('./log/widget_' + tag+ ".log")
        logfile.setLevel(loglevel)
        logfile.setFormatter(formatter)
        logging.getLogger('').addHandler(logfile)
        haveLogger = True




#import model
from model import date2secs,secs2date, secs2dateString
import themes #for nice colorsing



#give a part tree of nodes, return a dict with const=value
def get_const_nodes_as_dict(tree):
    consts ={}
    for node in tree:
        if node["type"] in ["const","variable"]:
            consts[node["name"]]=node["value"]
        if node["type"] == "referencer":
            if "forwardPaths" in node:
                consts[node["name"]] = node["forwardPaths"]

    return consts




class TimeSeriesWidgetDataServer():
    """
        a helper class for the time series widget dealing with the connection to the backend rest model server
        it also caches settings which don't change over time
    """
    def __init__(self,modelUrl,avatarPath):
        self.url = modelUrl # get the data from here
        self.path = avatarPath # here is the struct for the timeserieswidget
        #self.timeOffset = 0 # the timeoffset of display in seconds (from ".displayTimeZone)
        self.annotations = {}
        self.scoreVariables = []
        self.sseCb = None # the callbackfunction on event

        self.__init_logger(logging.DEBUG)
        self.__init_proxy()
        self.__get_settings()
        self.__init_sse()


    def __init_sse(self):
        self.sse = sse.SSEReceiver(f'{self.url}event/stream',self.sse_cb)
        self.sse.start()

    def sse_cb(self,data):
        self.logger.debug(f'sse {data}, {self.settings["observerIds"]}')
        #now we filter out the events which are for me
        if data["data"] in self.settings["observerIds"]: #only my own observers are currently taken
            #self.logger.info("sse match")
            if self.sseCb:
                self.sseCb(data)

    def sse_stop(self):
        self.sse.stop()
    def sse_register_cb(self,cb):
        self.sseCb = cb

    def __init_proxy(self):
        """
            try to open the proxies file, set the local proxy if possible
        """
        self.proxySetting = {}
        try:
            with open('proxies.json','r') as f:
                self.proxySetting = json.loads(f.read())
                self.logger.info("using a proxy!")
        except:
            self.logger.info("no proxy used")
            pass

    def __init_logger(self, level=logging.DEBUG):
        setup_logging(loglevel = level, tag=self.path)
        self.logger = logging.getLogger("TSServer")
        self.logger.setLevel(level)
        #handler = logging.StreamHandler()
        #formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
        #handler.setFormatter(formatter)
        #self.logger.addHandler(handler)
        #self.logger.setLevel(level)



    def __web_call(self,method,path,reqData):
        """
            this functions makes a call to the backend model serer to get data
            Args:
                method(string) one of ["GET","POST"]
                path: the nodepath to the time series widtet
                reqData: a dictionary with request data for te query like the list of variables, time limits etc.
            Returns (dict):
                the data from the backend as dict
        """
        self.logger.info("__web_call %s @%s data:%s",method,path,str(reqData))

        response = None
        now = datetime.datetime.now()
        if method.upper() == "GET":
            try:
                response = requests.get(self.url + path, timeout=globalRESTTimeout,proxies=self.proxySetting)
            except Exception as ex:
                self.logger.error("requests.get"+str(timeout)+" msg:"+str(ex))

        elif method.upper() == "POST":
            now = datetime.datetime.now()
            try:
                response = requests.post(self.url + path, data=json.dumps(reqData), timeout=globalRESTTimeout,
                                         proxies=self.proxySetting)
            except Exception as ex:
                self.logger.error("requets.post" + str(timeout) + " msg:" + str(ex))

        after = datetime.datetime.now()
        diff = (after-now).total_seconds()
        self.logger.info("response "+str(response)+" took "+ str(diff))
        if not response:
            self.logger.error("Error calling web " + path )
            return None
        else:
            rData = json.loads(response.content.decode("utf-8"))
            return rData

    def get_selected_variables_sync(self):
        request = self.path + ".selectedVariables"
        selectedVars = []

        nodes = self.__web_call("post", "_getleaves", request)
        selectedVars=[node["browsePath"] for node in nodes]
        self.selectedVariables=copy.deepcopy(selectedVars)
        return selectedVars


    def load_annotations(self):
        self.logger.debug("load_annotations")
        if (self.settings["hasAnnotation"] == True) or (self.settings["hasThreshold"] == True):
            response = self.__web_call("post","_get",[self.path+"."+"hasAnnotation"])
            annotationsInfo = get_const_nodes_as_dict(response[0]["children"])
            self.settings.update(annotationsInfo)
            #now get all annotations
            nodes = self.__web_call("post","_getleaves",self.path+".hasAnnotation.annotations")
            self.logger.debug("ANNOTATIONS"+json.dumps(nodes,indent=4))
            #now parse the stuff and build up our information
            self.annotations={}
            for node in nodes:
                if node["type"]=="annotation":
                    self.annotations[node["browsePath"]]=get_const_nodes_as_dict(node["children"])

                    if "startTime" in self.annotations[node["browsePath"]]:
                        self.annotations[node["browsePath"]]["startTime"] = date2secs(self.annotations[node["browsePath"]]["startTime"])*1000
                    if "endTime" in self.annotations[node["browsePath"]]:
                        self.annotations[node["browsePath"]]["endTime"] = date2secs(self.annotations[node["browsePath"]]["endTime"]) * 1000
                    if self.annotations[node["browsePath"]]["type"] == "threshold":
                        #we also pick the target
                        self.annotations[node["browsePath"]]["variable"]=self.annotations[node["browsePath"]]["variable"][0]
            self.logger.debug("server annotations" + json.dumps(self.annotations, indent=4))





    def __get_settings(self):
        """
            get all the settings of the widget and store them also in the self.settings cache
            Returns: none

        """
        request = [self.path]
        info = self.__web_call("post","_get",request)
        self.logger.debug("initial settings %s",json.dumps(info,indent=4))
        #self.originalInfo=copy.deepcopy(info)
        #grab some settings
        self.settings = get_const_nodes_as_dict(info[0]["children"])

        #also grab the selected
        request = self.path+".selectedVariables"
        self.selectedVariables=[]
        nodes = self.__web_call("post","_getleaves",request)
        for node in nodes:
            self.selectedVariables.append(node["browsePath"])
        #get the selectable
        nodes = self.__web_call('POST',"_getleaves",self.path+'.selectableVariables')
        self.selectableVariables = []
        for node in nodes:
            self.selectableVariables.append(node["browsePath"])
        #also remeber the timefield as path
        request = self.path+".table"
        nodes = self.__web_call("post","_getleaves",request)
        #this should return only one node
        timerefpath = nodes[0]["browsePath"]+".timeField"
        #another call to get it right
        nodes = self.__web_call("post", "_getleaves", timerefpath)
        self.timeNode = nodes[0]["browsePath"]
        #get the score nodes if any
        nodes = self.__web_call('POST', "_getleaves", self.path + '.scoreVariables')
        if not nodes:
            self.scoreVariables = []
        else:
            self.scoreVariables = [node["browsePath"] for node in nodes]

        self.load_annotations()
        """
        #now grab more infor for annotations if needed:
        if (self.settings["hasAnnotation"] == True) or (self.settings["hasThreshold"] == True):
            response = self.__web_call("post","_get",[self.path+"."+"hasAnnotation"])
            annotationsInfo = get_const_nodes_as_dict(response[0]["children"])
            self.settings.update(annotationsInfo)
            #now get all annotations
            nodes = self.__web_call("post","_getleaves",self.path+".hasAnnotation.annotations")
            #self.logger.debug("ANNOTATIONS"+json.dumps(nodes,indent=4))
            #now parse the stuff and build up our information
            self.annotations={}
            for node in nodes:
                if node["type"]=="annotation":
                    self.annotations[node["browsePath"]]=get_const_nodes_as_dict(node["children"])

                    if "startTime" in self.annotations[node["browsePath"]]:
                        self.annotations[node["browsePath"]]["startTime"] = date2secs(self.annotations[node["browsePath"]]["startTime"])*1000
                    if "endTime" in self.annotations[node["browsePath"]]:
                        self.annotations[node["browsePath"]]["endTime"] = date2secs(self.annotations[node["browsePath"]]["endTime"]) * 1000
                    if self.annotations[node["browsePath"]]["type"] == "threshold":
                        #we also pick the target
                        self.annotations[node["browsePath"]]["variable"]=self.annotations[node["browsePath"]]["variable"][0]
            #self.logger.debug("server annotations" + json.dumps(self.annotations, indent=4))
        """
        #grab the info for the buttons
        myButtons=[]
        for node in info[0]["children"]:
            if node["name"]=="buttons":
                myButtons = node["children"]

        #now get more info on the buttons
        if myButtons != []:
            buttonInfo = self.__web_call("post","_get",myButtons)
            self.settings["buttons"]=[]
            for button in buttonInfo:
                #find the caption and target
                caption = ""
                target = ""
                for child in button["children"]:
                    if child["name"] == "caption":
                        caption=child["value"]
                    if child["name"] == "onClick":
                        targets = child["forwardRefs"]
                if targets != "":
                    #create that button
                    self.settings["buttons"].append({"name":caption,"targets":targets.copy()})


        # now compile info for the observer #new observers
        # we remeber all ids of observers in our widget
        self.settings["observerIds"]=[]
        for node in info[0]["children"]:
            if node["type"]=="observer":
                self.settings["observerIds"].append(node["id"])

        # now grab the info for the backgrounds
        background={}
        for node in info[0]["children"]:
            if node["name"] == "hasBackground":
                background["hasBackground"] = node["value"]
            if node["name"] == "background" and background["hasBackground"]==True:
                # we take only the first entry (there should be only one) of the referencer:
                # this is the nodeId of the background values
                background["background"]=node["forwardRefs"][0]
            if node["name"] == "backgroundMap":
                background["backgroundMap"] = copy.deepcopy(node["value"])      #the json map for background values and color mapping
        if all(key in background for key in ["hasBackground","background","backgroundMap"]):
            self.settings["background"]=copy.deepcopy(background)
        else:
            self.settings["background"]={"hasBackground":False}
                #we dont have a valid background definition


        self.logger.debug("SERVER.SETTINGS-------------------------")
        self.logger.debug("%s",json.dumps(self.settings,indent=4))


    ##############################
    ## INTERFACE FOR THE WIDGET
    ##############################

    def execute_function(self,descriptor):
        """ trigger the execution of a registered function in the backend """
        return self.__web_call("POST","_execute",descriptor)


    def get_values(self,varList):
        """  get a list of values of variables this is for type varialb, const """
        return self.__web_call("POST","_getvalue",varList)


    def get_data(self,variables,start=None,end=None,bins=300):
        """
            retrieve a data table from the backend
            Args:
                variables(list): the nodes from which the data is retrieved
                start (float): the startime in epoch ms
                end (float): the endtime in epoch ms
                bins (int): the number of samples to be retrieved between the start and end time
            Returns (dict):
                the body of the response of the data request of the backend
        """
        self.logger.debug("server.get_data()")
        varList = self.selectedVariables.copy()
        #include background values if it has background enabled
        if self.settings["background"]["hasBackground"]==True:
            varList.append(self.settings["background"]["background"]) # include the node it holding the backgrounds
        # now get data from server
        if start:
            start=start/1000
        if end:
            end=end/1000
        body = {
            "nodes": varList,
             "startTime" : start,
             "endTime" :   end,
            "bins":bins,
            "includeTimeStamps": "02:00",
        }
        r=self.__web_call("POST","_getdata",body)
        #convert the time to ms since epoch
        r["__time"]=(numpy.asarray(r["__time"])*1000).tolist()
        #make them all lists and make all inf/nan etc to nan
        for k,v in r.items():
            r[k]=[value if numpy.isfinite(value) else numpy.nan for value in v]
        #self.logger.debug(str(r))
        return r

    def get_time_node(self):
        return self.timeNode


    def get_variables_selectable(self):
        """ returns the selectable variables from the cache"""
        return copy.deepcopy(self.selectableVariables)

    def get_variables_selected(self):
        """ return list of selected variables from the cache"""
        return copy.deepcopy(self.selectedVariables)

    def get_annotations(self):
        return copy.deepcopy(self.annotations)

    def bokeh_time_to_string(self,epoch):
        localtz =  timezone(self.settings["timeZone"])
        dt = datetime.datetime.fromtimestamp(epoch/1000, localtz)
        return dt.isoformat()

    def get_score_variables(self):
        return copy.deepcopy(self.scoreVariables)

    def is_score_variable(self,variableBrowsePath):
        return (variableBrowsePath in self.scoreVariables)


    #start and end are ms(!) sice epoch, tag is a string
    def add_annotation(self,start=0,end=0,tag="unknown",type="time",min=0,max=0, var = None):
        """
            add a new user annotation to the model and also add it to the local cache
            Args:
                start(float): the start time in epcoh ms
                end(float): the end time in epoch ms
                tag (string) the tag to be set for this annotation
            Returns:
                the node browsePath of this new annotation
        """

        #place a new annotation into path
        nodeName = '%08x' % random.randrange(16 ** 8)
        annoPath = self.path + "." + "hasAnnotation.newAnnotations."+nodeName
        if type == "time":
            nodesToCreate = [
                {"browsePath": annoPath,"type":"annotation"},
                {"browsePath": annoPath + '.type',"type":"const","value":"time"},
                {"browsePath": annoPath + '.startTime',"type":"const","value":self.bokeh_time_to_string(start)},
                {"browsePath": annoPath + '.endTime', "type": "const", "value":self.bokeh_time_to_string(end)},
                {"browsePath": annoPath + '.tags', "type": "const", "value": [tag]}
                ]
        elif type =="threshold":
            nodesToCreate = [
                {"browsePath": annoPath, "type": "annotation"},
                {"browsePath": annoPath + '.type', "type": "const", "value": "threshold"},
                {"browsePath": annoPath + '.min', "type": "const", "value": min},
                {"browsePath": annoPath + '.max', "type": "const", "value": max},
                {"browsePath": annoPath + '.tags', "type": "const", "value": [tag]},
                {"browsePath": annoPath + '.variable', "type": "referencer", "targets": [var]}

            ]
        self.logger.debug("creating anno %s",str(nodesToCreate))
        res = self.__web_call('POST','_create',nodesToCreate)

        #now also update our internal list
        self.annotations[annoPath] = {"startTime":start,"endTime":end,"tags":[tag],"min":min,"max":max,"type":type,"variable":self.get_variables_selected()[0]}
        return annoPath


    def adjust_annotations(self,annoPath,anno):
        """
            change an exising annotation and write it back to the model via REST
            Args:
                anno [dict]: contains entries to be overwritten in the original annotation dict
        """
        if annoPath not in self.annotations:
            return False
        self.annotations[annoPath].update(anno)
        if anno['type'] == "time":
            #for time annotation we write the startTime and endTime
            nodesToModify =[
                {"browsePath": annoPath + ".startTime", "value":self.bokeh_time_to_string(anno["startTime"])},
                {"browsePath": annoPath + ".endTime", "value": self.bokeh_time_to_string(anno["endTime"])}
            ]
        elif anno['type'] == "threshold":
            nodesToModify = [
                {"browsePath": annoPath + ".min", "value": anno["min"]},
                {"browsePath": annoPath + ".max", "value": anno["max"]}

            ]
        else:
            logger.error("adjust_annotations : unsopported type")
            return

        res = self.__web_call('POST', 'setProperties', nodesToModify)





    def delete_annotations(self,deleteList):
        """ delete existing annotation per browsePath from model and cache"""
        for nodePath in deleteList:
            del self.annotations[nodePath]
        self.__web_call("POST","_delete",deleteList)
        pass

    def set_variables_selected(self, varList):
        """ update the currently selected variables to cache and backend """
        query={"deleteExisting":True,"parent":self.path+".selectedVariables","add":varList}
        self.__web_call("POST","_references",query)
        self.selectedVariables=varList.copy()
        return

    def get_settings(self):
        return copy.deepcopy(self.settings)

    def refresh_settings(self):
        self.__get_settings()

    def select_annotation(self,annoList):
        #anno list is a list of browsepaths
        query = {"deleteExisting": True, "parent": self.path + ".hasAnnotation.selectedAnnotations", "add": annoList}
        self.__web_call("POST", "_references", query)
        return


class TimeSeriesWidget():
    def __init__(self, dataserver,curdoc=None):
        self.curdoc = curdoc
        self.id = "id#"+str('%8x'%random.randrange(16**8))
        self.__init_logger()
        self.logger.debug("__init TimeSeriesWidget()")
        self.server = dataserver
        self.height = 600
        self.width = 900
        self.lines = {} #keeping the line objects
        self.legendItems ={} # keeping the legend items
        self.legend ={}
        self.hasLegend = False
        self.data = None
        self.dispatchList = [] # a list of function to be executed in the bokeh app context
                                # this is needed e.g. to assign values to renderes etc
        self.dispatchLock = threading.Lock() # need a lock for the dispatch list
        #self.dispatcherRunning = False # set to true if a function is still running
        self.annotationTags = []
        self.hoverTool = None
        self.showThresholds = True # initial value to show or not the thresholds (if they are enabled)
        self.streamingMode = False # is set to true if streaming mode is on
        self.annotations = {} #   holding the bokeh objects of the annotations
        self.userZoomRunning = False # set to true during user pan/zoom to avoid stream updates at that time
        self.inStreamUpdate = False # set true inside the execution of the stream update
        self.backgrounds = [] #list of current boxannotations dict entries: these are not the renderers
        self.threadsRunning = True # the threads are running: legend watch
        self.annotationsVisible = False # we are currently not showing annotations
        self.boxModifierVisible = False # we are currently no showing the modifiert lines

        self.__init_figure() #create the graphical output
        self.__init_new_observer()      #

    class ButtonCb():
        """
            a wrapper class for the user button callbacks. we need this as we are keeping parameters with the callback
            and the bokehr callback system does not extend there
        """
        def __init__(self,parent,parameter):
            self.parameter = parameter
            self.parent = parent
        def cb(self):
            self.parent.logger.info("user button callback to trigger %s",str(self.parameter))
            self.parent.server.execute_function(self.parameter[0]) # we just trigger the first reference
            pass


    def __init_logger(self, level=logging.DEBUG):
        """initialize the logging object"""
        setup_logging()
        self.logger = logging.getLogger("TSWidget")
        self.logger.setLevel(logging.DEBUG)
        #handler = logging.StreamHandler()

        #formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
        #handler.setFormatter(formatter)
        #self.logger.addHandler(handler)

        #self.logger.setLevel(level)


    def observer_cb(self,data):
        """
         called by the ts server on reception of an event from the model server
         events are
         - update for lines (selection of lines, add, remove lines)
         - update in the backgrounds
         - streaming update
           we can do calls to the restservice here but can't work with the bokeh data, therefore we
           dispatch functions to be executed in the callback from the bokeh loop
        """
        self.logger.debug(f"observer_cb {data}")
        if data["event"] == "timeSeriesWidget.variables":
            #refresh the lines
            self.server.get_selected_variables_sync() # get the new set of lines
            self.logger.debug("dispatch the refresh lines")
            self.__dispatch_function(self.refresh_plot)
        elif data["event"] == "timeSeriesWidget.background":
            self.logger.debug("dispatch the refresh background")
            self.__dispatch_function(self.refresh_backgrounds)
        elif data["event"] == "timeSeriesWidget.stream":
            self.logger.debug(f"self.streamingMode {self.streamingMode}")
            if self.streamingMode and not self.streamingUpdateData:
                #self.logger.debug("get stream data")
                #we update the streaming every second
                #get fresh data, store it into a variable and make the update on dispatch in the context of bokeh
                variables = self.server.get_variables_selected()
                variablesRequest = variables.copy()
                variablesRequest.append("__time")  # make sure we get the time included
                #self.logger.debug(f"request stream data{self.streamingInterval}")
                self.streamingUpdateDataInterval = self.streamingInterval #store this to check later if it has changed
                self.streamingUpdateData = self.server.get_data(variablesRequest, -self.streamingInterval, None,
                                                                self.server.get_settings()["bins"])  # for debug
                self.__dispatch_function(self.stream_update)
        elif data["event"] == "timeSeriesWidget.annotations":
            self.logger.debug(f"must reload annotations")
            self.reInitAnnotationsVisible = self.annotationsVisible #store the state
            # sync from the server
            self.__dispatch_function(self.reinit_annotations)

    def reinit_annotations(self):
        self.hide_annotations()
        self.server.load_annotations()
        self.logger.debug("reinit_annotations=>init_annotations")
        self.init_annotations()
        if self.reInitAnnotationsVisible:
            self.logger.debug("reinit_annotations=>init_annotations")
            self.show_annotations()

    def __legend_check(self):
        try:
            # now we also check if we have a legend click which means that we must delete a variable from the selection
            # self.logger.debug("RENDERERS CHECK --------------------------")
            deleteList = []
            for r in self.plot.renderers:
                if r.name and r.name in self.server.get_variables_selected() and r.visible == False:
                    # there was a click on the legend to hide the variables
                    self.logger.debug("=>>>>>>>>>>>>>>>>>DELETE FROM plot:" + r.name)
                    deleteList.append(r.name)
            if deleteList != []:
                # now prepare the new list:
                newVariablesSelected = [var for var in self.server.get_variables_selected() if var not in deleteList]
                self.logger.debug("new var list" + str(newVariablesSelected))
                self.server.set_variables_selected(newVariablesSelected)
                # self.__dispatch_function(self.refresh_plot)
        except Exception as ex:
            self.logger.error("problem during __legend_check" + str(ex))

        return (deleteList != [])


    def __init_new_observer(self):
        self.server.sse_register_cb(self.observer_cb)


    def __init_figure(self):

        """
            initialize the time series widget, plot the lines, create controls like buttons and menues
            also hook the callbacks
        """

        self.hoverCounter = 0
        self.newHover = None
        self.hoverTool = None # forget the old hovers
        self.showBackgrounds = False
        self.showThresholds = False
        self.buttonWidth = 70

        #layoutControls = []# this will later be applied to layout() function

        settings = self.server.get_settings()

        if "width" in settings:
            self.width = settings["width"]
        if "height" in settings:
            self.height = settings["height"]

        #set the theme
        if settings["theme"] == "dark":
            self.curdoc().theme = Theme(json=themes.darkTheme)
            self.lineColors = themes.darkLineColors
        else:
            self.curdoc().theme = Theme(json=themes.whiteTheme)
            self.lineColors = themes.whiteLineColors

        #self.cssClasses = {"button":"button_21","groupButton":"group_button_21","multiSelect":"multi_select_21"}
        #self.cssClasses = {"button": "button_21_sm", "groupButton": "group_button_21_sm", "multiSelect": "multi_select_21_sm"}
        #self.layoutSettings = {"controlPosition":"bottom"} #support right and bottom, the location of the buttons and tools


        #initial values
        self.rangeStart = settings["startTime"]
        self.rangeEnd = settings["endTime"]

        #create figure
        """
           the creation of the figure was reworked as this is a work around for a well known bug (in 1.04), see here
           https://github.com/bokeh/bokeh/issues/7497

           it's a bokeh problem with internal sync problems of frontend and backend, so what we do now is:
           1) use toolbar_location = None to avoid auto-creation of toolbar
           2) create tools by hand
           3) assign them to the figure with add_tools()
           4) create a toolbar and add it to the layout by hand
        """
        self.wheelZoomTool = WheelZoomTool(dimensions="width")
        tools = [self.wheelZoomTool, PanTool(dimensions="width")]
        if settings["hasAnnotation"] == True:
            self.boxSelectTool = BoxSelectTool(dimensions="width")
            tools.append(self.boxSelectTool)
        elif settings["hasThreshold"] == True:
            self.boxSelectTool = BoxSelectTool(dimensions="height")
            tools.append(self.boxSelectTool)
        tools.append(ResetTool())










        fig = figure(toolbar_location=None, plot_height=self.height,
                     plot_width=self.width,
                     sizing_mode="scale_width",
                     x_axis_type='datetime', y_range=Range1d())
        self.plot = fig

        #b1 = date2secs(datetime.datetime(2015,2,13,3,tzinfo=pytz.UTC))*1000
        #b2 = date2secs(datetime.datetime(2015,2,13,4,tzinfo=pytz.UTC))*1000
        #wid = 20*60*1000 # 20 min
        #self.boxData = ColumnDataSource({'x': [b1,b2], 'y':[0,0],'width': [5, 5],'height':[300,300],"alpha":[1,1,0.2]})

        #self.boxRect = self.plot.rect(x="x", y="y", width="width", height="height",source=self.boxData)
        #self.boxRect = self.plot.rect('x', 'y', 'width', 'height', source=self.boxData,width_units="screen")#, height_units="screen")#, height_units="screen")
        self.boxModifierTool=BoxEditTool( renderers=[],num_objects=0,empty_value=0.1)#,dimensions="width")
        self.box_modifier_init()
        #self.box_modifier_show()

        # possible attribures to boxedittool:
        # custom_icon, custom_tooltip, dimensions, empty_value, js_event_callbacks, js_property_callbacks, name, num_objects, renderers, subscribed_events
        #self.plot.add_layout(self.boxRect)
        #self.boxModifierRect.data_source.on_change("selected",self.box_cb)
        #self.boxRect.data_source.on_change("active", self.box_cb_2)

        tools.append(self.boxModifierTool)





        for tool in tools:
            fig.add_tools(tool) # must assign them to the layout to have the actual use hooked
        toolBarBox = ToolbarBox()  #we need the strange creation of the tools to avoid the toolbar to disappear after
                                   # reload of widget, then drawing an annotations (bokeh bug?)
        toolBarBox.toolbar = Toolbar(tools=tools,active_inspect=None,active_scroll=self.wheelZoomTool)
        #active_inspect = [crosshair],
        # active_drag =                         # here you can assign the defaults
        # active_scroll =                       # wheel_zoom sometimes is not working if it is set here
        # active_tap
        toolBarBox.toolbar_location = "right"
        toolBarBox.toolbar.logo = None # no bokeh logo

        self.tools = toolBarBox
        self.toolBarBox = toolBarBox


        self.plot.xaxis.formatter = FuncTickFormatter(code = """
            let local = moment(tick).tz('%s');
            let datestring =  local.format();
            return datestring.slice(0,-6);
            """%settings["timeZone"])

        self.plot.xaxis.ticker = DatetimeTicker(desired_num_ticks=4)# give more room for the date time string (default was 6)
        self.refresh_plot()

        #hook in the callback of the figure
        self.plot.x_range.on_change('start', self.range_cb)
        self.plot.x_range.on_change('end', self.range_cb)
        self.plot.on_event(events.Pan, self.event_cb)
        self.plot.on_event(events.PanStart, self.event_cb)
        self.plot.on_event(events.PanEnd, self.event_cb)
        self.plot.on_event(events.LODEnd, self.event_cb)
        self.plot.on_event(events.Reset, self.event_cb)
        self.plot.on_event(events.SelectionGeometry, self.event_cb)
        self.plot.on_event(events.Tap,self.event_cb)


        #make the controls
        layoutControls =[]

        #Annotation drop down
        labels=[]
        if settings["hasAnnotation"] == True:
            labels = settings["tags"]
            labels.append("-erase-")
        if settings["hasThreshold"] == True:
            labels.extend(["threshold","-erase threshold-"])
        if labels:
            menu = [(label,label) for label in labels]
            self.annotationDropDown = Dropdown(label="Annotate: "+str(labels[0]), menu=menu,width=self.buttonWidth,css_classes = ['dropdown_21'])
            self.currentAnnotationTag = labels[0]
            self.annotationDropDown.on_change('value', self.annotation_drop_down_on_change_cb)
            #self.annotation_drop_down_on_change_cb() #call it to set the box select tool right and the label
            layoutControls.append(self.annotationDropDown)

        # show Buttons
        # initially everything is disabled
        # check background, threshold, annotation, streaming
        self.showGroupLabels = []
        self.showGroupLabelsDisplay=[]
        if self.server.get_settings()["hasAnnotation"] == True:
            self.showGroupLabels.append("Annotation")
            self.showGroupLabelsDisplay.append("Anno")
        if self.server.get_settings()["background"]["hasBackground"]:
            self.showGroupLabels.append("Background")
            self.showGroupLabelsDisplay.append("Back")
            self.showBackgrounds = False # initially off
        if self.server.get_settings()["hasThreshold"] == True:
            self.showGroupLabels.append("Threshold")
            self.showGroupLabelsDisplay.append("Thre")
            self.showThresholds = False # initially off
        if self.server.get_settings()["hasStreaming"] == True:
            self.showGroupLabels.append("Streaming")
            self.showGroupLabelsDisplay.append("Stream")
            self.streamingMode = False # initially off
        self.showGroup = CheckboxButtonGroup(labels=self.showGroupLabelsDisplay)
        self.showGroup.on_change("active",self.show_group_on_click_cb)
        layoutControls.append(row(self.showGroup))

        #make the custom buttons
        buttonControls = []
        self.customButtonsInstances = []
        if "buttons" in settings:
            self.logger.debug("create user buttons")
            #create the buttons
            for entry in settings["buttons"]:
                button = Button(label=entry["name"],width=self.buttonWidth)#,css_classes=['button_21'])
                instance = self.ButtonCb(self,entry["targets"])
                button.on_click(instance.cb)
                buttonControls.append(button)
                self.customButtonsInstances.append(instance)

        #make the debug button
        if "hasReloadButton" in self.server.get_settings():
            if self.server.get_settings()["hasReloadButton"] == True:
                #we must create a reload button
                button = Button(label="reload",width=self.buttonWidth)#, css_classes=['button_21'])
                button.on_click(self.reset_all)
                buttonControls.append(button)


        if 0: # turn this helper button on to put some debug code
            self.debugButton= Button(label="debug",width=self.buttonWidth)
            self.debugButton.on_click(self.debug_button_cb)
            buttonControls.append(self.debugButton)

        layoutControls.extend(buttonControls)

        #build the layout
        #self.layout = layout( [row(children=[self.plot,self.tools],sizing_mode="fixed")],row(layoutControls,width=self.width ,sizing_mode="scale_width"))
        self.layout = layout([row(children=[self.plot, self.tools], sizing_mode="fixed")], row(layoutControls, width=int(self.width*0.6),sizing_mode="scale_width"))

        if self.server.get_settings()["hasAnnotation"] == True:
            self.init_annotations() # we create all annotations that we have into self.annotations



    def debug_button_cb(self):
        self.debugButton.css_classes = ['button_21']

    def box_cb(self,attr,old,new):
        self.debug("BOXCB")

    def box_update(self,x1,x2):
        self.boxData.data["xs"]=[x1,x2]

    def show_group_on_click_cb(self,attr,old,new):
        # in old, new we get a list of indices which are active
        self.logger.debug("show_group_on_click_cb "+str(attr)+str(old)+str(new))
        turnOn = [self.showGroupLabels[index] for index in (set(new)-set(old))]
        turnOff = [self.showGroupLabels[index] for index in (set(old)-set(new))]
        if "Background" in turnOn:
            self.showBackgrounds = True
            self.refresh_backgrounds()
        if "Background" in turnOff:
            self.showBackgrounds = False
            self.refresh_backgrounds()
        if "Annotation" in turnOn:
            self.show_annotations()
        if "Annotation" in turnOff:
            self.hide_annotations()
        if "Threshold" in turnOn:
            self.showThresholds = True
            self.show_thresholds()
        if "Threshold" in turnOff:
            self.showThresholds = False
            self.hide_thresholds()
        if "Streaming" in turnOn:
            self.start_streaming()
        if "Streaming" in turnOff:
            self.stop_streaming()

    def start_streaming(self):
        self.logger.debug(f"start_streaming {self.rangeEnd-self.rangeStart}")
        #get data every second and push it to the graph
        self.streamingInterval = self.rangeEnd-self.rangeStart # this is the currently selected "zoom"
        self.streamingUpdateData = None
        self.streamingMode = True


    def stop_streaming(self):
        self.logger.debug("stop streaming")
        self.streamingMode = False



    def annotation_drop_down_on_change_cb(self,attr,old,new):
        mytag = self.annotationDropDown.value
        self.logger.debug("annotation_drop_down_on_change_cb " + str(mytag))
        self.annotationDropDown.label = "Annotate: "+mytag
        self.currentAnnotationTag = mytag
        if "threshold" in mytag:
            #we do a a threshold annotation, adjust the tool
            self.boxSelectTool.dimensions = "height"
        else:
            self.boxSelectTool.dimensions = "width"


    def annotations_radio_group_cb(self,args):
        """called when a selection is done on the radio button for the annoations"""
        option = self.annotationButtons.active  # gives a 0,1 list, get the label now
        # tags = self.server.get_settings()["tags"]
        mytag = self.annotationTags[option]
        self.logger.debug("annotations_radio_group_cb "+str(mytag))
        if "threshold" in mytag:
            #we do a a threshold annotation, adjust the tool
            self.boxSelectTool.dimensions = "height"
        else:
            self.boxSelectTool.dimensions = "width"

    def testCb(self, attr, old, new):
        self.logger.debug("testCB "+"attr"+str(attr)+"\n old"+str(old)+"\n new"+str(new))
        self.logger.debug("ACTIVE: "+str(self.plot.toolbar.active_drag))

    def __make_tooltips(self):
        #make the hover tool
        """
            if we create a hover tool, it only appears if we plot a line, we need to hook the hover tool to the figure and the toolbar separately:
            to the figure to get the hover functionality, there we also need to add all renderers to the hover by hand if we create line plots later on
            still haven't found a way to make the hover tool itself visible when we add it to the toolbar; it does appear when we draw a new line,
            if we change edit/del and add lines, (including their renderers, we need to del/add those renderes to the hover tools as well

        """

        if not self.hoverTool:
            #we do this only once

            self.logger.info("MAKE TOOLTIPS"+str(self.hoverCounter))
            hover = HoverTool(renderers=[])
            #hover.tooltips = [("name","$name"),("time", "@__time{%Y-%m-%d %H:%M:%S.%3N}"),("value","@$name{0.000}")] #show one digit after dot
            hover.tooltips = [("name", "$name"), ("time", "@{__time}{%f}"),
                             ("value", "@$name{0.000}")]  # show one digit after dot
            #hover.formatters={'__time': 'datetime'}
            custom = """var local = moment(value).tz('%s'); return local.format();"""%self.server.get_settings()["timeZone"]
            hover.formatters = {'__time': CustomJSHover(code=custom)}
            if self.server.get_settings()["hasHover"] in ['vline','hline','mouse']:
                hover.mode = self.server.get_settings()["hasHover"]
            hover.line_policy = 'nearest'
            self.plot.add_tools(hover)
            self.hoverTool = hover
            self.toolBarBox.toolbar.tools.append(hover)  # apply he hover tool to the toolbar

        # we do this every time
        # reapply the renderers to the hover tool
        renderers = []
        self.hoverTool.renderers = []
        renderers = []
        for k, v in self.lines.items():

            if not self.server.is_score_variable(k):
                self.logger.debug(f"add line {k} t hover")
                renderers.append(v)
        self.hoverTool.renderers = renderers


    def stream_update_backgrounds(self):
        """ we update the background by following this algo:
            - take the last existing entry in the backgrounds
            - do we have a new one which starts inside the last existing?
              NO: find the
        """
        #make current backgrounds from the latest data and check against the existing backgrounds, put those which we need to append
        newBackgrounds = self.make_background_entries(self.streamingUpdateData)
        addBackgrounds = [] # the backgrounds to be created new
        self.logger.debug("stream_update_backgrounds")
        if self.backgrounds == []:
            #we don't have backgrounds yet, make them
            self.hide_backgrounds()
        else:
            # we have backgrounds
            # now see if we have to adjust the last background
            for entry in newBackgrounds:
                if entry["start"] <= self.backgrounds[-1]["end"] and entry["end"] > self.backgrounds[-1]["end"]:
                    # this is the first to show, an overlapping or extending one, we cant' extend the existing easily, so
                    # we put the new just right of the old
                    addEntry = {"start": self.backgrounds[-1]["end"], "end": entry["end"], "value":entry["value"], "color": entry["color"]}
                    addBackgrounds.append(addEntry)
                if entry["start"] > self.backgrounds[-1]["end"] and entry["end"]> self.backgrounds[-1]["end"]:
                    #these are on the right side of the old ones, just add them
                    addBackgrounds.append(entry)

        boxes =[]

        for back in addBackgrounds:
            name = "__background"+str('%8x'%random.randrange(16**8))
            newBack = BoxAnnotation(left=back["start"], right=back["end"],
                                    fill_color=back["color"],
                                    fill_alpha=globalAlpha,
                                    name=name)  # +"_annotaion
            boxes.append(newBack)
            back["rendererName"]=name
            self.backgrounds.append(back) # put it in the list of backgrounds for later use

        self.plot.renderers.extend(boxes)

        #remove renderes out of sight
        deleteList = []
        for r in self.plot.renderers:
            if r.name and "__background" in r.name:
                #self.logger.debug(f"check {r.name}, is is {r.right} vs starttime {self.plot.x_range.start}")
                #this is a background, so let's see if it is out of sight
                if r.right < self.plot.x_range.start:
                    #this one can go, we can't see it anymore
                    deleteList.append(r.name)
        self.logger.debug(f"remove background renderes out of sight{deleteList}")
        if deleteList:
            self.remove_renderers(deleteList=deleteList)


        #newBackgrounds = self.make_background_entries(self.streamingUpdateData)
        #self.hide_backgrounds()
        #self.show_backgrounds()


        return




    def stream_update(self):
        try:
            self.inStreamUpdate = True # to tell the range_cb that the range adjustment was not from the user
            self.logger.debug("stream update")#+str(self.streamingUpdateData))
            if self.streamingUpdateData:
                if not self.userZoomRunning:
                    if not self.streamingUpdateDataInterval == self.streamingInterval:
                        #the interval has changed in the meantime due to user pan/zoom, we skip this data, get fresh one
                        self.streamingUpdateData = None
                        self.inStreamUpdate = False
                        self.logger.debug("interval has changed")
                        return
                    #, we can now savely push them
                    # debug prints
                    #for k,v in self.streamingUpdateData.items():
                    #    self.logger.debug(f" {k}:{v}")

                    self.logger.debug(f"apply data {self.streamingUpdateData.keys()},")
                    if set(self.streamingUpdateData.keys()) != set(self.data.data.keys()):
                        self.logger.error(f"keys not match {self.streamingUpdateData.keys()},{self.data.data.keys()}, skip this data")
                        self.streamingUpdateData = None
                    else:
                        self.data.data = self.streamingUpdateData# #update the plot
                        self.plot.x_range.start = self.data.data["__time"][0]
                        self.plot.x_range.end = self.data.data["__time"][-1]
                        self.adjust_y_axis_limits()
                        if self.showBackgrounds:
                            #we also try to update the backgrounds here
                            self.stream_update_backgrounds()

                        self.streamingUpdateData = None #the thread can get new data
                else:
                    self.logger.info("user zoom running, try later")
                    #user is panning, zooming, we should wait and try again later
                    self.__dispatch_function(self.stream_update)
        except Exception as ex:
            self.logger.error(f"stream_update error {ex}")
        self.inStreamUpdate = False
        self.streamingUpdateData = None
    def __check_observed(self,counter):
        """
            this function is periodically called from a threading.thread
            we check if some data if the backend has changed and if we need to do something on change
        """
        self.logger.debug("enter __check_observed() "+str(counter))
        try:
            """
            #now see what we have to do
            if "background" in self.observerStatus:
                #check the background counter for update
                backgroundCounter = self.server.get_values(self.server.get_settings()["observer"]["observerBackground"])
                #self.logger.debug("background observer Val"+str(backgroundCounter))
                if self.observerStatus["background"] != None and self.observerStatus["background"] != backgroundCounter:
                    #we have a change in the background:
                    self.logger.debug("observer background changed")
                    self.__dispatch_function(self.refresh_backgrounds)
                self.observerStatus["background"] = backgroundCounter
            if "variables" in self.observerStatus:
                variables = self.server.get_selected_variables_sync()
                if self.observerStatus["variables"] != None and self.observerStatus["variables"]!=variables:
                    #we have a change in the selected variables
                    self.logger.debug("variables selection observer changed"+str(self.observerStatus["variables"] )+"=>"+str(variables))
                    self.__dispatch_function(self.refresh_plot)
                self.observerStatus["variables"] = variables
            """
            #now we also check if we have a legend click which means that we must delete a variable from the selection
            self.logger.debug("RENDERERS CHECK --------------------------")
            deleteList=[]
            for r in self.plot.renderers:
                if r.name and r.name in self.server.get_variables_selected() and r.visible == False:
                    #there was a click on the legend to hide the variables
                    self.logger.debug("=>>>>>>>>>>>>>>>>>DELETE FROM plot:"+r.name)
                    deleteList.append(r.name)
            if deleteList != []:
                #now prepare the new list:
                newVariablesSelected = [var for var in self.server.get_variables_selected() if var not in deleteList]
                self.logger.debug("new var list"+str(newVariablesSelected))
                self.server.set_variables_selected(newVariablesSelected)
                #self.__dispatch_function(self.refresh_plot)
        except Exception as ex:
            self.logger.error("problem during __check_observed"+str(ex)+str(sys.exc_info()[0]))

        self.logger.debug("leave __check_observed()")

    def reset_all(self):
        """
            this is an experimental function that reloads the widget in the frontend
            it should be executed as dispatched
        """
        self.logger.debug("self.reset_all()")
        self.server.refresh_settings()

        #clear out the figure
        self.hasLegend = False # to make sure the __init_figure makes a new legend
        self.plot.renderers = [] # no more renderers
        self.data = None #no more data
        self.lines = {} #no more lines



        self.__init_figure()
        #self.__init_observer()
        self.__init_new_observer()

        self.curdoc().clear()
        self.curdoc().add_root(self.get_layout())

    def __dispatch_function(self,function):
        """
            queue a function to be executed in the periodic callback from the bokeh app main loop
            this is needed for functions which are triggered from a separate thread but need to be
            executed in the context of the bokeh app loop

        Args:
            function: functionpointer to be executed
        """
        with self.dispatchLock:
            self.logger.debug(f"__dispatch_function {function.__name__}")
            self.dispatchList.append(function)


    def adjust_y_axis_limits(self):
        """
            this function automatically adjusts the limts of the y-axis that the data fits perfectly in the plot window
        """
        self.logger.debug("adjust_y_axis_limits")

        lineData = []
        selected = self.server.get_variables_selected()
        for item in self.data.data:
            if item in selected:
                lineData.extend(self.data.data[item])

        if len(lineData) > 0:
            all_data = numpy.asarray(lineData, dtype=numpy.float)
            dataMin = numpy.nanmin(lineData)
            dataMax = numpy.nanmax(lineData)
            if dataMin==dataMax:
                dataMin -= 1
                dataMax += 1
            # Adjust the Y min and max with 2% border
            yMin = dataMin - (dataMax - dataMin) * 0.02
            yMax = dataMax + (dataMax - dataMin) * 0.02
            self.logger.debug("current y axis limits" + str(yMin)+" "+str(yMax))

            self.plot.y_range.start = yMin
            self.plot.y_range.end = yMax
            
            self.box_modifier_rescale()

        else:
            self.logger.warning("not y axix to arrange")


    def box_modifier_init(self):
        self.logger.debug("box_modifier_init")

        b1 = date2secs(datetime.datetime(2015, 2, 13, 3, tzinfo=pytz.UTC)) * 1000
        b2 = date2secs(datetime.datetime(2015, 2, 13, 4, tzinfo=pytz.UTC)) * 1000
        wid = 20 * 60 * 1000  # 20 min
        self.boxModifierData = ColumnDataSource( {'x': [b1, b2], 'y': [0, 0], 'width': [5, 5], 'height': [300, 300] })

        self.boxModifierRectHorizontal = self.plot.rect('x', 'y', 'width', 'height', source=self.boxModifierData, width_units="screen",line_width=5,line_dash="dotted",line_color="white",fill_color="black" )  # , height_units="screen")#, height_units="screen")
        self.boxModifierRectVertical = self.plot.rect('x', 'y', 'width', 'height', source=self.boxModifierData, height_units="screen",line_width=5,line_dash="dotted",line_color="white",fill_color="black")  # , height_units="screen")#, height_units="screen")

        self.boxModifierRectHorizontal.data_source.on_change("selected", self.box_cb)
        self.boxModifierRectVertical.data_source.on_change("selected", self.box_cb)

        #self.boxModifierTool.renderers=[self.boxModifierRectHorizontal]#,self.boxModifierRectVertical]

        #self.boxModifierRectHorizontal.visible = False
        #self.boxModifierRectVertical.visible = False
        self.box_modifier_hide()# remove the renderers

    def box_modifier_tap(self, x=None, y=None):

        self.logger.debug(f"box_modifier_tap x:{x} y:{y}")
        #we do this only if annotations are visible
        if self.annotationsVisible:
            #check if we are inside an annotation
            for annoName, anno in self.server.get_annotations().items():
                self.logger.debug("check anno "+annoName+" "+anno["type"])
                if anno["type"] == "time":
                    if anno["startTime"]<x and anno["endTime"]>x:
                        #we are inside this annotation:
                        self.box_modifier_show(annoName,anno)
                        return
        if self.showThresholds:

            for annoName, anno in self.server.get_annotations().items():
                if anno["type"] == "threshold":
                    # we must also check if that specific threshold annotation is currently visible
                    if self.find_renderer(annoName):
                        self.logger.debug(f" annomin {anno['min']} anno max {anno['max']}")
                        if anno["min"] < y and anno["max"] > y:
                            self.box_modifier_show(annoName,anno)
                            return
        #we are not inside an annotation, we hide the box modifier
        self.box_modifier_hide()


    def box_modifier_show(self,annoName,anno):
        self.logger.debug(f"box_modifier_show {annoName}")

        if self.boxModifierVisible:
            if self.boxModifierAnnotationName == annoName:
                #this one is already visible, we are done
                return
            else:
                #if another is already visible, we hide it first
                self.box_modifier_hide()


        self.boxModifierAnnotationName = annoName
        self.server.select_annotation(annoName)
        boxYCenter = int((self.plot.y_range.start + self.plot.y_range.end) / 2)
        boxXCenter = int((self.plot.x_range.start + self.plot.x_range.end) / 2)
        boxYHeight = (self.plot.y_range.end - self.plot.y_range.start) * 4
        boxXWidth = (self.plot.x_range.end - self.plot.x_range.start)

        if anno["type"] == "time":
            start = anno["startTime"]
            end = anno["endTime"]
            self.boxModifierData.data = {'x': [start, end], 'y': [boxYCenter, boxYCenter], 'width': [5, 5], 'height': [boxYHeight, boxYHeight]}
            self.boxModifierRectHorizontal.visible=True
            self.boxModifierOldData = copy.deepcopy(self.boxModifierData.data)
            self.boxModifierVisible = True
            self.plot.renderers.append(self.boxModifierRectHorizontal)
            self.boxModifierTool.renderers = [self.boxModifierRectHorizontal]  # ,self.boxModifierRectVertical]

        if anno["type"] == "threshold":
            self.boxModifierData.data = {'x': [boxXCenter, boxXCenter], 'y': [anno['min'], anno['max']], 'width': [boxXWidth,boxXWidth], 'height': [5, 5]}
            self.boxModifierRectVertical.visible=True
            self.boxModifierOldData = copy.deepcopy(self.boxModifierData.data)
            self.boxModifierVisible = True
            self.plot.renderers.append(self.boxModifierRectVertical)
            self.boxModifierTool.renderers = [self.boxModifierRectVertical]



    def box_modifier_hide(self):

        self.boxModifierVisible = False
        self.boxModifierRectVertical.visible = False #hide the renderer
        self.boxModifierRectHorizontal.visible = False #hide the renderer

        self.server.select_annotation([]) # unselect all
        #also remove the renderer from the renderers
        self.remove_renderers(renderers=[self.boxModifierRectHorizontal,self.boxModifierRectVertical])

        self.logger.debug("box_modifier_hide")
        #self.boxModifierTool.renderers=[]

        #self.boxModifierData.data = {'x': [], 'y': [], 'width': [], 'height': [] }

    # this is called when we resize the plot via variable selection, mouse wheel etc
    def box_modifier_rescale(self):
        if self.boxModifierVisible == False:
            return
        anno = self.server.get_annotations()[self.boxModifierAnnotationName]
        if anno["type"] == "time":
            #adjust the limits to span the rectangles on full view area
            boxYCenter = int((self.plot.y_range.start + self.plot.y_range.end)/2)
            boxYHeight = (self.plot.y_range.end - self.plot.y_range.start)*4
            data = copy.deepcopy(self.boxModifierData.data)
            data['y'] = [boxYCenter, boxYCenter]
            data['height'] = [boxYHeight, boxYHeight]
            self.boxModifierData.data = data
        if anno["type"] == "threshold":
            boxXCenter = int((self.plot.x_range.start + self.plot.x_range.end) / 2)
            data = copy.deepcopy(self.boxModifierData.data)
            self.logger.debug(f" rescale box modifier {self.boxModifierData.data['x']} => {boxXCenter} {self.boxModifierData.data['x'][0]-boxXCenter}")
            data['x'] = [boxXCenter, boxXCenter]
            self.boxModifierData.data = data

    def box_modifier_modify(self):
        self.logger.debug(f"box_modifier_modify {self.boxModifierVisible}, now => {self.boxModifierData.data}")
        if self.boxModifierVisible == False:
            return False

        anno = self.server.get_annotations()[self.boxModifierAnnotationName]
        self.logger.debug(f" box_modifier_modify {anno}")


        if anno["type"] == "time":
            if self.boxModifierData.data['x'][1] <= self.boxModifierData.data['x'][0]:
                #end before start not possible
                self.logger.warning("box_modifier_modify end before start error")
                return False

            # re-center the y axis height to avoid vertical out-shifting
            boxYCenter = int((self.plot.y_range.start + self.plot.y_range.end) / 2)
            boxYHeight = (self.plot.y_range.end - self.plot.y_range.start) * 4
            self.boxModifierData.data['y'] = [boxYCenter, boxYCenter]
            self.boxModifierData.data['height'] = [boxYHeight, boxYHeight]

            #now modify it:
            # adjust the local value in the timeseries server,
            # correct the visible glyph of the annotation
            # push it back to the model

            # sanity check: end not before start
            anno["startTime"] = self.boxModifierData.data['x'][0]
            anno["endTime"] = self.boxModifierData.data['x'][1]
            self.server.adjust_annotations(self.boxModifierAnnotationName, anno)
            self.remove_renderers(deleteMatch=self.boxModifierAnnotationName)
            self.draw_annotation(self.boxModifierAnnotationName)
            #now also find the box glyph and tune it

        elif anno["type"] == "threshold":
            if self.boxModifierData.data['y'][1] <= self.boxModifierData.data['y'][0]:
                #end before start not possible
                self.logger.warning("box_modifier_modify min gt max error")
                return False
                # sanity check: end not before start
            #now move the box back in
            boxXCenter = int((self.plot.x_range.start + self.plot.x_range.end) / 2)
            self.boxModifierData.data['x'] = [boxXCenter, boxXCenter]

            anno["min"] = self.boxModifierData.data['y'][0]
            anno["max"] = self.boxModifierData.data['y'][1]
            self.server.adjust_annotations(self.boxModifierAnnotationName, anno)
            self.remove_renderers(deleteMatch=self.boxModifierAnnotationName)
            self.draw_threshold(self.boxModifierAnnotationName,anno['variable'])



        else:
            self.logger.error(f"we don't support annos of type {anno['type']}")
            return False



        return True


    def check_boxes(self):
        if self.boxModifierVisible:
            try:
                #self.logger.debug(self.boxData.data)
                #self.logger.debug(self.toolBarBox.toolbar.active_drag)

                if len(self.boxModifierData.data["x"]) != 2:
                    self.logger.warning("box modifier >2:  restore")
                    self.boxModifierData.data = copy.deepcopy(self.boxModifierOldData)


                new = json.dumps(self.boxModifierData.data)
                old = json.dumps(self.boxModifierOldData)
                if old!= new:
                    if not self.box_modifier_modify():
                        self.logger.warning("box modifier invalid,  restore")
                        self.boxModifierData.data = copy.deepcopy(self.boxModifierOldData)


                    self.boxModifierOldData = copy.deepcopy(self.boxModifierData.data)

            except Exception as ex:
                self.logger.error(f"check_boxes {ex}")


    def periodic_cb(self):
        """
            called periodiaclly by the bokeh system
            here, we execute function that modifiy bokeh variables etc via the dispatching list
            this is needed, as modifications to data or parameters in the bokeh objects
            are only possible withing the bokeh thread, not from any other.

            attention: make sure this functin does normally not last longer than the periodic call back period, otherwise
            bokeh with not do anything else than this function here

        """
        start = time.time()
        self.check_boxes()
        legendChange =  self.__legend_check() # check if a user has deselected a variable
        try: # we need this, otherwise the inPeriodicCb will not be reset

            #self.logger.debug("enter periodic_cb")

            executelist=[]
            with self.dispatchLock:
                if self.dispatchList:
                    executelist = self.dispatchList.copy()
                    self.dispatchList = []

            for fkt in set(executelist): # avoid double execution
                self.logger.info("now executing dispatched %s",str(fkt.__name__))
                fkt() # execute the functions which wait for execution and must be executed from this context

        except Exception as ex:
            self.logger.error(f"Error in periodic callback {ex}")

        if legendChange or executelist != []:
            self.logger.debug(f"periodic_cb was {time.time()-start}")

    def __get_free_color(self):
        """
            get a currently unused color from the given palette, we need to make this a function, not just a mapping list
            as lines come and go and therefore colors become free again

            Returns:
                a free color code

        """
        usedColors =  [self.lines[lin].glyph.line_color for lin in self.lines]
        for color in self.lineColors:
            if color not in usedColors:
                return color
        return "green" # as default




    def __plot_lines(self,newVars = None):
        """ plot the currently selected variables as lines, update the legend
            if newVars are given, we only plot them and leave the old
        """
        self.logger.debug("@__plot_lines")

        if newVars == None:
            #take them all fresh
            newVars = self.server.get_variables_selected()

        #first, get fresh data
        settings= self.server.get_settings()
        variables = self.server.get_variables_selected()
        #self.logger.debug("@__plot_lines:from server var selected %s",str(newVars))
        variablesRequest = variables.copy()
        variablesRequest.append("__time")   #make sure we get the time included
        #self.logger.debug("@__plot_lines:self.variables, bins "+str(variablesRequest)+str( settings["bins"]))
        if not self.streamingMode:
            getData = self.server.get_data(variablesRequest,self.rangeStart,self.rangeEnd,settings["bins"]) # for debug
        else:
            # avoid to send a different request between the streaming data requests, this causes "jagged" lines
            # still not the perfec solution as zooming out now causes a short empty plot
            getData = self.server.get_data(variablesRequest, -self.streamingInterval, None,
                                                            self.server.get_settings()["bins"])  # for debug
        #self.logger.debug("GETDATA:"+str(getData))
        if not getData:
            self.logger.error(f"no data received")
            return
        if newVars == []:
            self.data.data = getData  # also apply the data to magically update
        else:
            self.logger.debug("new column data source")
            if self.data is None:
                #first time
                self.data = ColumnDataSource(getData)  # this will magically update the plot, we replace all data
            else:
                #add more data
                for variable in getData:
                    if variable not in self.data.data:
                        self.data.add(getData[variable],name=variable)

        self.logger.debug(f"self.data {self.data}")
        timeNode = "__time"
        #now plot var
        for variableName in newVars:
            color = self.__get_free_color()
            self.logger.debug("new color ist"+color)
            if variableName != timeNode:
                self.logger.debug(f"plotting line {variableName}, is score: {self.server.is_score_variable(variableName)}")
                if self.server.is_score_variable(variableName):
                    self.lines[variableName] = self.plot.circle(timeNode, variableName, line_color="red", fill_color=None,
                                                  source=self.data, name=variableName,size=7)  # x:"time", y:variableName #the legend must havee different name than the source bug



                else:
                    self.lines[variableName] = self.plot.line(timeNode, variableName, color=color,
                                                  source=self.data, name=variableName,line_width=2)  # x:"time", y:variableName #the legend must havee different name than the source bug

                #we set the lines and glypsh to no change their behaviour when selections are done, unfortunately, this doesn't work, instead we now explicitly unselect in the columndatasource
                self.lines[variableName].nonselection_glyph = None  # autofading of not selected lines/glyphs is suppressed
                self.lines[variableName].selection_glyph = None     # self.data.selected = Selection(indices = [])

                self.legendItems[variableName] = LegendItem(label=variableName,renderers=[self.lines[variableName]])
                if self.showThresholds:
                    self.show_thresholds_of_line(variableName)


        #now make a legend
        #legendItems=[LegendItem(label=var,renderers=[self.lines[var]]) for var in self.lines]
        legendItems = [v for k,v in self.legendItems.items()]
        if not self.hasLegend:
            #at the first time, we create the "Legend" object
            self.plot.add_layout(Legend(items=legendItems))
            self.plot.legend.location = "top_right"
            self.plot.legend.click_policy = "hide"
            self.hasLegend = True
        else:
            self.plot.legend.items = legendItems #replace them

        self.adjust_y_axis_limits()


    def range_cb(self, attribute,old, new):
        """
            callback by bokeh system when the scaling have changed (roll the mouse wheel), see bokeh documentation
        """
        #we only store the range, and wait for an LOD or PANEnd event to refresh
        #self.logger.debug(f"range_cb {attribute}")
        if attribute == "start":
            self.rangeStart = new
        if attribute == "end":
            self.rangeEnd = new
        if self.streamingMode == True and not self.inStreamUpdate:
            self.userZoomRunning = True
        #print("range cb"+str(attribute),self.rangeStart,self.rangeEnd)
        #self.logger.debug(f"leaving range_cb with userzoom running {self.userZoomRunning}")

    def refresh_plot(self):
        """
            # get data from the server and plot the lines
            # if the current zoom is out of range, we will resize it:
            # zoom back to max zoom level shift
            # or shift left /right to the max positions possible
            # if there are new variables, we will rebuild the whole plot
        """
        self.logger.debug("refresh_plot()")
        #have the variables changed?

        #make the differential analysis: what do we currently show and what are we supposed to show?
        currentLines = [lin for lin in self.lines] #these are the names of the current vars
        backendLines = self.server.get_variables_selected()
        deleteLines = list(set(currentLines)-set(backendLines))
        newLines = list(set(backendLines)-set(currentLines))
        self.logger.debug("diffanalysis new"+str(newLines)+"  del "+str(deleteLines))


        #now delete the ones to delete
        for key in deleteLines:
            self.lines[key].visible = False
            del self.lines[key]
            del self.legendItems[key]
        #remove the legend
        legendItems = [v for k, v in self.legendItems.items()]
        self.plot.legend.items = legendItems
        #remove the lines
        self.remove_renderers(deleteLines)
        #remove the according thresholds if any
        for lin in deleteLines:
            self.remove_renderers(self.find_thresholds_of_line(lin))


        #create the new ones
        self.__plot_lines(newLines)

        #xxxtodo: make this differential as well
        if self.server.get_settings()["background"]["hasBackground"]:
            self.refresh_backgrounds()

        if self.server.get_settings()["hasHover"] not in [False,None]:
            self.__make_tooltips() #must be the last in the drawings

    def refresh_backgrounds_old(self):
        """ check if backgrounds must be drawn if not, we just hide them"""
        self.hide_backgrounds()
        if self.showBackgrounds:
            self.show_backgrounds()

    def refresh_backgrounds(self):
        # we show the new backgrounds first and then delete the old to avoid the short empty time, looks a bit better
        deleteList = []
        for r in self.plot.renderers:
            if r.name:
                if "__background" in r.name:
                    deleteList.append(r.name)
        if self.showBackgrounds:
            self.show_backgrounds()
        if deleteList:
            self.remove_renderers(deleteList=deleteList)


    def var_select_button_cb(self):
        """
            UI callback, called when the variable selection button was clicked
        """
        #apply the selected vars to the plot and the backend
        currentSelection = self.variablesMultiSelect.value
        #write the changes to the backend
        self.server.set_variables_selected(currentSelection)
        self.refresh_plot()


    def event_cb(self,event):
        """
            the event callback from the UI for any user interaction: zoom, select, annotate etc
            Args:
                event (bokeh event): the event that happened
        """

        eventType = str(event.__class__.__name__)
        msg = " "
        for k in event.__dict__:
            msg += str(k) + " " + str(event.__dict__[k]) + " "
        self.logger.debug("event " + eventType + msg)
        #print("event " + eventType + msg)

        if eventType in ["PanStart","Pan"]:
            if self.streamingMode:
                self.userZoomRunning = True # the user is starting with pannin, we old the ui updates during user pan

        if eventType == "PanEnd":
            #self.refresh_plot()
            if self.streamingMode:
                self.userZoomRunning = False # the user is finished with zooming, we can now push data to the UI again
            pass
        if eventType == "LODEnd":
            if self.streamingMode:
                self.userZoomRunning = False # the user is finished with zooming, we can now push data to the UI again
                # also update the zoom level during streaming
                self.streamingInterval = self.rangeEnd - self.rangeStart
            self.refresh_plot()

        if eventType == "Reset":
            self.reset_plot_cb()

        if eventType == "SelectionGeometry":
            #option = self.annotationButtons.active # gives a 0,1 list, get the label now
            #tags = self.server.get_settings()["tags"]
            #mytag = self.annotationTags[option]
            mytag =self.currentAnnotationTag
            #self.logger.info("TAGS"+str(self.annotationTags)+"   "+str(option))
            self.data.selected = Selection(indices=[])  # suppress real selection
            self.edit_annotation_cb(event.__dict__["geometry"]["x0"],event.__dict__["geometry"]["x1"],mytag,event.__dict__["geometry"]["y0"],event.__dict__["geometry"]["y1"])
        if eventType == "Tap":
            #self.logger.debug(f"TAP {self.annotationsVisible}, {event.__dict__['sx']}")
            #plot all attributes
            #self.logger.debug(f"legend {self.plot.legend.width}")
            self.box_modifier_tap(event.__dict__["x"],event.__dict__["y"]  )
            self.logger.debug(f"TAP")


        self.logger.debug(f"leave event with user zomm running{self.userZoomRunning}")
    def reset_plot_cb(self):
        self.logger.debug("reset plot")
        self.rangeStart = None
        self.rangeEnd = None
        self.box_modifier_hide() # reset the selection
        self.refresh_plot()


    def find_renderer(self,rendererName):
        for r in self.plot.renderers:
            if r.name:
                if r.name == rendererName:
                    return True
        return False

    def add_renderers(self,addList):
        self.plot.renderers.extend(addList)

    def remove_renderers(self,deleteList=[],deleteMatch="",renderers=[]):
        """
         this functions removes renderers (plotted elements from the widget), we find the ones to delete based on their name attribute
         Args:
            deletelist: a list or set of renderer names to be deleted
            deleteMatch(string) a part of the name to be deleted, all renderer that have this string in their names will be removed
            renderers : a list of bokeh renderers to be deleted
        """
        newRenderers = []
        if renderers == []:
            for r in self.plot.renderers:
                if r.name:
                    if r.name in deleteList:
                        self.logger.debug(f"remove_renderers {r.name}")
                        pass  # we ignore this one and do NOT add it to the renderers, this will hide the object
                    elif deleteMatch != "" and deleteMatch in r.name:
                        pass  # we ignore this one and do NOT add it to the renderers, this will hide the object
                    else:
                        newRenderers.append(r)  # we keep this one, as it doesnt mathc the deletersl
                else:
                    newRenderers.append(r)  # if we have no name, we can't filter, keep this
        else:
            for r in self.plot.renderers:
                if r in renderers:
                    pass # dont take this one
                else:
                    newRenderers.append(r)

        self.plot.renderers = newRenderers

    def annotation_toggle_click_cb(self,toggleState):
        """
            callback from ui for turning on/off the annotations
            Args:
                toggleState (bool): true for set, false for unset
        """
        if toggleState:
            self.showAnnotationToggle.label = "hide Annotations"
            self.show_annotations()
        else:
            #remove all annotations from plot
            self.showAnnotationToggle.label = "show Annotations"
            self.hide_annotations()

    def threshold_toggle_click_cb(self,toggleState):
        """
            callback from ui for turning on/off the threshold annotations
            Args:
                toggleState (bool): true for set, false for unset
        """
        if toggleState:
            self.showThresholdToggle.label = "hide Thresholds"
            self.showThresholds = True
            self.show_thresholds()
        else:
            #remove all annotations from plot
            self.showThresholdToggle.label = "show Thresholds"
            self.showThresholds = False
            self.hide_thresholds()

    def show_thresholds(self):
        """
            check which lines are currently shown and show their thresholds as well
        """
        if not self.showThresholds:
            return

        for annoName,anno in self.server.get_annotations().items():
            #self.logger.debug("@show_thresholds "+annoName+" "+anno["type"])
            if anno["type"]=="threshold":
                # we only show the annotations where the lines are also there
                self.logger.debug("@show_thresholds "+annoName+" "+anno["type"]+"and the lines are currently"+str(list(self.lines.keys())))
                if anno["variable"] in self.lines:
                    self.draw_threshold(annoName,anno["variable"])


    def hide_thresholds(self):
        """ hide the current annotatios in the widget of type time"""
        self.box_modifier_hide()
        annotations = self.server.get_annotations()
        timeAnnos = [anno for anno in annotations.keys() if annotations[anno]["type"]=="threshold" ]
        self.remove_renderers(deleteList=timeAnnos)
        pass


    def backgroundbutton_cb(self,toggleState):
        """
            event callback function triggered by the UI
            toggleStat(bool): True/False on toggle is set or not
        """
        if toggleState:
            self.backgroundbutton.label = "hide Backgrounds"
            self.showBackgrounds = True
            self.show_backgrounds(None)
        else:
            self.backgroundbutton.label = "show Backgrounds"
            self.hide_backgrounds()
            self.showBackgrounds = False



    def init_annotations(self):
        """
            chreate the actual bokeh objects based on existing annotations, this speeds up the process a lot when show
            ing the annotations later, we will keep the created objecs in the self.annotations list and apply it to
            the renderes later, this will only be used for "time" annotations, the others are called thresholds
        """
        self.annotations={}
        self.logger.debug(f"init {len(self.server.get_annotations())} annotations..")
        for annoname, anno in self.server.get_annotations().items():
            if "type" in anno and anno["type"] != "time":
                continue # ignore any other type
            self.draw_annotation(annoname,add_layout=False)
        #now we have all bokeh objects in the self.annotations
        self.logger.debug("init_annotations.. done")

    def show_annotations(self):
        self.plot.renderers.extend([v for k,v in self.annotations.items()])
        self.annotationsVisible = True



    def hide_annotations(self):
        """ hide the current annotatios in the widget of type time"""
        annotations = self.server.get_annotations()
        timeAnnos = [anno  for anno in annotations.keys() if annotations[anno]["type"]=="time" ]
        self.logger.debug("hide_annotations "+str(timeAnnos))
        self.remove_renderers(deleteList=timeAnnos)
        self.annotationsVisible = False
        self.box_modifier_hide()

    def get_layout(self):
        """ return the inner layout, used by the main"""
        return self.layout
    def set_curdoc(self,curdoc):
        self.curdoc = curdoc
        #curdoc().theme = Theme(json=themes.defaultTheme) # this is to switch the theme

    def remove_annotations(self,deleteList):
        """
            remove annotation from plot, object list and from the server
            modelPath(list of string): the model path of the annotation, the modelPath-node must contain children startTime, endTime, colors, tags
        """
        self.remove_renderers(deleteList=deleteList)
        self.server.delete_annotations(deleteList)
        for anno in deleteList:
            if anno in self.annotations:
                del self.annotations[anno]





    def draw_annotation(self, modelPath, add_layout = True):
        """
            draw one time annotation on the plot
            Args:
             modelPath(string): the path to the annotation, the modelPath-node must contain children startTime, endTime, colors, tags
        """
        try:
            self.logger.debug(f"draw_annotation  {modelPath}, add layout {add_layout}")
            annotations = self.server.get_annotations()

            if annotations[modelPath]["type"]!= "time":
                return # we only want the time annotations
            settings = self.server.get_settings()
            #now get the first tag, we only use the first
            tag = annotations[modelPath]["tags"][0]
            #if tag not in settings["tags"]:
            #    self.logger.warning(f"ignored tag {modelPath}, as {tag} is not in list of annotations: {settings['tags']}")
            #    return None

            try: # to set color and pattern
                if type(settings["colors"]) is list:
                    tagIndex = settings["tags"].index(tag)
                    pattern = None
                    color = settings["colors"][tagIndex]
                elif type(settings["colors"]) is dict:
                    color = settings["colors"][tag]["color"]
                    pattern = settings["colors"][tag]["pattern"]
                    if not pattern is None:
                        if pattern not in [" ",".","o","-","|","+",":","@","/","\\","x",",","`","v",">","*"]:
                            pattern = 'x'
            except:
                color = None
                pattern = None
            if not color:
                self.logger.error("did not find color for boxannotation")
                color = "red"

            start = annotations[modelPath]["startTime"]
            end = annotations[modelPath]["endTime"]

            infinity=1000000
            # we must use varea, as this is the only one glyph that supports hatches and does not create a blue box when zooming out
            #self.logger.debug(f"have pattern with hatch {pattern}, tag {tag}, color{color} ")
            if not pattern is None:
                newAnno = self.plot.varea(x=[start,end],
                                          y1=[-infinity,-infinity],
                                          y2=[infinity,infinity],
                                          fill_color=color,
                                          hatch_color="black",
                                          hatch_pattern=pattern,
                                          hatch_alpha=1,
                                          name=modelPath,
                                          fill_alpha=globalAlpha)
            else:
                #no pattern
                newAnno = self.plot.varea(x=[start, end],
                                          y1=[-infinity, -infinity],
                                          y2=[infinity, infinity],
                                          fill_color=color,
                                          name=modelPath,
                                          fill_alpha=globalAlpha)



            if not add_layout:
                self.remove_renderers(renderers=[newAnno])

            self.annotations[modelPath]=newAnno # put it in the annotation store for later

            if add_layout:
                #already added
                pass
            else:
                return newAnno
        except Exception as ex:
            self.logger.error("error draw annotation"+modelPath+" : "+str(ex))

        #this is an example for labelling
        #label = Label(x=((end-start)*0.25+start), y=50, y_units='screen', text=modelPath,text_font_size='0.8em', angle=3.1415/2)
        #self.plot.add_layout(label)


    def find_thresholds_of_line(self,path):
        """
            find the hreshold annotations that belong to a line given as model path
            Args:
                path: the path to the variable
            Returns:
                (list of strings of the threshold sannotations that belong to this variable
        """
        result = []
        for k,v in self.server.get_annotations().items():
            if v["type"] == "threshold":
                if v["variable"] == path:
                    result.append(k)
        self.logger.debug("@find_thresholds of line returns "+path+" => "+str(result))
        return result

    def show_thresholds_of_line(self,path):
        self.logger.debug("@show_threasholds_of_line "+path)
        thresholds = self.find_thresholds_of_line(path)
        for threshold in thresholds:
            self.draw_threshold(threshold,path)

    def hide_thresholds_of_line(self,path):
        thresholds = self.find_thresholds_of_line(path)
        self.remove_renderers(deleteList=thresholds)

    def draw_threshold(self, modelPath, linePath=None):
        """ draw the boxannotation for a threshold
            Args:
                 modelPath(string): the path to the annotation, the modelPath-node must contain children startTime, endTime, colors, tags
        """

        try:
            annotations = self.server.get_annotations()
            # now get the first tag, we only use the first
            tag = annotations[modelPath]["tags"][0]



            if linePath:
                color = self.lines[linePath].glyph.line_color
            else:
                color ="blue"

            min = annotations[modelPath]["min"]
            max = annotations[modelPath]["max"]
            if min>max:
                max,min = min,max # swap them

            # print("draw new anno",color,start,end,modelPath)

            newAnno = BoxAnnotation(top=max, bottom=min,
                                    fill_color=color,
                                    fill_alpha=globalAlpha,
                                    name=modelPath)  # +"_annotaion

            self.add_renderers([newAnno])
        except Exception as ex:
            self.logger.error("error draw threshold "+str(modelPath)+ " "+linePath+" "+str(ex))

    def make_background_entries(self, data, roundValues = True):
        """
            create background entries from background colum of a table:
            we iterate through the data and create a list of entries
            {"start":startTime,"end":time,"value":value of the data,"color":color from the colormap}
            those entries can directly be used to draw backgrounds
            Args:
                data: dict with {backgroundId: list of data , __time: list of data
                roundValue [bool] if true, we round the values to int, floats are not useful for table lookups
            Returns:
                list of dict entries derived from the data
        """
        backGroundNodeId = self.server.get_settings()["background"]["background"]
        colorMap = self.server.get_settings()["background"]["backgroundMap"]

        startTime = None
        backgrounds = []
        defaultColor = "grey"

        if roundValues:
            # round the values, it is not useful to have float values here, we use the background value
            # for lookup of coloring, so we need int
            self.logger.debug(f"before round {data[backGroundNodeId]}")
            data[backGroundNodeId]=[ round(value) if numpy.isfinite(value) else value for value in data[backGroundNodeId] ]
            self.logger.debug(f"after round {data[backGroundNodeId]}")


        for value, time in zip(data[backGroundNodeId], data["__time"]):
            # must set the startTime?
            if not startTime:
                if not numpy.isfinite(value):
                    continue  # can't use inf/nan
                else:
                    startTime = time
                    currentBackGroundValue = value
            else:
                # now we are inside a region, let's see when it ends
                if value != currentBackGroundValue:
                    # a new entry starts, finish the last and add it to the list of background
                    try:
                        color = colorMap[str(int(currentBackGroundValue))]
                    except:
                        color = defaultColor
                    entry = {"start": startTime, "end": time, "value": currentBackGroundValue, "color": color}
                    self.logger.debug("ENTRY" + json.dumps(entry))
                    backgrounds.append(entry)
                    # now check if current value is finite, then we can start
                    if numpy.isfinite(value):
                        currentBackGroundValue = value
                        startTime = time
                    else:
                        startTime = None  # look for the next start
        # now also add the last, if we have one running
        if startTime:
            try:
                color = colorMap[str(int(currentBackGroundValue))]
            except:
                color = defaultColor
            entry = {"start": startTime, "end": time, "value": currentBackGroundValue, "color": color}
            backgrounds.append(entry)

        return copy.deepcopy(backgrounds)


    def show_backgrounds(self,data=None):
        """
            show the current backgrounds
            Args:
                data(dict):  contains a dict holding the nodeid with of the background and the __time as keys and the lists of data
                    if te data is not given, we get the backgrounds fresh from the data server
        """

        self.logger.debug("__show backgrounds()")
        backGroundNodeId = self.server.get_settings()["background"]["background"]

        if not data:
            #we have to pick up the background data first
            self.logger.debug("get fresh background data from the model server %s",backGroundNodeId)
            bins = self.server.get_settings()["bins"]
            #bins = 30
            #bins = 30
            getData = self.server.get_data([backGroundNodeId], start=self.rangeStart, end=self.rangeEnd,
                                           bins=bins)  # for debug
            data = getData

        #now make the new backgrounds
        backgrounds = self.make_background_entries(data)
        #now we have a list of backgrounds
        self.logger.info("have %i background entries",len(backgrounds))
        #now plot them

        boxes =[]

        self.backgrounds=[]

        for back in backgrounds:
            name = "__background"+str('%8x'%random.randrange(16**8))
            newBack = BoxAnnotation(left=back["start"], right=back["end"],
                                    fill_color=back["color"],
                                    fill_alpha=globalAlpha,
                                    name=name)  # +"_annotaion
            boxes.append(newBack)
            back["rendererName"] = name
            self.backgrounds.append(back)  # put it in the list of backgrounds for later look up for streaming

        self.plot.renderers.extend(boxes)

    def hide_backgrounds(self):
        """ remove all background from the plot """
        self.remove_renderers(deleteMatch="__background")




    #called when the user dreates/removes annotations
    def edit_annotation_cb(self,start,end,tag,min,max):
        """
            call as a callback from the UI when a user adds or removes an annotation
            Args:
                start(float): the start time in epoch ms
                end (float): the end time in epoch ms
                tag (string): the currently selected tag by the UI, for erase there is the "-erase-" tag
        """
        self.logger.debug("edit anno %s %s %s",str(start),str(end),str(tag))
        if tag == '-erase-':
            #remove all annotations which are inside the time
            deleteList = []
            annotations=self.server.get_annotations()
            for annoPath,annotation in annotations.items():
                if annotation["type"] == "time":
                    if annotation["startTime"]>start and annotation["startTime"]<end:
                        self.logger.debug("delete "+annoPath)
                        deleteList.append(annoPath)
            #now hide the boxes
            self.remove_annotations(deleteList)
        elif tag =="-erase threshold-":
            # remove all annotations which are inside the limits are are currently visible
            deleteList = []
            annotations = self.server.get_annotations()
            currentThresholds = [] # the list of threshold annotation currently visible
            for r in self.plot.renderers:
                if r.name in annotations:
                    #this annotation is currenlty visible
                    if annotations[r.name]["type"] == "threshold":
                        #this annotation is a threshold
                        currentThresholds.append(r.name)

            #now check if we have to delete it
            deleteList =[]
            for threshold in currentThresholds:
                tMin = annotations[threshold]["min"]
                tMax = annotations[threshold]["max"]
                if tMin>tMax:
                    tMin,tMax = tMax,tMin
                if tMax<=max and tMax>=min: # we check against the top line of the annotation
                    #must delete this one
                    deleteList.append(threshold)
            # now hide the boxes
            self.logger.debug(f"deletelist {deleteList}")
            self.remove_renderers(deleteList=deleteList)
            self.server.delete_annotations(deleteList)


        elif "threshold" not in tag:
            #create a time annotation one

            newAnnotationPath = self.server.add_annotation(start,end,tag,type="time")
            #print("\n now draw"+newAnnotationPath)
            self.draw_annotation(newAnnotationPath)
            #print("\n draw done")
        else:
            #create a threshold annotation, but only if ONE variable is currently selected
            variables = self.server.get_variables_selected()
            scoreVariables = self.server.get_score_variables()
            vars=list(set(variables)-set(scoreVariables))
            if len(vars) != 1:
                self.logger.error("can't create threshold anno, len(vars"+str(len(vars)))
                return


            newAnnotationPath = self.server.add_annotation(start,end,tag,type ="threshold",min=min,max=max,var = vars[0] )
            self.draw_threshold(newAnnotationPath,vars[0])

    def session_destroyed_cb(self,context):
        # this still doesn't work
        self.id=self.id+"destroyed"
        self.logger.debug("SEESION_DETROYEd CB")
        print("DESTROYED")


if __name__ == '__main__':

    ts_server = TimeSeriesWidgetDataServer('http://localhost:6001/',"root.visualization.widgets.timeseriesOne")
    t=TimeSeriesWidget(ts_server)
