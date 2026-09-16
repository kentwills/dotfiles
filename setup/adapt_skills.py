#!/usr/bin/env python3
"""Generate Codex-native manager skills without vendoring private source text."""

import argparse
import json
from pathlib import Path
import shutil

DESCRIPTIONS = {
    'em-promotion-reviewer': 'Review EM promotion packets or selected subdimensions against the target management-level rubric; identify evidence gaps and draft targeted questions. Not for IC packets.',
    'ic-promotion-reviewer': 'Review IC engineering promotion packets or selected subdimensions against the target IC-level rubric; identify evidence gaps and draft targeted questions. Not for management packets.',
    'pep-reviewer': 'Review Product Engineering Proposals against the proposal template, scoped to the requested stage or sections; identify substantive gaps and draft concise questions.',
    'review-packet': 'Route a promotion packet or Product Engineering Proposal to the appropriate specialized reviewer. Use when the document type or promotion track has not been specified.',
    'promo-eval': 'Evaluate the quality of promotion-review output using a supplied scoring rubric. Use for explicit review-quality evaluation, not routine promotion review.',
    'writing-style': 'Write and revise flowing professional prose while preserving meaning and uncertainty. Use for strategy documents, proposals, and professional writing.',
}

ACCESS = '''## Documents and tools

Use supplied text or local files directly. For document URLs, use the authenticated
document/search connectors available in this Codex session. Discover their actual
tool names rather than assuming Claude-specific MCP methods exist. If access is
unavailable, identify the missing source and continue with the supplied evidence;
request the text only when its absence prevents the requested review.

Separate observed evidence from inference. Do not claim to have read linked
artifacts, comments, or live definitions that the tools did not return. Current
authoritative definitions supplied by the user or retrieved through an available
internal-code connector take precedence over the bundled snapshot. Identify the
version used. If caching is useful, use the user's cache directory, not a Claude
configuration directory, and do not let a cache replace the requested source.

State the target, scope, and material assumptions briefly and proceed when clear.
Ask only about ambiguities that change the review, such as conflicting target
levels. Do not pause for a blanket confirmation of already supplied information.
Draft feedback in chat or local files. Posting comments, editing source documents,
uploading files, or changing sharing settings requires authorization for that
external action; a request to review alone is not authorization to publish it.
'''

REVIEW = '''## Review

Read [the domain guide](references/guide.md) for exact definitions, evidence
criteria, and examples. Apply only the requested track, level, sections, and stage.
Do not add requirements beyond the applicable definition or turn a heuristic into
a mandatory criterion. Missing evidence is not proof of missing capability.

Map each material gap to an exact criterion and the evidence actually provided.
Distinguish scope and ownership from demonstrated outcomes. Check existing comments
when accessible and avoid duplicating an already answered question. For each gap,
give a short observation and a precise, answerable question, prioritized by impact.
For a partial packet, do not flag unprovided sections as missing from the full packet.
Template and word-count observations should reflect the supplied document and
verified template, not a fixed subtraction assumed to match every packet.

Read [writing-style](../writing-style/SKILL.md) when drafting substantial prose.
Keep the final response focused on useful feedback, with references to the relevant
section or evidence. Do not turn a review into an employment decision.
'''


def between(text, start, end=None):
    if start not in text or (end is not None and end not in text):
        raise ValueError(f'Private skill structure changed; review adapter boundary: {start!r}')
    result = text[text.index(start):]
    return result[:result.index(end)].strip() if end else result.strip()


def skill_body(source, name):
    text = (source / 'skills' / name / 'SKILL.md').read_text()
    parts = text.split('---', 2)
    if len(parts) != 3 or not text.startswith('---\n'):
        raise ValueError(f'Invalid source skill frontmatter: {name}')
    return parts[2].strip()


def generate(source, output):
    source, output = Path(source), Path(output)
    # Read and validate the complete input set before writing any output.
    bodies = {name: skill_body(source, name) for name in DESCRIPTIONS}
    for name, description in DESCRIPTIONS.items():
        destination = output / name
        destination.mkdir(parents=True, exist_ok=True)
        heading = '# ' + name.replace('-', ' ').title() + '\n\n'
        guide = None
        if name in ('em-promotion-reviewer', 'ic-promotion-reviewer'):
            guide = between(bodies[name], '## Level Scope Guidelines', '## Review Process')
            guide += '\n\n' + between(bodies[name], '## Heuristics & Edge Cases')
            body = heading + ACCESS + '\n' + REVIEW
            source_heading = '**If Sourcegraph MCP is available**'
            if source_heading in bodies[name]:
                live_source = between(bodies[name], source_heading, 'Before evaluating')
                live_source = live_source.replace(
                    '**If Sourcegraph MCP is available**, fetch the live level definitions before evaluating:',
                    '# Authoritative definition source\n\nUse an available authenticated internal-code connector to retrieve these definitions:'
                ).replace('~/.claude/cache/', '~/.cache/codex/')
                references = destination / 'references'
                references.mkdir(exist_ok=True)
                (references / 'definition-source.md').write_text(live_source + '\n')
                body += '\nFor live definition lookup and cache provenance, read [the source details](references/definition-source.md).\n'
        elif name == 'pep-reviewer':
            guide = between(bodies[name], '## Review Process')
            body = heading + ACCESS + '\n' + REVIEW + '''
Check proposal structure and named decision owners against the provided template.
Respect problem-only, solution, and full-review requests. Do not treat empty
post-experiment results or retrospective sections as gaps at proposal stage.
'''
        elif name == 'writing-style':
            guide = bodies[name].split('## Integration', 1)[0].strip()
            body = heading + '''Use [the writing guide](references/guide.md) to revise professional prose.
Preserve the author's meaning, factual qualifications, uncertainty, and requested
format. Apply the relevant guidance rather than forcing every document into an
executive-summary template. Other specialized skills are optional, not dependencies.
'''
        elif name == 'review-packet':
            body = heading + ACCESS + '''
## Route the document

Read enough to distinguish an EM promotion packet, an IC promotion packet, and a
Product Engineering Proposal. Prefer explicit target-level and track labels over
inference from section names. Ask a focused question only if the track or target
cannot be determined reliably.

- Management packet: read [em-promotion-reviewer](../em-promotion-reviewer/SKILL.md).
- IC packet: read [ic-promotion-reviewer](../ic-promotion-reviewer/SKILL.md).
- Proposal: read [pep-reviewer](../pep-reviewer/SKILL.md).

Apply the selected skill to the already retrieved content. Reading a sibling skill
file is sufficient; no Claude `Skill` tool or delegated agent is required.
For another document type, follow the user's request without inventing a packet review.
'''
        else:
            body = heading + ACCESS + '''
## Evaluate review quality

Distinguish the packet's claimed levels from scores assigned to review quality.
Split the requested scope into subdimension units, retaining the claimed score,
evidence, existing comments when available, and the actual reviewer output.
Read the applicable sibling EM or IC skill if generating a review is part of the
request. Do not describe a self-review as an independent evaluation.

Use [the rubric availability note](references/eval-rubric.md) before assigning
numeric completeness, accuracy, or tone scores. If the authoritative scoring
rubric is missing, ask for it rather than inventing score anchors; a qualitative
review can still proceed. Explain each score using the criterion and evidence.
Report per-dimension averages only over scored units, with the denominators.

Return a table and, when useful, a local CSV with Subdimension, Claimed Score,
Evidence Excerpt, Reviewer Output, Completeness, Accuracy, Tone, and Notes.
Mark excerpts as truncated when shortened and retain full evidence for evaluation.
Uploading the CSV is a separate, explicitly authorized action, not the default.
'''
            references = destination / 'references'
            references.mkdir(exist_ok=True)
            rubric = source / 'evals/rubric.md'
            if rubric.is_file():
                shutil.copyfile(rubric, references / 'eval-rubric.md')
            else:
                (references / 'eval-rubric.md').write_text(
                    '# Scoring rubric not supplied\n\n'
                    'The source plugin refers to `evals/rubric.md`, but does not include it.\n'
                    'Obtain the authoritative scoring rubric from the user or an accessible\n'
                    'internal source before assigning numeric scores. Do not invent it.\n'
                )
        if guide is not None:
            references = destination / 'references'
            references.mkdir(exist_ok=True)
            (references / 'guide.md').write_text(guide + '\n')
        frontmatter = f'---\nname: {name}\ndescription: {json.dumps(description)}\n---\n\n'
        (destination / 'SKILL.md').write_text(frontmatter + body)
    print(f'Generated {len(DESCRIPTIONS)} Codex skills in {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    generate(args.source, args.output)
