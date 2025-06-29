from django import template
from django.utils.dateparse import parse_datetime

register = template.Library()

@register.filter
def parse_and_format_datetime(value, date_format):
    if value:
        parsed_date = parse_datetime(value)
        if parsed_date:
            return parsed_date.strftime(date_format)
    return ''

