from copy import copy
import re

from graphql.language import ast as graphql_ast, parser as graphql_parser

from .iterables import find, to_dict, to_multidict


def document_text_to_query(document_text, query_type):
    document_ast = graphql_parser.parse(document_text)
    
    operation = find(
        lambda definition: isinstance(definition, graphql_ast.OperationDefinition),
        document_ast.definitions,
    )
    
    fragments = to_dict(
        (fragment.name.value, fragment)
        for fragment in filter(
            lambda definition: isinstance(definition, graphql_ast.FragmentDefinition),
            document_ast.definitions,
        )
    )
    
    fields = to_dict(_read_selection_set(
        operation.selection_set,
        graph_type=query_type,
        fragments=fragments,
    ))
    return query_type(**fields)


def _read_selection_set(selection_set, graph_type, fragments):
    if selection_set is None:
        return ()
    else:
        return [
            _read_graphql_field(graphql_field, graph_type=graph_type, fragments=fragments)
            for graphql_field in _flatten_graphql_selections(selection_set.selections, fragments=fragments)
        ]


def _flatten_graphql_selections(selections, fragments):
    # TODO: handle type conditions
    # TODO: validation
    graphql_fields = to_multidict(
        (_field_key(graphql_field), graphql_field)
        for selection in selections
        for graphql_field in _graphql_selection_to_graphql_fields(selection, fragments=fragments)
    )
    
    return [
        _merge_graphql_fields(graphql_fields_to_merge)
        for field_name, graphql_fields_to_merge in graphql_fields.items()
    ]


def _merge_graphql_fields(graphql_fields):
    merged_field = copy(graphql_fields[0])
    merged_field.selection_set = copy(merged_field.selection_set)
    
    for graphql_field in graphql_fields[1:]:
        if graphql_field.selection_set is not None:
            merged_field.selection_set.selections += graphql_field.selection_set.selections
    
    return merged_field


def _graphql_selection_to_graphql_fields(selection, fragments):
    if isinstance(selection, graphql_ast.Field):
        return (selection, )
    
    elif isinstance(selection, graphql_ast.InlineFragment):
        return _graphql_fragment_to_graphql_fields(selection, fragments=fragments)
    
    elif isinstance(selection, graphql_ast.FragmentSpread):
        return _graphql_fragment_to_graphql_fields(fragments[selection.name.value], fragments=fragments)
        
    else:
        raise Exception("Unhandled selection type: {}".format(type(selection)))


def _graphql_fragment_to_graphql_fields(fragment, fragments):
    return [
        graphql_field
        for subselection in fragment.selection_set.selections
        for graphql_field in _graphql_selection_to_graphql_fields(subselection, fragments=fragments)
    ]


def _read_graphql_field(graphql_field, graph_type, fragments):
    key = _field_key(graphql_field)
    field_name = _camel_case_to_snake_case(graphql_field.name.value)
    field = getattr(graph_type, field_name)
    args = [
        getattr(field, arg.name.value)(int(arg.value.value))
        for arg in graphql_field.arguments
    ]
    subfields = to_dict(_read_selection_set(graphql_field.selection_set, graph_type=field.type, fragments=fragments))
    field_query = field(*args, **subfields)
    return (key, field_query)


def _field_key(selection):
    if selection.alias is None:
        return selection.name.value
    else:
        return selection.alias.value


def _camel_case_to_snake_case(value):
    # From: https://stackoverflow.com/revisions/1176023/2
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', value)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()