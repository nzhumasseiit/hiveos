# Product

## Register

product

## Users

Beekeeping clients checking the health of their hives, plus the founding team
demoing the platform. Non-technical users on laptops (sometimes outdoors on
mobile). Primary job: glance at a hive and know in seconds whether it's fine
or needs a visit.

## Product Purpose

BEElive (HiveOS) is an IoT monitoring platform for smart beehives: ESP32 sensor
nodes → nRF24 radio → Raspberry Pi gateway → FastAPI backend → InfluxDB →
this dashboard. Success: a client trusts the numbers enough to skip a physical
hive inspection.

## Brand Personality

Warm, trustworthy, grounded. Honey/amber accent on a dark comb background is
the committed brand identity. Calm confidence, not tech bravado.

## Anti-references

- Generic AI-generated SaaS dashboards (numbered nav eyebrows, emoji-as-icons,
  glassmorphism everywhere, fake status rows).
- Anything that shows made-up data — client trust is the product; never render
  hardcoded "ONLINE / 4G Active" style placeholders.

## Design Principles

1. **Never lie to the client** — every status shown must come from the API.
2. **Glanceable first** — the last reading and its freshness beat dense charts.
3. **Honest empty states** — "no data yet from this hive" teaches, dashes confuse.
4. **Density with air** — readable at a glance on a 13" laptop without full-bleed sprawl.

## Accessibility & Inclusion

Body text ≥4.5:1 against the dark background. Reduced-motion alternative for
all animations. Status never conveyed by color alone (badge text accompanies it).
