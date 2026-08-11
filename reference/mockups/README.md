# Mockups

Design mockups that are parked, not adopted. Nothing here is a record, nothing
here validates, and nothing in the catalog reads from this directory.

A mockup lives here when an idea is worth looking at before anyone decides
whether to build it. Putting it in the repository rather than in a slide means
the idea can be opened, clicked and discussed on its own terms, and that it
does not quietly become a commitment just because it looks finished.

## beyond-ai-scenarios.html

What proposing a scenario would look like if Liszt carried more than one kind of
infrastructure. Walks a proposal against a described environment, a web
application or a population of endpoints, rather than against the AI stack that
every current record assumes.

Six web application and endpoint environments are worked through, two real
incidents are mapped into the standard record layout, and an engineering sheet
shows how the components of an environment would be edited.

`tools/build_viewer.py` embeds this file in its own tab in the viewer, inside an
isolated frame, labeled as a parked idea. The embed is optional by construction:
delete this file and the tab disappears, and the generated viewer is byte for
byte what it was before.

**Status: parked.** Adopting it means generalizing
`classification.ai_infrastructure_layer`, which is a required enum of five AI
values today. That change and its consequences are written up separately. Until
those decisions are made, this is a picture of an idea and nothing more.
