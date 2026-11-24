# todoist

Personal Todoist automation.

Tokens live in the macOS Keychain, never in this repo:

| Keychain service | Token |
|---|---|
| `todoist-api` | Todoist: Settings → Integrations → Developer |
| `jira-api` | Jira: https://id.atlassian.com/manage-profile/security/api-tokens |

Store one with `security add-generic-password -a "$USER" -s <service> -w` (prompts for the value).

## jira-sync

Hourly one-way sync of Jira tickets assigned to me into the Todoist `tickets` project. Behavior is described in the docstring of `jira-sync/sync.py`.

Install the schedule (runs hourly and at login):

```sh
ln -s "$PWD/jira-sync/com.jbradbeer.jira-todoist-sync.plist" ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jbradbeer.jira-todoist-sync.plist
```

Run once by hand: `jira-sync/sync.py`. Logs: `~/Library/Logs/jira-todoist-sync.log`.
