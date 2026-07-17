# ORVIBO Cloud for Home Assistant

An experimental Home Assistant custom integration for the cloud account used by
ORVIBO HomeMate and ZhiJia365.

## Current scope

- Discovers the regional ORVIBO endpoint.
- Authenticates with `/getOauthToken`.
- Retrieves and verifies the account family list.
- Downloads the current app's full device table through
  `/v2/cmd/app/readtable`, lets the user select which devices to add, and only
  registers the selected devices in the Home Assistant Device Registry.
- Assigns each selected device to its discovered ORVIBO room by default and
  allows choosing another Home Assistant area during setup or later from the
  integration's configuration dialog.
- Controls verified curtain motors and color-temperature lights through the
  ORVIBO mutual-TLS binary cloud on port `10002`.
- Supports multiple-family selection and Home Assistant reauthentication.
- Exposes cloud connectivity, selected family, and device count as diagnostic
  entities.
- Never stores the plaintext password. The uppercase MD5 credential required by
  ORVIBO is stored instead and must be treated as password-equivalent.
- Keeps the separate binary-session password returned by `readtable` in memory
  only; it is excluded from diagnostics and object representations.

This version registers the Giant Eye 2K S1 when ORVIBO includes it in the account
device list, but does **not** expose it as a `camera` entity. Packet captures show
that its video uses Meari's encrypted ICE/P2P protocol rather than RTSP or ONVIF.

## Installation

Copy `custom_components/orvibo_cloud` into your Home Assistant configuration:

```text
config/
  custom_components/
    orvibo_cloud/
```

Restart Home Assistant, then open **Settings > Devices & services > Add
integration** and search for **ORVIBO Cloud**.

For HACS, add this repository as a custom integration repository after publishing
it to GitHub.

## Protocol notes

The observed login sequence is:

1. `GET https://<region>.orvibo.com/getOauthToken`
2. `POST https://<region>.orvibo.com/v2/family/statistics/users`
3. Mutual-TLS binary connection to port `10002` for verified device commands
4. Separate Meari cloud and encrypted P2P sessions for S1 video

Device discovery is read-only and comes from the REST table snapshot. Control is
enabled only for packet-capture-verified profiles: type-34 curtains support open,
close, stop, and position; type-38/subtype-6 lights support power, brightness, and
color temperature. Camera video requires another, independent Meari implementation.

## Security

- Do not log OAuth responses or the saved password hash.
- Treat a diagnostics export as private even though credentials are redacted.
- Port `10002` uses a legacy ORVIBO client certificate and private key that are
  already published by the acknowledged MIT project. Do not reuse them for any
  service other than your own ORVIBO account integration.
- This is an unofficial integration and may stop working if ORVIBO changes its
  private API.

## Verification

Run the dependency-free protocol tests with:

```powershell
python -m unittest discover -s tests -v
```

## Acknowledgements

Protocol behavior was cross-checked against packet captures and the MIT-licensed
[`orvibo-homeassistant-curtains`](https://github.com/kjanko/orvibo-homeassistant-curtains)
project.

## License

MIT
