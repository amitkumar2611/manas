# MANAS — Memory (Layer 40)

## TIERS
1. working      — current task scratchpad (in-process, evictable)
2. conversation — dialog history, summarized on overflow
3. episodic     — what happened (events, actions, outcomes)
4. semantic     — distilled facts, preferences, projects, relationships
5. knowledge    — indexed external corpus (repos, docs, tickets, transcripts)

## RECORD SCHEMA
{id, tier, content, embedding?, importance(0-1), created, last_access,
 access_count, source, links[], version}

## RULES
- Write-through: episodic is append-only; semantic is versioned, never
  destructively edited.
- Retrieval = recency * importance * similarity (weights configurable).
- Curator agent periodically: summarizes, compresses, promotes episodic →
  semantic, and decays importance. Never deletes without an audit record.
- Personal memory and enterprise memory are separate stores with separate
  encryption keys. Cross-store queries require explicit scope grant.
