from django import template
import ast


register = template.Library()

@register.filter
def get(data, key):
    if isinstance(data, dict):
        return data.get(key)
    elif isinstance(data, str):
        str_to_dict = ast.literal_eval(data)
        return str_to_dict[key]


@register.filter
def unpack_associated_field(lst):
    try:
        result = lst[0]
        return result
    except Exception as e:
        return {'value': 'Нет значения'}


@register.filter
def get_from_list(list_with_dict, key):
    try:
        dictionary = list_with_dict[0]
        return dictionary.get(key, 'Шаблон не задан')
    except IndexError as e:
        return 'Шаблон не задан'