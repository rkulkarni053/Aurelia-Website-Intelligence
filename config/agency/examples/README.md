# Agency Brain training examples (few-shot)

These JSON files are **approved gold answers**. Brain and Design chat load them via `feedback_store.load_examples` and inject them into prompts so local models copy **your agency voice** — not generic SEO spam.

## How “training” works here

1. Add / edit `*.json` examples in this folder (`approved_example: true`).
2. Optionally record live edits under `data/agency/feedback/` (same shape).
3. Brain uses them as few-shot when the LLM runs, and as industry templates when profile-first (CPU) skips the LLM.

This is **not** weight fine-tuning. It is the practical training loop for Aurelia on local hardware.

## Example kinds

| `kind` | Used for |
|---|---|
| `brain_recommendation` | Full Brain JSON voice (preferred) |
| `executive_summary` | Short pitch voice |
| `content_suggestions` | Hero / CTA copy patterns |
| `opportunity_rewrite` | Client-facing opportunity titles |
| `chat_reply` | Design / advisory chat tone |

## External references used for seed examples

- [EVP Malta site](https://evp-website-one.vercel.app/) — studio voice, CTA “Start a project”, benefit-led hero
- [Base44](https://www.base44.com/) — outcome headline, clear product sections, specific CTAs
- [Over Exposed](https://overexposed.tv/) — OB / live-stream capability + proof
- [Outside Broadcast UK](https://outsidebroadcast.uk/) — plain “what you get” + next step
- [Conte Studios — clarity in copy](https://contestudios.com/clarity-in-business-copywriting/) — outcome headlines, specific CTAs (not “Learn more”)
