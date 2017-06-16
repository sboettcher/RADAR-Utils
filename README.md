# RADAR-Utils
Some smaller utilities for the RADAR-CNS project

## radar_api_monitor.py
A small python GUI tool for interfacing with the REST API @ [RADAR-RestApi/dev](https://github.com/RADAR-CNS/RADAR-RestApi/tree/dev)
### Dependencies:
```
pip3 install numpy certifi pyqt5 pyqtgraph
```
### Installation:
- Go to http://editor.swagger.io/
- `File > Import URL > http://radar-restapi.eu-west-1.elasticbeanstalk.com/api/swagger.json > OK`
- In the left pane edit value of `host` to your API URL
- In the left pane edit value of `schemes` to `https`
- `Generate Client > python`
- Unzip the generated folder into this directory
- (optional) in `python-client/swagger_client/configuration.py` change `self.verify_ssl` to `False`
- copy `cp -r python-client/swagger_client .`

As far as I can tell there is currently an issue in the swagger generation, to fix it run exactly:
```
sed -ie "/return_data\ =\ None/s/None/self.deserialize\(response_data,\"object\"\)/" swagger_client/api_client.py
```

## radar_data_viz.py
Tool for visualizing raw data extracted/restructured from the HDFS ([Restructure-HDFS-topic/dev](https://github.com/RADAR-CNS/Restructure-HDFS-topic/tree/dev)).
### Dependencies:
```
pip3 install numpy matplotlib
```

