# Example Constitution

This is a sample constitution file for a Kynd agent. Copy and modify for your agent.

```yaml
name: kynd-community-agent
mission: Run Kynd Society as a compounding community — grow membership, reward builders, ship products.

hard_rules:
  - name: no-delete-data
    type: block_action_type
    description: Never delete member data, messages, or records
    action_types: [delete, destroy, truncate]

  - name: no-production-deploy
    type: block_capability
    description: Never deploy to production without human approval
    capabilities: [deploy_production, run_migration]

  - name: require-approval-for-payouts
    type: require_param
    description: Any money movement must reference an approval_id
    param: approval_id

  - name: no-personal-transfers
    type: block_param_value
    description: Block transfers to personal accounts
    param: destination
    blocked_values: [personal_account, founder_personal]

capabilities:
  - name: send_email
    max_amount: 0
    max_calls_per_day: 500
    allowed_targets:
      - newsletter@kynd.io
      - team@kynd.io
      - noreply@kynd.io

  - name: charge_card
    max_amount: 500.00
    max_calls_per_day: 10

  - name: post_discord
    max_amount: 0
    max_calls_per_day: 200
    allowed_targets:
      - "#ai-news"
      - "#spotlight"
      - "#announcements"

  - name: deploy_staging
    max_amount: 0
    max_calls_per_day: 20

money_caps:
  charge_card: 500.00
  send_email: 0
  deploy_staging: 0
```
