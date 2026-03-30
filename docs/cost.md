# Cost Breakdown

## Monthly Cost

| Service | Cost | Notes |
|---|---|---|
| Hetzner CX23 | EUR3.49 (~$3.80) | 2 vCPU x86, 4 GB RAM, 40 GB SSD |
| Cloudflare Free | $0 | CDN, DNS, Pages, WAF, 100K Workers/day |
| Cloudflare R2 | $0 (MVP) | 10 GB storage free, 1M Class B ops free. $0.015/GB/mo + $0.36/M Class A ops after. |
| Domain | ~$12/year (~$1/mo) | .com registration |
| **Total** | **~$5/mo** | No free tier expiration. Stable from day 1. |

## Comparison to AWS Architecture

| | AWS (Year 1) | AWS (Year 2+) | Hetzner + Cloudflare |
|---|---|---|---|
| Monthly cost | $0 (free tier) | $30-35 | ~$5 |
| Annual cost | $0 | $360-420 | ~$60 |
| Free tier expiration | Yes (12 months) | -- | No |
| RAM available | 1 GB | 1 GB | 4 GB |

The AWS architecture was cheaper in Year 1 due to the free tier, but cost 6-7x more from Year 2 onward. The Hetzner setup costs ~$5/mo from day one with no cliff.

## Cost Traps to Avoid

- **Hetzner snapshots:** $0.012/GB/mo if enabled. Use `pg_dump` + R2 instead of server snapshots for backups.
- **R2 Class A operations (PUT/POST):** $4.50/million. Only matters at scale -- pipeline writes are <10K/week.
- **Hetzner traffic:** 20 TB/mo included. A county-level civic tool will never approach this.
- **Domain auto-renewal:** Set a calendar reminder. Losing a domain is the one cost trap that actually hurts.

## When to Upgrade

| Trigger | Action | New Cost |
|---|---|---|
| Memory > 80% sustained | CX23 --> CX33 (4 vCPU, 8 GB) | EUR6/mo |
| Disk > 80% | Add Hetzner volume (EUR0.052/GB/mo) | +EUR2-5/mo |
| R2 > 10 GB | Pay-as-you-go ($0.015/GB/mo) | +$0.15-0.75/mo |

Resize is done in the Hetzner console with ~2 minutes downtime. No architecture changes needed.
