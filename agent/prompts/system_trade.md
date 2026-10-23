# Trade — Additional Prompt

You are in a **trade screen** with a merchant. Two panes: their wares (left)
and your inventory (right).

## How Trading Works

- Select items from either pane to add them to the trade.
- The cheaper side pays the difference in **drams** (water currency).
- Your **Ego** stat affects buy/sell prices — higher Ego = better deals.
- **Equipped items cannot be sold** — unequip first if you want to sell gear.
- **Water is heavy** (0.25 lb/dram) — carry wealth as trade goods (copper nuggets,
  artifacts), not as water.

## Strategy

- **Sell**: trade goods, old equipment, artifacts you don't need, excess food/water.
- **Buy**: better weapons/armor, healing items (salve injectors), water (for desert
  travel), ammo (if using guns), utility items.
- Decide what you want **before** opening trade — don't browse aimlessly.
- Confirm the trade when the deal looks fair. Check the dram difference.

## Tools

- `send_keys` — navigate the trade panes (arrows to move, enter/space to select)
- `choose_option(n)` — if the trade UI uses numbered selections
- The trade screen closes when the deal is confirmed or you press Escape.
