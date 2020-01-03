# How to use
It's very simple:

+ Make sure you have `docker` and `docker-compose` in your system
+ Copy this folder anywhere you like (part of some other repo or ...)
+ Edit the `config.yaml` file and fill it with your simulations and devices (next section help)
+ If you provide a name other than `sim1` for your simulation inside `config.yaml`
then edit `docker-compose.yml` file and change `--simulation=sim1` to  
`--simulation=YOUR_SIMULATION_NAME` under `command` section 
+ Run `docker-compose up` in your folder
+ See simulation logs while it's running :)

# config.yaml
Here you define devices with their specs and simulation to be run.  
Check the comments inside the config.yaml file to see available options