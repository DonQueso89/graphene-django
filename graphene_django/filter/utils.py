import graphene

from django_filters.utils import get_model_field
from django_filters.filters import Filter, BaseCSVFilter

from .filterset import custom_filterset_factory, setup_filterset
from .filters import InFilter, RangeFilter


def get_filtering_args_from_filterset(filterset_class, type):
    """ Inspect a FilterSet and produce the arguments to pass to
        a Graphene Field. These arguments will be available to
        filter against in the GraphQL
    """
    from ..forms.converter import convert_form_field

    args = {}
    model = filterset_class._meta.model
    for name, filter_field in filterset_class.base_filters.items():
        form_field = None
        filter_type = filter_field.lookup_expr

        if name in filterset_class.declared_filters:
            # Get the filter field from the explicitly declared filter
            form_field = filter_field.field
            field = convert_form_field(form_field)
        else:
            # Get the filter field with no explicit type declaration
            model_field = get_model_field(model, filter_field.field_name)
            if filter_type != "isnull" and hasattr(model_field, "formfield"):
                form_field = model_field.formfield(
                    required=filter_field.extra.get("required", False)
                )

            # Fallback to field defined on filter if we can't get it from the
            # model field
            if not form_field:
                form_field = filter_field.field

            field = convert_form_field(form_field)

        if filter_type in {"in", "range", "contains", "overlap"}:
            # Replace CSV filters (`in`, `range`, `contains`, `overlap`) argument type to be a list of
            # the same type as the field.  See comments in
            # `replace_csv_filters` method for more details.
            field = graphene.List(field.get_type())

        field_type = field.Argument()
        field_type.description = str(filter_field.label) if filter_field.label else None
        args[name] = field_type

    return args


def get_filterset_class(filterset_class, **meta):
    """
    Get the class to be used as the FilterSet.
    """
    if filterset_class:
        # If were given a FilterSet class, then set it up.
        graphene_filterset_class = setup_filterset(filterset_class)
    else:
        # Otherwise create one.
        graphene_filterset_class = custom_filterset_factory(**meta)

    replace_csv_filters(graphene_filterset_class)
    return graphene_filterset_class


def replace_csv_filters(filterset_class):
    """
    Replace the "in", "contains", "overlap" and "range" filters (that are not explicitly declared) to not be BaseCSVFilter (BaseInFilter, BaseRangeFilter) objects anymore
    but regular Filter objects that simply use the input value as filter argument on the queryset.

    This is because those BaseCSVFilter are expecting a string as input with comma separated value but with GraphQl we
    can actually have a list as input and have a proper type verification of each value in the list.

    See issue https://github.com/graphql-python/graphene-django/issues/1068.
    """
    for name, filter_field in list(filterset_class.base_filters.items()):
        filter_type = filter_field.lookup_expr
        if name in filterset_class.declared_filters:
            continue
        if filter_type in {"in", "contains", "overlap"}:
            filterset_class.base_filters[name] = InFilter(
                field_name=filter_field.field_name,
                lookup_expr=filter_field.lookup_expr,
                label=filter_field.label,
                method=filter_field.method,
                exclude=filter_field.exclude,
                **filter_field.extra
            )

        elif filter_type == "range":
            filterset_class.base_filters[name] = RangeFilter(
                field_name=filter_field.field_name,
                lookup_expr=filter_field.lookup_expr,
                label=filter_field.label,
                method=filter_field.method,
                exclude=filter_field.exclude,
                **filter_field.extra
            )
