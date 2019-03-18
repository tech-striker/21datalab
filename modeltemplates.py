timeseriesWidget = [
    {"name":"selectableVariables","type":"referencer"},
    {"name":"selectedVariables","type":"referencer"},
    {"name":"startTime","type":"variable"},
    {"name":"endTime","type":"variable"},
    {"name":"bins","type":"const","value":300},
    {"name":"hasAnnotation","type":"const","value":True,"children":[
             {"name":"annotations","type":"referencer"},
             {"name":"newAnnotations","type":"folder"},
             {"name":"tags","type":"const","value":["one","two"]},
             {"name":"colors","type":"const","value":["yellow","brown","grey","green","red"]},
        ]
    },
    {"name":"table","type":"referencer"},
    {"name":"lineColors","type": "const", "value": ["blue", "yellow", "brown", "grey", "red"]},
    {"name":"observer","type":"referencer"},
    {"name":"observerUpdate","type": "const","value":["line","background","annotations"]},
    {"name":"buttons","type":"folder","children":[
        {"name":"button1","type":"folder"}
    ]},
    {"name":"hasBackground","type": "const", "value": True},
    {"name":"background","type":"referencer"},
    {"name":"backgroundMap","type": "const", "value": {"1": "red", "0": "green", "-1": "blue", "default": "white"}}
]

button=[
    {"name":"caption","type":"const","value":"learn"},
    {"name":"counter","type":"variable"},
    {"name":"onClick","type":"referencer"}]