# Triage Labels

These labels are used by the `triage` skill to move issues through the triage state machine.

| Role | Label string | Meaning |
|------|-------------|---------|
| Needs evaluation | `needs-triage` | Maintainer needs to evaluate this issue |
| Waiting on reporter | `needs-info` | Blocked — need more info from the submitter |
| AFK-agent-ready | `ready-for-agent` | Fully specified; an agent can pick it up with no human context |
| Human-ready | `ready-for-human` | Needs a human to implement |
| Won't action | `wontfix` | Will not be addressed |

## GitHub label setup

Run once to create these labels in the repo:

```bash
gh label create needs-triage --color "e4e669" --description "Maintainer needs to evaluate"
gh label create needs-info --color "d93f0b" --description "Waiting on reporter"
gh label create ready-for-agent --color "0075ca" --description "AFK-agent-ready"
gh label create ready-for-human --color "008672" --description "Ready for human implementation"
gh label create wontfix --color "ffffff" --description "Will not be actioned"
```
