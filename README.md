# Retry HA (Home Assistant Custom Integration)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/default)
[![Validate](https://github.com/SekulaTomasz/retry-action-HA/actions/workflows/validate.yml/badge.svg)](https://github.com/SekulaTomasz/retry-action-HA/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Retry HA** is a robust Home Assistant custom integration that wraps any service/action call with automatic retries, exponential backoff, target state verification, and comprehensive error handling.

Eliminate automation failures caused by:
- Flaky Zigbee / Z-Wave / RF / Wi-Fi devices that occasionally miss commands.
- Devices that acknowledge commands but fail to physically change state.
- Transient network or cloud API timeouts (e.g. REST commands, webhooks, voice notifications).

---

## Features

- 🔄 **Universal Action Wrapper**: Retries any Home Assistant action (e.g. `light.turn_on`, `switch.toggle`, `rest_command.sync`, `notify.mobile_app`, `script.*`).
- ⏱️ **Exponential Backoff & Delay Caps**: Configure initial delay, multiplier factor (`backoff`), and max delay ceiling to avoid spamming devices.
- 🎯 **State Verification (`expected_state`)**: Verifies that the target entity actually reaches the expected state (e.g. `expected_state: "on"`) before marking the attempt as successful.
- 🛡️ **Fallback Actions (`on_error`)**: Execute alternative actions (send alerts, sound buzzers, flip backups) if all retries are exhausted. The failure message is available via `{{ error }}`.
- 🔧 **Home Assistant Repairs Integration**: Optionally create persistent repair tickets in Home Assistant when critical actions repeatedly fail, auto-dismissed on future success.
- 📊 **Response Data Support**: Fully compatible with Home Assistant's `response_variable`.
- 🎛️ **Modern HA UI & Selectors**: Works seamlessly in both the visual automation editor and YAML scripts.
- ⚙️ **Configurable Global Defaults**: Adjust default retries and delay settings via **Settings -> Devices & Services -> Configure**.

---

## Installation

### Method 1: Via HACS (Recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance.
2. In Home Assistant, open **HACS** -> **Integrations**.
3. Click the **3 dots** (top right) and select **Custom repositories**.
4. Enter the repository URL:
   ```text
   https://github.com/SekulaTomasz/retry-action-HA
   ```
5. Select **Integration** as the Category, then click **Add**.
6. Find **Retry HA** in the integration list and click **Download**.
7. Restart Home Assistant.
8. Go to **Settings** -> **Devices & Services** -> **Add Integration** and search for **Retry HA**.

### Method 2: Manual Installation

1. Download the `retry_ha` folder from `custom_components/retry_ha` in this repository.
2. Copy `retry_ha` into your Home Assistant `<config>/custom_components/` directory:
   ```text
   config/
   └── custom_components/
       └── retry_ha/
           ├── __init__.py
           ├── config_flow.py
           ├── const.py
           ├── manifest.json
           ├── services.yaml
           └── translations/
               └── en.json
   ```
3. Restart Home Assistant.
4. Go to **Settings** -> **Devices & Services** -> **Add Integration** -> **Retry HA**.

---

## Action Reference (`retry_ha.call` / `retry_ha.action`)

The integration registers two identical service actions:
- `retry_ha.call`
- `retry_ha.action` (modern HA 2024+ alias)

### Parameters

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `action` | `string` / `dict` / `list` | **Required** | The action/service to execute (e.g. `light.turn_on`, `switch.turn_off`). Can also be a full action dictionary. |
| `target` | `target` / `dict` | `None` | Target `entity_id`, `device_id`, or `area_id`. |
| `data` | `dict` | `{}` | Parameters to pass into the target action (e.g. `brightness: 255`). |
| `retries` | `integer` | `3` | Maximum number of retry attempts after initial failure. |
| `delay` | `float` | `1.0` | Initial delay in seconds before the first retry attempt. |
| `backoff` | `float` | `2.0` | Multiplier for subsequent retry delays (`delay * (backoff ^ attempt)`). Set to `1.0` for constant delay. |
| `max_delay` | `float` | `60.0` | Maximum cap on retry delay in seconds. |
| `expected_state` | `string` / `list` | `None` | Verifies target entity changes to this state before considering call successful. |
| `expected_state_timeout`| `float` | `2.0` | Seconds to wait for target entity to reach `expected_state`. |
| `on_error` | `action` / `list` | `None` | Actions to run if all retry attempts fail. Context variable `{{ error }}` contains the failure details. |
| `raise_on_failure` | `boolean` | `false` | If `true`, raises `HomeAssistantError` stopping the automation. If `false`, logs warning and continues. |
| `create_repair` | `boolean` | `false` | If `true`, creates a persistent issue in Home Assistant's Repairs dashboard upon failure. |

---

## Examples

### 1. Basic Retry for a Flaky Smart Switch

Retry turning on a plug up to 3 times with a 2-second delay between attempts:

```yaml
action: retry_ha.call
data:
  action: switch.turn_on
  target:
    entity_id: switch.garden_pump
  retries: 3
  delay: 2.0
```

---

### 2. State Validation (Ensure Light Actually Turned On)

Some mesh devices report success to HA but fail to illuminate. `expected_state` checks that the entity transitioned to `"on"`:

```yaml
action: retry_ha.call
data:
  action: light.turn_on
  target:
    entity_id: light.living_room_ceiling
  data:
    brightness_pct: 100
  expected_state: "on"
  expected_state_timeout: 3.0
  retries: 4
  delay: 1.5
```

If `light.living_room_ceiling` is still `"off"` after 3 seconds, `retry_ha` treats it as a failure and re-executes `light.turn_on`!

---

### 3. Exponential Backoff for Webhooks or Cloud APIs

Retry an external API call with exponential backoff (2s -> 4s -> 8s -> 16s...):

```yaml
action: retry_ha.call
data:
  action: rest_command.trigger_webhook
  data:
    payload: "arming_alarm"
  retries: 4
  delay: 2.0
  backoff: 2.0
  max_delay: 30.0
```

---

### 4. Fallback Notification on Persistent Failure (`on_error`)

If all retries fail, execute an alternative action and include the error message:

```yaml
action: retry_ha.call
data:
  action: cover.close_cover
  target:
    entity_id: cover.garage_door
  expected_state: "closed"
  expected_state_timeout: 15.0
  retries: 3
  delay: 5.0
  create_repair: true
  on_error:
    - action: notify.mobile_app_phone
      data:
        title: "⚠️ Garage Door Alert"
        message: "Garage door failed to close after retries! Error: {{ error }}"
```

---

### 5. Using Response Data in Scripts

Capture the response from services that return data:

```yaml
sequence:
  - action: retry_ha.call
    data:
      action: weather.get_forecasts
      target:
        entity_id: weather.home
      data:
        type: daily
    response_variable: weather_forecast
  - action: notify.mobile_app_phone
    data:
      message: "Weather received: {{ weather_forecast.response['weather.home'].forecast[0].condition }}"
```

---

## Running Tests

You can run the included unit tests locally with Python 3.11+:

```bash
python -m unittest discover -s tests -v
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
