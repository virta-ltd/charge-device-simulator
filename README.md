# Device Simulator
## How to use
Please read the README.md file inside `how-to-use` folder

## Development
Simulators are developed using `Python 3.7`. You can:

+ Open the root folder your editor of choice (`PyCharm` or `VS Code` are suggested ones)
+ Create your virtual env (suggested method compared to system-wide python)
+ Run `pip3 install requirements.txt` manually or use your IDE to do so
+ Inside `debug` folder you can find two versions for test/debug:
    + With `python3 ./playground.py` you can debug/test using python interpreter
    + With `python3 ./simulator-executor.py --config=debug/config.yaml --simulation=sim1` 
    you can test the easy to use simulator executor used for docker image 
    + With `docker-compose` you can build and run a live image of your code with: `docker-compose --build up`

### Conventions and Rules
+ Use all default python conventions (naming, ...) - default PyCharm profile
+ Create abstract functions for devices and simulator,
 then implement them per case (protocol,...) 
+ Keep the compatibility
