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
- `./radar_api_monitor.py`
