"""Deterministic reviewed anchors; ambiguous aliases never become entity starts."""
import re
import unicodedata

from research_assistant.contracts import EvidenceItem, fingerprint
from research_assistant.retrieval.catalog import ReviewCatalog, evidence_text
from research_assistant.review.contracts import EntityDefinition


def unambiguous_matches(text: str, entities: dict[str,EntityDefinition]) -> dict[str,int]:
    """Return longest normalized alias length per entity; omit every ambiguous spelling."""
    normalize=lambda value:unicodedata.normalize('NFKC',value).casefold().strip()
    aliases={}
    for key,entity in entities.items():
        for alias in [entity.name,*entity.aliases]:
            normalized=normalize(alias)
            if normalized:aliases.setdefault(normalized,set()).add(key)
    matched={}
    for alias,keys in aliases.items():
        if len(keys)==1 and re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',normalize(text)):
            key=next(iter(keys));matched[key]=max(matched.get(key,0),len(alias))
    return matched


def graph_anchors(question: str, evidence: list[EvidenceItem], catalog: ReviewCatalog) -> tuple[list[dict],set[str],set[str],dict[str,list[str]]]:
    """Reserve one explicit Method/Dataset each, then fill four total slots from evidence."""
    hits=unambiguous_matches(question,catalog.entities)
    anchors=[]
    chosen={}
    for kind in ('method','dataset'):
        candidates=[key for key in hits if catalog.entities[key].kind==kind]
        chosen[kind]=sorted(candidates,key=lambda key:(-hits[key],key))[:1]
        for key in chosen[kind]:
            anchors.append({'id':'entity:'+key,'type':'entity','entity_id':key,'kind':kind,
                            'entity_node':fingerprint(catalog.entities[key].model_dump())})
    seen={a['id'] for a in anchors}
    for item in evidence:
        if len(anchors)>=4:break
        if item.id not in seen:
            anchors.append({'id':item.id,'type':'evidence','paper_id':item.paper_ids[0],
                            'chunk_ids':item.source_chunk_ids})
            seen.add(item.id)
    seed_items=[item for item in evidence if item.id in {a['id'] for a in anchors if a['type']=='evidence'}]
    shown=set().union(*(set(unambiguous_matches(evidence_text(item),catalog.entities)) for item in seed_items))
    expansion={kind:chosen[kind] or sorted(key for key in shown if catalog.entities[key].kind==kind)
               for kind in ('method','dataset')}
    return anchors,set(hits),shown,expansion
