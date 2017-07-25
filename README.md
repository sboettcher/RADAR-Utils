# RADAR-Utils
Some smaller utilities for the RADAR-CNS project

## radar_api_monitor.py
A small python GUI tool for interfacing with the REST API @ [RADAR-RestApi/dev](https://github.com/RADAR-CNS/RADAR-RestApi/tree/dev).
Already includes the python API client generated at http://editor.swagger.io/

### Dependencies:
```
pip3 install numpy pyqtgraph pyqt5 urllib3 certifi six
```
- [**pyqtgraph**](http://www.pyqtgraph.org/): A python library for easy drawing of scientific graphs and small application GUIs. Based on Qt and numpy.
- [**pyqt5**](http://doc.qt.io/qt-5/qt5-intro.html): Qt is cross-platform application framework, used to draw the GUI elements. Dependency of *pyqtgraph*.
- [**urllib3**](https://urllib3.readthedocs.io/en/latest/): Powerful Python HTTP client library. Dependency of *swagger_client*.
- [**certifi**](https://pypi.python.org/pypi/certifi): Curated collection of Root Certificates for SSL authentication. Dependency of *swagger_client*.
- [**six**](https://pypi.python.org/pypi/six):  Python 2 and 3 compatibility library. Dependency of *swagger_client*.

### Installation:
- clone the repository to your local drive and `cd` into it
- in `swagger_client/configuration.py` change the line
``` python
self.host = "https://[host]/api"
```
to point to your local RADAR-RestApi endpoint. For example:
``` python
self.host = "https://example.server.com/api"
```
