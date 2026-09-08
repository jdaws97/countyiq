from copy import deepcopy

from countyiq.lib.pass0_facts import FACTS_SCHEMA
from eval.pass0_schema_guidance import annotated_schema


def test_field_annotations_preserve_contract_and_strict_reference_compatibility():
    original = deepcopy(FACTS_SCHEMA)
    annotated = annotated_schema(FACTS_SCHEMA)

    def without_descriptions(value):
        if isinstance(value, list):
            return [without_descriptions(item) for item in value]
        if isinstance(value, dict):
            # The serving provider rejects sibling keywords beside a reference.
            if "$ref" in value:
                assert set(value) == {"$ref"}
            return {
                key: without_descriptions(item)
                for key, item in value.items()
                if key != "description"
            }
        return value

    assert without_descriptions(annotated) == without_descriptions(original)
    assert FACTS_SCHEMA == original
    assert annotated["$defs"]["participant"]["description"]
