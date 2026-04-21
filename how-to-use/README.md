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

# Available flows

| Flow | Description |
|------|-------------|
| `heartbeat` | Sends periodic heartbeat messages to the server |
| `authorize` | Sends periodic authorize requests |
| `charge` | Runs a full charging session (authorize, start, meter values, stop) |
| `preparing` | Keeps the charger in OCPP PREPARING state by periodically sending a StatusNotification. Simulates a charger with a cable always plugged in. Skips if a charge is already in progress. When active, charge sessions end with Preparing instead of Available. Useful for chargers that should accept remote-start sessions without ever going back to Available. |

## Example: charger waiting for remote start
A common setup is `heartbeat` + `preparing` — the charger stays in PREPARING and only charges when triggered by a RemoteStartTransaction from the server:
```yaml
frequent_flows:
  - flow: heartbeat
    delay_seconds: 30
    count: -1
  - flow: preparing
    delay_seconds: 60
    count: -1
```